"""Pump-probe spectroscopy scan.

Acquires a full spectrum at each of a series of pump-probe delays,
combining a 1D delay stage with a spectrometer. The stage's linear
position stands in for optical delay (a real double-pass delay line
converts stage travel to delay via delay_s = 2 * distance_m / c —
substitute that conversion here if you need real time units instead of
raw stage position).

References its instruments by *role*, not a specific instrument id — bind
"delay_stage" and "spectrometer" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from labpilot.core.session import Session
from labpilot.core.workflow_templates._common import (
    integration_time_key,
    move_and_settle_by_moving_flag,
    spectrum_key,
)

REQUIRED_INSTRUMENTS = {
    "delay_stage": {"kind": "motor", "dimensionality": "1D"},
    "spectrometer": {"kind": "detector", "dimensionality": "1D"},
}
STAGE_ID = "delay_stage"
SPECTROMETER_ID = "spectrometer"

# Read by the native desktop window (workflow_window.py) to render a live
# image (delay x wavelength) that grows one row at a time as the scan runs
# — see session.report_progress() calls below.
RESULT_UI = {
    "type": "image2d",
    "value_key": "spectra",
    "x_key": "delay_positions_mm",
    "value_label": "Intensity",
    "x_label": "Delay (mm)",
    "y_label": "Wavelength index",
}

# Stage positions (mm) to visit, in order — the "delay axis" of the scan.
DELAY_POSITIONS_MM = [30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0]

INTEGRATION_TIME_MS = 50.0

# Safety cap on settle-wait polls per delay, so a stage that never reports
# moving=False (misconfigured/broken hardware) fails loudly instead of
# hanging the workflow forever.
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    stage = session.get(STAGE_ID)
    spectrometer = session.get(SPECTROMETER_ID)

    it_key = integration_time_key(spectrometer)
    if it_key:
        await spectrometer.write({it_key: INTEGRATION_TIME_MS})
    value_key = spectrum_key(spectrometer)

    spectra: list[list[float]] = []
    actual_positions_mm: list[float] = []
    total = len(DELAY_POSITIONS_MM)
    await spectrometer.stage()
    try:
        for delay_mm in DELAY_POSITIONS_MM:
            settled = await move_and_settle_by_moving_flag(stage, {"position": delay_mm}, max_polls=MAX_SETTLE_POLLS)
            actual_positions_mm.append(settled["position"])

            spectrum = await spectrometer.read()
            spectra.append(list(spectrum[value_key]))
            await session.report_progress({
                "spectra": spectra,
                "delay_positions_mm": actual_positions_mm,
                "completed": len(actual_positions_mm),
                "total": total,
            })
    finally:
        await spectrometer.unstage()

    return {
        "stage": STAGE_ID,
        "spectrometer": SPECTROMETER_ID,
        "delay_positions_mm": actual_positions_mm,
        "spectra": spectra,  # spectra[i] = spectrum acquired at delay_positions_mm[i]
    }
