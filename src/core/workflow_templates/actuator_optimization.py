"""Actuator optimization.

Optimizes a single actuator's position against a 0D detector's reading:
a coarse grid scan over `SEARCH_RANGE` to locate the approximate maximum,
followed by a local step-halving hill-climb refinement around it —
pyMoDAQ's `Optimisation` extension pattern (maximize a detector signal by
moving an actuator), generalized to any single-axis actuator + any 0D
detector pairing.

References its instruments by *role*, not a specific instrument id — bind
"actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from core.session import Session
from core.workflow_templates._common import move_and_settle

REQUIRED_INSTRUMENTS = {
    "actuator": {"kind": "motor", "dimensionality": "1D"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
ACTUATOR_ID = "actuator"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live
# curve of every position tried so far — see session.report_progress()
# below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "positions_tried",
    "y_key": "values_tried",
    "x_label": "Position",
    "y_label": "Detector reading",
}

# Coarse search bounds and grid resolution — units are whatever the bound
# actuator's own schema reports.
SEARCH_RANGE = (0.0, 10.0)
N_COARSE_STEPS = 11

# Local refinement around the coarse best: number of step-halving rounds,
# and each round's initial step size relative to the coarse grid spacing.
N_REFINE_ROUNDS = 4
REFINE_STEP_FRACTION = 0.5  # of the coarse grid spacing, halved every round

SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000


async def _measure_at(actuator, detector, position_key: str, value_key: str, target: float,
                       positions_tried: list, values_tried: list, session: Session, total: int) -> float:
    actual = await move_and_settle(actuator, {position_key: target}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
    data = await detector.read()
    value = float(data[value_key])
    positions_tried.append(float(actual[position_key]))
    values_tried.append(value)
    await session.report_progress({
        "positions_tried": positions_tried,
        "values_tried": values_tried,
        "completed": len(positions_tried),
        "total": total,
    })
    return value


async def run(session: Session) -> dict:
    actuator = session.get(ACTUATOR_ID)
    detector = session.get(DETECTOR_ID)
    position_key = next(iter(actuator.schema.readable.keys()))
    value_key = next(iter(detector.schema.readable.keys()))

    lo, hi = SEARCH_RANGE
    step = (hi - lo) / (N_COARSE_STEPS - 1) if N_COARSE_STEPS > 1 else 0.0
    coarse_positions = [lo + i * step for i in range(N_COARSE_STEPS)]
    total = N_COARSE_STEPS + N_REFINE_ROUNDS * 2

    positions_tried: list[float] = []
    values_tried: list[float] = []
    await detector.stage()
    try:
        # Coarse grid pass — locate the approximate maximum.
        for target in coarse_positions:
            await _measure_at(actuator, detector, position_key, value_key, target,
                               positions_tried, values_tried, session, total)

        best_idx = values_tried.index(max(values_tried))
        best_position = positions_tried[best_idx]
        best_value = values_tried[best_idx]

        # Local hill-climb refinement: try +/- a shrinking step around the
        # current best, keep whichever of the three (stay, +step, -step)
        # actually measured highest, halve the step, repeat.
        refine_step = step * REFINE_STEP_FRACTION
        for _ in range(N_REFINE_ROUNDS):
            candidates = [best_position - refine_step, best_position + refine_step]
            for candidate in candidates:
                if candidate < lo or candidate > hi:
                    continue
                value = await _measure_at(actuator, detector, position_key, value_key, candidate,
                                           positions_tried, values_tried, session, total)
                if value > best_value:
                    best_value = value
                    best_position = candidate
            refine_step /= 2.0

        # Leave the actuator parked at the best position found.
        await move_and_settle(actuator, {position_key: best_position}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
    finally:
        await detector.unstage()

    return {
        "actuator": ACTUATOR_ID,
        "detector": DETECTOR_ID,
        "positions_tried": positions_tried,
        "values_tried": values_tried,
        "best_position": best_position,
        "best_value": best_value,
    }
