"""Omniscan.

A general N-dimensional scan: rasters a chosen subset of axes a bound ND
actuator actually has (auto-detected from its own schema, not hardcoded to
x/y/z) against a bound detector's reading — the detector can be 0D, 1D, or
2D; a non-0D detector's OWN internal axes (a spectrometer's wavelength
axis, a camera's row/col pixel axes) are appended as EXTRA dimensions of
the overall array, alongside the actuator's own scanned axes. They are
never movable by any actuator, just extra dimensions of what the detector
hands back at every actuator position. Generalizes qudi's own
`scanning_probe_logic.py`/`scanning_data_logic.py` pattern (per-axis
range+resolution, and picking any subset of the scanner's axes for a given
scan while the rest stay parked at a fixed "hold" position — see
SCAN_AXES/HOLD_POSITIONS below) beyond qudi's hardware-native 1D/2D-only,
0D-detector-only scanning-probe interface, to any number of actuator axes
against any detector dimensionality. Read by the native desktop window
(components/workflow_result.py's `NDScanResultView`) as a set of coupled
2D mean-projections, one per pair of axes, with a region selector on each
panel that filters what the *other* panels average over. Only
actuator-actuator panels get a live crosshair — dragging a
detector-internal axis has nothing to move.

References its instruments by *role*, not a specific instrument id — bind
"actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.

## What this template does and does not do

It chooses which axes to scan, and hands that to a `Plan`
(`core/run/plans.py`). It does not allocate the result, count progress,
assemble axis metadata, publish frames or stream patches: `Run` does all of
that for every plan, so the conventions those depend on — flat row-major
layout, first axis slowest, `None` for a point not yet taken, the leading
axes being the movable ones — are stated once rather than re-implemented
per template.

That is the whole of the ~120 lines this file used to spend discovering, on
its first progress callback, how big its own result would be. A plan is
described before anything moves, which is also what makes the run
pausable and abortable: `Run` owns the loop between points.
"""

from labpilot.core.run import ScanAxis, ScanPlan, execute
from labpilot.core.run.plans import HardwareTimedScanPlan
from labpilot.core.session import Session

REQUIRED_INSTRUMENTS = {
    # "actuator"+"detector" (the per-point move-and-read path) and
    # "scanner" (the hardware-timed whole-frame path — a single device
    # implementing HardwareScanMixin, e.g. a real NI DAQ card managing its
    # own position waveform + detector readback together, one hardware
    # clock, no per-pixel software round-trip; see
    # instruments/hardware_scan_mixin.py) are two alternative ways to run
    # this SAME workflow — bind whichever one you have. All three are
    # "optional" here (engine.py's _check_instrument_bindings skips an
    # optional role's binding check entirely) since exactly which pair is
    # bound isn't known until run time; run() below raises a clear error
    # if neither alternative ends up bound.
    "actuator": {"kind": "motor", "dimensionality": "ND", "optional": True},
    # No "dimensionality" here (unlike "actuator") — deliberately accepts a
    # 0D, 1D or 2D detector interchangeably. What a point contains is
    # discovered by the plan, from one reading, before the scan starts.
    "detector": {"kind": "detector", "optional": True},
    "scanner": {"kind": "generic", "optional": True},
}
ACTUATOR_ID = "actuator"
DETECTOR_ID = "detector"
SCANNER_ID = "scanner"

# Fast-axis pixel rate for the hardware-timed "scanner" path (Hz) — see
# HardwareTimedScanPlan; ignored entirely on the per-point path.
SCAN_FREQUENCY = 5000.0

# Declares this workflow's tier-2 capabilities (WORKFLOW_COMPOSITION.md) —
# the server auto-wires an optimizer (generic /optimize/start|stop|state
# routes, "around" the "actuator" role) and a save action, with no
# per-template server.py/workflow_window.py code.
CAPABILITIES = {
    "scan": {},
    "optimizer": {"around": "actuator"},
    "save": {},
}

# Read by the native desktop window (workflow_window.py) to render one live
# 2D projection per pair of axes as the scan runs. "crosshair" draws a
# draggable qudi-scanner-style crosshair on every ACTUATOR-actuator
# projection panel, tracking (and, when idle, click/drag-moving) the
# "actuator" role's live position.
#
# Still declared, though `pick_view` (core/workflow/view.py) would now
# infer an equivalent spec from the data itself: an explicit declaration
# always wins, and this one names the crosshair's role.
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
# declares as positions are ever scanned; an entry here for an axis it
# doesn't have is simply ignored (edit this dict to match a real
# actuator's real axis names — "x"/"y"/"z" are just the common case).
AXIS_RANGES = {
    "x": (-4.0, 4.0, 5),
    "y": (-4.0, 4.0, 5),
    "z": (-2.0, 2.0, 3),
}

# Which of the axes declared above to actually raster THIS run — qudi's own
# scanning_probe_logic pattern: any subset of the scanner's axes can be
# chosen for a given scan, not just a fixed 1D/2D pair. Defaults to every
# declared axis (a full N-D sweep); narrow it to e.g. ["x", "y"] for a
# quick 2D scan while z stays parked wherever HOLD_POSITIONS (or its last
# commanded position, if not listed there either) leaves it.
SCAN_AXES: list = ["x", "y", "z"]

# Fixed position to move to (and hold for the whole run) for any available
# axis that's NOT in SCAN_AXES. An axis missing here is left where it is.
HOLD_POSITIONS: dict = {}

SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    has_scanner = session.has(SCANNER_ID)
    has_actuator_pair = session.has(ACTUATOR_ID) and session.has(DETECTOR_ID)
    if not has_scanner and not has_actuator_pair:
        raise RuntimeError(
            "Bind either 'scanner' (a single hardware-timed-scanning device, e.g. a "
            "real NI DAQ card or mock_ni_scanner) or both 'actuator' and 'detector' "
            "(the ordinary per-point move-and-read path) before running this workflow."
        )
    plan = _scanner_plan(session) if has_scanner else _per_point_plan(session)
    result = await execute(session, plan)
    return {
        # Which role produced this, for provenance in the saved file.
        **({"scanner": SCANNER_ID} if has_scanner
           else {"actuator": ACTUATOR_ID, "detector": DETECTOR_ID}),
        **result,
    }


def _axes_for(session: Session, role: str, available: list[str]) -> list[ScanAxis]:
    """The axes to sweep, as the plan wants them."""
    active = [name for name in SCAN_AXES if name in available]
    if not active:
        raise RuntimeError(
            f"None of SCAN_AXES {SCAN_AXES} are available on the bound {role} "
            f"(available: {available}) — edit SCAN_AXES to pick from those."
        )
    return [
        ScanAxis(name, role, *AXIS_RANGES[name][:2], points=int(AXIS_RANGES[name][2]))
        for name in active
    ]


def _per_point_plan(session: Session) -> ScanPlan:
    actuator = session.get(ACTUATOR_ID)
    available = [name for name in AXIS_RANGES if name in actuator.schema.position_axes]
    if not available:
        raise RuntimeError(
            f"None of {list(AXIS_RANGES)} are position axes on the bound actuator "
            f"(it declares: {list(actuator.schema.position_axes)}) — edit AXIS_RANGES "
            f"to match its real axis names."
        )
    axes = _axes_for(session, ACTUATOR_ID, available)
    scanned = {axis.name for axis in axes}
    return ScanPlan(
        axes=axes,
        detector=DETECTOR_ID,
        name="omniscan",
        hold={
            name: value for name, value in HOLD_POSITIONS.items()
            if name in available and name not in scanned
        },
        hold_device=ACTUATOR_ID,
        settle_tolerance=SETTLE_TOLERANCE,
        max_settle_polls=MAX_SETTLE_POLLS,
    )


def _scanner_plan(session: Session) -> HardwareTimedScanPlan:
    axes = _axes_for(session, SCANNER_ID, list(AXIS_RANGES))
    if len(axes) > 2:
        raise RuntimeError(
            f"The hardware-timed 'scanner' path supports at most 2 simultaneously-"
            f"scanned axes (only the fast axis is genuinely hardware-clocked on this "
            f"class of device — see instruments/hardware_scan_mixin.py), but "
            f"SCAN_AXES selects {len(axes)}: {[a.name for a in axes]}. Narrow "
            f"SCAN_AXES, or use the 'actuator'+'detector' per-point path instead."
        )
    return HardwareTimedScanPlan(
        axes=axes, scanner=SCANNER_ID, frequency=SCAN_FREQUENCY, name="omniscan",
    )
