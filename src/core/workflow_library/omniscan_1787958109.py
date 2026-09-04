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

from core.session import Session
from core.workflow.capabilities import ScanCapability
from core.workflow_templates._common import detector_axes

REQUIRED_INSTRUMENTS = {
    "actuator": {"kind": "motor", "dimensionality": "ND"},
    # No "dimensionality" here (unlike "actuator" above) — deliberately
    # accepts a 0D, 1D, or 2D detector interchangeably; detector_axes()
    # below auto-detects which, from the bound instrument's own schema.
    "detector": {"kind": "detector"},
}
ACTUATOR_ID = "actuator"
DETECTOR_ID = "detector"

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
AXIS_RANGES = {'x': [0.0, 4.0, 30], 'y': [0.0, 4.0, 30]}

# Which of the axes declared above to actually raster THIS run — qudi's
# own scanning_probe_logic pattern: any subset of the scanner's axes can
# be chosen for a given scan, not just a fixed 1D/2D pair. Defaults to
# every declared axis (a full N-D sweep); narrow it to e.g. ["x", "y"]
# for a quick 2D scan while z stays parked wherever HOLD_POSITIONS (or its
# last commanded position, if not listed there either) leaves it.
SCAN_AXES: list = ['x', 'y']

# Fixed position to move to (and hold for the whole run) for any available
# axis that's NOT in SCAN_AXES. An axis missing here is simply left at
# wherever it already is.
HOLD_POSITIONS: dict = {}

SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000

# Safety ceiling on the result array's total element count (actuator grid
# points x detector values/point) — see on_progress()'s check below.
_MAX_SCAN_ELEMENTS = 50000000


async def run(session: Session) -> dict:
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
                detector.schema.readable, readings[0]
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
            state.update({
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
            "completed": completed,
            "total": grid_progress["total"],
        })
        # A bounded-size (always `per_point` values, however big the scan
        # gets) companion to the report_progress() call above — see
        # Session.report_reading()'s docstring. Drives the desktop app's
        # live per-point view without it needing to refetch the whole
        # (potentially multi-million-element) array on every point.
        await session.report_reading({
            "index": start,
            "values": flat_values,
            "shape": state["shape"],
            "axis_names": state["axis_names"],
            "axis_positions": state["axis_positions"],
            "actuator_axis_count": len(active_axes),
            "completed": completed,
            "total": grid_progress["total"],
        })

    scan = ScanCapability(actuator, detector, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
    await scan.run_grid(active_axes, AXIS_RANGES, hold_positions=hold_targets or None, on_progress=on_progress)

    return {
        "actuator": ACTUATOR_ID,
        "detector": DETECTOR_ID,
        "axis_names": state["axis_names"],
        "axis_positions": state["axis_positions"],
        "actuator_axis_count": len(active_axes),
        "shape": state["shape"],
        "data": state["data"],  # flat, row-major (last axis varies fastest) — reshape to `shape` to use
    }
