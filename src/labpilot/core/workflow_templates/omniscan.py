"""Omniscan.

A general N-dimensional scan: rasters a chosen subset of axes a bound ND
actuator actually has (auto-detected from its own schema, not hardcoded to
x/y/z) against a bound detector's reading — the detector can be 0D, 1D, or
2D (auto-detected the same way, via `detector_axes()`); a non-0D
detector's OWN internal axes (e.g. a spectrometer's wavelength axis, a
camera's row/col pixel axes) are appended as EXTRA dimensions of the
overall array, alongside the actuator's own scanned axes — they're never
movable/scannable by any actuator, just extra dimensions of what the
detector hands back at every actuator position. Generalizes qudi's own
`scanning_probe_logic.py`/`scanning_data_logic.py` pattern (per-axis
range+resolution, and picking any subset of the scanner's axes for a
given scan while the rest stay parked at a fixed "hold" position — see
SCAN_AXES/HOLD_POSITIONS below) beyond qudi's hardware-native 1D/2D-only,
0D-detector-only scanning-probe interface, to any number of actuator axes
against any detector dimensionality. Read by the native desktop window
(components/workflow_result.py's `NDScanResultView`) as a set of coupled
2D mean-projections, one per pair of axes (actuator-actuator,
actuator-detector, or detector-detector), with a region selector on each
panel that filters what the *other* panels average over — the same
coupled-image/coupled-spectrum interaction this session's confocal work
was asked to draw from (github.com/AdrienR09/hyperspex). Only
actuator-actuator panels get a live crosshair (see "actuator_axis_count"
below and NDScanResultView) — dragging a detector-internal axis has
nothing to move.

References its instruments by *role*, not a specific instrument id — bind
"actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.

The actual point-by-point move-and-read loop below is
`core/workflow/capabilities.py`'s `ScanCapability.run_grid` — the same
object `OptimizerCapability`'s own sub-scans are built on
(`WORKFLOW_COMPOSITION.md`'s Phase 3 design) — this template only resolves
which axes are active and reshapes what comes back, not how to move an
actuator or wait for it to settle.
"""

import numpy as np

from labpilot.core.data.dataset import DatasetPatch
from labpilot.core.session import Session
from labpilot.core.workflow.capabilities import (
    HardwareTimedScanCapability,
    ScanCapability,
)
from labpilot.core.workflow_templates._common import detector_axes

REQUIRED_INSTRUMENTS = {
    # "actuator"+"detector" (the per-point move-and-read path, below) and
    # "scanner" (the hardware-timed whole-frame path — a single device
    # implementing HardwareScanMixin, e.g. a real NI DAQ card managing its
    # own position waveform + detector readback together, one hardware
    # clock, no per-pixel software round-trip; see
    # instruments/hardware_scan_mixin.py) are two alternative ways to run
    # this SAME workflow — bind whichever one you have. All three are
    # "optional" here (engine.py's _check_instrument_bindings skips an
    # optional role's binding check entirely) since exactly which pair
    # is bound isn't known until run time; run() below raises a clear
    # error if neither alternative ends up bound.
    "actuator": {"kind": "motor", "dimensionality": "ND", "optional": True},
    # No "dimensionality" here (unlike "actuator" above) — deliberately
    # accepts a 0D, 1D, or 2D detector interchangeably; detector_axes()
    # below auto-detects which, from the bound instrument's own schema.
    "detector": {"kind": "detector", "optional": True},
    "scanner": {"kind": "generic", "optional": True},
}
ACTUATOR_ID = "actuator"
DETECTOR_ID = "detector"
SCANNER_ID = "scanner"

# Fast-axis pixel rate for the hardware-timed "scanner" path (Hz) — see
# HardwareTimedScanCapability.run_scan; ignored entirely when running the
# ordinary per-point actuator+detector path instead.
SCAN_FREQUENCY = 5000.0

# Declares this workflow's tier-2 capabilities (WORKFLOW_COMPOSITION.md) —
# the server auto-wires an optimizer (generic /optimize/start|stop|state
# routes, backed by OptimizerCapability, "around" the "actuator" role) and
# a save action, with no per-template server.py/workflow_window.py code.
# Every OTHER existing template still works unchanged with no CAPABILITIES
# constant at all (read_capabilities() falls back to inferring the
# optimizer from RESULT_UI["crosshair"] below) — this workflow declares it
# explicitly since it's the first one built against the Phase 3 pattern.
CAPABILITIES = {
    "scan": {},
    "optimizer": {"around": "actuator"},
    "save": {},
}

# Read by the native desktop window (workflow_window.py) to render one
# live 2D projection per pair of axes as the scan runs — see
# session.report_progress() below and NDScanResultView. "crosshair" draws
# a draggable qudi-scanner-style crosshair on every ACTUATOR-actuator
# projection panel, tracking (and, when idle, click/drag-moving) the
# "actuator" role's live position — no fixed x_axis/y_axis needed here
# (unlike confocal_scanner.py's image2d crosshair) since which axes exist
# is only known once the actuator/detector are actually bound.
# "actuator_axis_count_key" tells the UI how many of the LEADING entries
# in axis_names/axis_positions are the actuator's own (movable) axes —
# everything after that is a detector-internal axis (not movable).
RESULT_UI = {
    "type": "ndscan",
    "value_key": "data",
    "shape_key": "shape",
    "axis_names_key": "axis_names",
    "axis_positions_key": "axis_positions",
    "actuator_axis_count_key": "actuator_axis_count",
    "value_label": "Detector reading",
    "crosshair": {"role": "actuator"},
}

# (start, stop, num_points) per axis — units are whatever the bound
# actuator's own schema reports. Only axes the bound actuator actually
# declares (readable+settable, non-boolean) are ever scanned; an entry
# here for an axis the actuator doesn't have is simply ignored (edit this
# dict to match a real actuator's real axis names — "x"/"y"/"z" are just
# the common case).
AXIS_RANGES = {
    "x": (-4.0, 4.0, 5),
    "y": (-4.0, 4.0, 5),
    "z": (-2.0, 2.0, 3),
}

# Which of the axes declared above to actually raster THIS run — qudi's
# own scanning_probe_logic pattern: any subset of the scanner's axes can
# be chosen for a given scan, not just a fixed 1D/2D pair. Defaults to
# every declared axis (a full N-D sweep); narrow it to e.g. ["x", "y"]
# for a quick 2D scan while z stays parked wherever HOLD_POSITIONS (or its
# last commanded position, if not listed there either) leaves it.
SCAN_AXES: list = ["x", "y", "z"]

# Fixed position to move to (and hold for the whole run) for any available
# axis that's NOT in SCAN_AXES. An axis missing here is simply left at
# wherever it already is.
HOLD_POSITIONS: dict = {}

SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000

# Safety ceiling on the result array's total element count (actuator grid
# points x detector values/point) — see on_progress()'s check below.
_MAX_SCAN_ELEMENTS = 50_000_000


async def run(session: Session) -> dict:
    has_scanner = session.has(SCANNER_ID)
    has_actuator_pair = session.has(ACTUATOR_ID) and session.has(DETECTOR_ID)
    if not has_scanner and not has_actuator_pair:
        raise RuntimeError(
            "Bind either 'scanner' (a single hardware-timed-scanning device, e.g. a "
            "real NI DAQ card or mock_ni_scanner) or both 'actuator' and 'detector' "
            "(the ordinary per-point move-and-read path) before running this workflow."
        )
    if has_scanner:
        return await _run_hardware_timed(session)
    return await _run_per_point(session)


async def _run_hardware_timed(session: Session) -> dict:
    """Whole-frame scan via a single HardwareScanMixin-implementing
    "scanner" device — see HardwareTimedScanCapability's own docstring
    for why this is a fundamentally different path from
    `_run_per_point` below (one shared hardware clock drives both
    position and detector readback, no per-pixel software round-trip),
    not just a faster version of the same loop."""
    scanner = session.get(SCANNER_ID)

    active_axes = [name for name in SCAN_AXES if name in AXIS_RANGES]
    if not active_axes:
        raise RuntimeError(
            f"None of SCAN_AXES {SCAN_AXES} are declared in AXIS_RANGES {list(AXIS_RANGES)} "
            f"— edit one to match the other."
        )
    if len(active_axes) > 2:
        raise RuntimeError(
            f"The hardware-timed 'scanner' path supports at most 2 simultaneously-scanned "
            f"axes (only the fast axis is genuinely hardware-clocked on this class of "
            f"device — see instruments/hardware_scan_mixin.py), but SCAN_AXES selects "
            f"{len(active_axes)}: {active_axes}. Narrow SCAN_AXES to 1 or 2 axes, or use "
            f"the 'actuator'+'detector' per-point path instead for a 3+ axis scan."
        )

    # active_axes is ["slow", "fast"] (or just ["only"] for 1D) — first
    # axis varies slowest, matching _run_per_point's own itertools.product
    # convention below and every result view built on it. build_scan_waveform
    # (instruments/hardware_scan_mixin.py) uses the OPPOSITE convention for
    # a 2-axis scan (axes[0]=fast, axes[1]=slow, mirroring the interfuse's
    # own tile/repeat order) — so call it with active_axes REVERSED, and
    # reverse its "positions"/"shape" fields back before reporting, so
    # this template's own output keeps the one "first axis slowest"
    # convention throughout. Its "data" field needs no such reversal: the
    # flat array it returns is already laid out slow-axis-outer/
    # fast-axis-inner — exactly what reshaping to [n_slow, n_fast] (this
    # function's own "shape", not build_scan_waveform's) expects.
    waveform_axes = list(reversed(active_axes))
    ranges = {axis: (AXIS_RANGES[axis][0], AXIS_RANGES[axis][1]) for axis in active_axes}
    resolution = {axis: int(AXIS_RANGES[axis][2]) for axis in active_axes}

    async def on_progress(chunk: dict) -> None:
        axis_positions = list(reversed(chunk["positions"]))
        shape = list(reversed(chunk["shape"]))
        await session.report_progress({
            "data": chunk["data"],
            "shape": shape,
            "axis_names": active_axes,
            "axis_positions": [list(p) for p in axis_positions],
            "actuator_axis_count": len(active_axes),
            "completed": chunk["completed"],
            "total": chunk["total"],
        })

    axis_units = {name: scanner.schema.units.get(name, "") for name in active_axes}
    scan = HardwareTimedScanCapability(scanner)
    result = await scan.run_scan(waveform_axes, ranges, resolution, SCAN_FREQUENCY, on_progress=on_progress)
    axis_positions = [list(p) for p in reversed(result["positions"])]
    shape = list(reversed(result["shape"]))

    return {
        "scanner": SCANNER_ID,
        "axis_names": active_axes,
        "axis_positions": axis_positions,
        "actuator_axis_count": len(active_axes),
        "axis_units": axis_units,
        "shape": shape,
        "data": result["data"],  # flat, row-major (last axis varies fastest) — reshape to `shape` to use
    }


async def _run_per_point(session: Session) -> dict:
    """Per-point actuator-move + detector-read loop — the original
    omniscan behavior, unchanged; see ScanCapability."""
    actuator = session.get(ACTUATOR_ID)
    detector = session.get(DETECTOR_ID)

    settable = actuator.schema.settable
    available_axes = [name for name in AXIS_RANGES if name in settable and settable[name] != "bool"]
    if not available_axes:
        raise RuntimeError(
            f"None of {list(AXIS_RANGES)} are settable axes on the bound actuator "
            f"(it declares: {list(settable)}) — edit AXIS_RANGES to match its real axis names."
        )

    active_axes = [name for name in SCAN_AXES if name in available_axes]
    if not active_axes:
        raise RuntimeError(
            f"None of SCAN_AXES {SCAN_AXES} are available on the bound actuator "
            f"(available: {available_axes}) — edit SCAN_AXES to pick from those."
        )

    hold_targets = {
        name: HOLD_POSITIONS[name]
        for name in available_axes
        if name not in active_axes and name in HOLD_POSITIONS
    }

    # Populated on the first point, once the detector's own internal axes
    # (if any) are known from a real reading — a schema only declares
    # dtypes, not sizes, so this can't be known ahead of time.
    state: dict = {}

    async def on_progress(grid_progress: dict) -> None:
        readings = grid_progress["readings"]
        if "value_key" not in state:
            value_key, det_axis_names, det_axis_positions = detector_axes(
                detector.schema, readings[0]
            )
            detector_shape = [len(positions) for positions in det_axis_positions]
            per_point = 1
            for n in detector_shape:
                per_point *= n
            actuator_shape = grid_progress["shape"]
            total_points = 1
            for n in actuator_shape:
                total_points *= n
            total_elements = total_points * per_point
            if total_elements > _MAX_SCAN_ELEMENTS:
                # AXIS_RANGES' point counts multiply directly into this
                # array's size — e.g. 50x50x30 actuator points against a
                # 32x32x64 detector cube is ~4.9 BILLION elements, an
                # allocation that thrashes/exhausts memory well before it
                # ever finishes, with nothing surfaced to explain why the
                # scan appears hung. Fail fast with the actual numbers
                # instead, since the fix (smaller AXIS_RANGES/detector
                # resolution) is always on the caller's side.
                raise RuntimeError(
                    f"This scan's result array would need {total_elements:,} elements "
                    f"({total_points:,} actuator points x {per_point:,} detector "
                    f"values/point) — over the {_MAX_SCAN_ELEMENTS:,}-element safety "
                    f"limit. Reduce AXIS_RANGES' point counts or the detector's own "
                    f"resolution."
                )
            primary = readings[0].primary() if hasattr(readings[0], "primary") else None
            state.update({
                # Units travel with the result so the saved HDF5 (and any
                # view) can label the axes — see core/storage/runs.py.
                "value_unit": primary.unit if primary is not None else "",
                "axis_units": {
                    name: actuator.schema.units.get(name, "") for name in active_axes
                } | {
                    axis.name: axis.unit
                    for axis in (readings[0].axes() if hasattr(readings[0], "axes") else ())
                },
                "value_key": value_key,
                "per_point": per_point,
                "shape": actuator_shape + detector_shape,
                "axis_names": active_axes + det_axis_names,
                "axis_positions": grid_progress["positions"] + det_axis_positions,
                "data": [None] * total_elements,
            })

        value_key = state["value_key"]
        per_point = state["per_point"]
        completed = grid_progress["completed"]
        value = readings[-1][value_key]
        flat_values = np.asarray(value, dtype=float).ravel().tolist() if per_point > 1 else [float(value)]
        start = (completed - 1) * per_point
        state["data"][start:start + per_point] = flat_values

        await session.report_progress({
            "data": state["data"],
            "shape": state["shape"],
            "axis_names": state["axis_names"],
            "axis_positions": state["axis_positions"],
            "actuator_axis_count": len(active_axes),
            "value_unit": state["value_unit"],
            "axis_units": state["axis_units"],
            "completed": completed,
            "total": grid_progress["total"],
        })
        # The live per-point path: one `DatasetPatch`, whose size is this
        # point's own contribution however far the scan has progressed —
        # see Session.report_reading(). The run-level description (shape,
        # axis names and positions) goes with the FIRST patch only;
        # repeating it would ship an axis array per point, which for a
        # 1800-channel spectrometer is most of the traffic the patch
        # exists to avoid. Clients merge what is present and keep the rest.
        description = {} if completed > 1 else {
            "shape": state["shape"],
            "axis_names": state["axis_names"],
            "axis_positions": state["axis_positions"],
            "actuator_axis_count": len(active_axes),
            "value_unit": state["value_unit"],
            "axis_units": state["axis_units"],
        }
        await session.report_reading(
            DatasetPatch("data", start, flat_values, seq=completed),
            completed=completed,
            total=grid_progress["total"],
            **description,
        )

    scan = ScanCapability(actuator, detector, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
    await scan.run_grid(active_axes, AXIS_RANGES, hold_positions=hold_targets or None, on_progress=on_progress)

    return {
        "actuator": ACTUATOR_ID,
        "detector": DETECTOR_ID,
        "axis_names": state["axis_names"],
        "axis_positions": state["axis_positions"],
        "actuator_axis_count": len(active_axes),
        "value_unit": state["value_unit"],
        "axis_units": state["axis_units"],
        "shape": state["shape"],
        "data": state["data"],  # flat, row-major (last axis varies fastest) — reshape to `shape` to use
    }
