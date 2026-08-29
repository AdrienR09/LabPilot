"""Omniscan.

A general N-dimensional scan: rasters a chosen subset of axes a bound ND
actuator actually has (auto-detected from its own schema, not hardcoded to
x/y/z) against a 0D detector's reading, building an N-dimensional array —
generalizing qudi's own `scanning_probe_logic.py`/`scanning_data_logic.py`
pattern (per-axis range+resolution, and picking any subset of the
scanner's axes for a given scan while the rest stay parked at a fixed
"hold" position — see SCAN_AXES/HOLD_POSITIONS below) beyond qudi's
hardware-native 1D/2D-only scanning-probe interface, to any number of
axes on any generic ND actuator. Read by the native desktop window
(components/workflow_result.py's `NDScanResultView`) as a set of coupled
2D mean-projections, one per pair of scanned axes, with a region selector
on each panel that filters what the *other* panels average over — the
same coupled-image/coupled-spectrum interaction this session's confocal
work was asked to draw from (github.com/AdrienR09/hyperspex).

References its instruments by *role*, not a specific instrument id — bind
"actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

import itertools
from typing import Optional

from core.session import Session
from core.workflow_templates._common import move_and_settle

REQUIRED_INSTRUMENTS = {
    "actuator": {"kind": "motor", "dimensionality": "ND"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
ACTUATOR_ID = "actuator"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render one
# live 2D projection per pair of scanned axes as the scan runs — see
# session.report_progress() below and NDScanResultView.
RESULT_UI = {
    "type": "ndscan",
    "value_key": "data",
    "shape_key": "shape",
    "axis_names_key": "axis_names",
    "axis_positions_key": "axis_positions",
    "value_label": "Detector reading",
}

# (start, stop, num_points) per axis — units are whatever the bound
# actuator's own schema reports. Only axes the bound actuator actually
# declares (readable+settable, non-boolean) are ever scanned; an entry
# here for an axis the actuator doesn't have is simply ignored (edit this
# dict to match a real actuator's real axis names — "x"/"y"/"z" are just
# the common case).
AXIS_RANGES = {'x': [-4.0, 4.0, 5], 'y': [-4.0, 4.0, 5]}

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


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    n = max(1, int(n))
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


async def run(session: Session) -> dict:
    actuator = session.get(ACTUATOR_ID)
    detector = session.get(DETECTOR_ID)
    value_key = next(iter(detector.schema.readable.keys()))

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
    if hold_targets:
        await move_and_settle(actuator, hold_targets, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)

    axis_position_lists = [_linspace(*AXIS_RANGES[name]) for name in active_axes]
    shape = [len(positions) for positions in axis_position_lists]
    total = 1
    for n in shape:
        total *= n

    data: list[Optional[float]] = [None] * total
    completed = 0
    await detector.stage()
    try:
        for flat_index, combo in enumerate(itertools.product(*axis_position_lists)):
            targets = dict(zip(active_axes, combo))
            await move_and_settle(actuator, targets, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)

            reading = await detector.read()
            data[flat_index] = float(reading[value_key])
            completed += 1
            await session.report_progress({
                "data": data,
                "shape": shape,
                "axis_names": active_axes,
                "axis_positions": axis_position_lists,
                "completed": completed,
                "total": total,
            })
    finally:
        await detector.unstage()

    return {
        "actuator": ACTUATOR_ID,
        "detector": DETECTOR_ID,
        "axis_names": active_axes,
        "axis_positions": axis_position_lists,
        "shape": shape,
        "data": data,  # flat, row-major (last axis varies fastest) — reshape to `shape` to use
    }
