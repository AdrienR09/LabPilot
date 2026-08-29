"""Generic 1D scan.

Steps any single-axis actuator through a series of positions and records
any 0D detector's reading at each one — pyMoDAQ's `DAQ_Scan` module
generalized to its simplest case (one actuator, one 0D detector, one
scanned axis), not tied to any particular instrument pairing the way
grating_spectrometer/pump_probe_spectroscopy are.

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
# curve that grows as the scan runs — see session.report_progress() below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "positions",
    "y_key": "values",
    "x_label": "Position",
    "y_label": "Detector reading",
}

# Positions to visit, in order — units are whatever the bound actuator's
# own schema reports.
POSITIONS = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]

# How close counts as "arrived", and a safety cap on settle-wait polls per
# position so an actuator that never settles (misconfigured hardware, or a
# target outside its travel range) fails loudly instead of hanging the
# workflow forever.
SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    actuator = session.get(ACTUATOR_ID)
    detector = session.get(DETECTOR_ID)
    position_key = next(iter(actuator.schema.readable.keys()))
    value_key = next(iter(detector.schema.readable.keys()))

    positions: list[float] = []
    values: list[float] = []
    total = len(POSITIONS)
    await detector.stage()
    try:
        for target in POSITIONS:
            actual = await move_and_settle(actuator, {position_key: target}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
            positions.append(float(actual[position_key]))

            data = await detector.read()
            values.append(float(data[value_key]))
            await session.report_progress({
                "positions": positions,
                "values": values,
                "completed": len(positions),
                "total": total,
            })
    finally:
        await detector.unstage()

    return {
        "actuator": ACTUATOR_ID,
        "detector": DETECTOR_ID,
        "positions": positions,  # positions[i] = actuator reading when values[i] was acquired
        "values": values,
    }
