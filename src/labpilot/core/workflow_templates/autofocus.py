"""Autofocus.

Steps a Z actuator through a range of positions, records a 0D detector's
reading at each one, fits a single peak to find the position of maximum
signal (core/analysis/fits.py's `fit_peak`), and moves the actuator there
— the standard confocal-microscopy autofocus routine (pyMoDAQ's and
qudi's equivalents both follow this same scan-fit-move pattern).

References its instruments by *role*, not a specific instrument id — bind
"z_actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from labpilot.core.analysis.fits import fit_peak
from labpilot.core.session import Session
from labpilot.core.workflow_templates._common import move_and_settle

REQUIRED_INSTRUMENTS = {
    "z_actuator": {"kind": "motor", "dimensionality": "1D"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
Z_ID = "z_actuator"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live
# curve that grows as the Z-scan runs — see session.report_progress()
# below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "z_positions",
    "y_key": "values",
    "x_label": "Z position",
    "y_label": "Detector reading",
}

# Z positions to visit, in order — units are whatever the bound actuator's
# own schema reports.
Z_POSITIONS = [-5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0]

FIT_SHAPE = "gaussian"

SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    z_actuator = session.get(Z_ID)
    detector = session.get(DETECTOR_ID)
    z_key = next(iter(z_actuator.schema.readable.keys()))
    value_key = next(iter(detector.schema.readable.keys()))

    z_positions: list[float] = []
    values: list[float] = []
    total = len(Z_POSITIONS)
    await detector.stage()
    try:
        for target in Z_POSITIONS:
            actual = await move_and_settle(z_actuator, {z_key: target}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
            z_positions.append(float(actual[z_key]))

            data = await detector.read()
            values.append(float(data[value_key]))
            await session.report_progress({
                "z_positions": z_positions,
                "values": values,
                "completed": len(z_positions),
                "total": total,
            })
    finally:
        await detector.unstage()

    fit = fit_peak(z_positions, values, FIT_SHAPE)
    best_z = fit["center"] if fit is not None else z_positions[values.index(max(values))]
    await move_and_settle(z_actuator, {z_key: best_z}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)

    return {
        "z_actuator": Z_ID,
        "detector": DETECTOR_ID,
        "z_positions": z_positions,
        "values": values,
        "fit": fit,  # {center, amplitude, fwhm, baseline}, or None if the fit didn't converge
        "best_z": best_z,  # fit center, or (if the fit failed) the best-observed sample position
    }
