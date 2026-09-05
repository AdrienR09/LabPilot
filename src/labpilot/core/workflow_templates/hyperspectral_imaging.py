"""Hyperspectral imaging scan.

Rasters a 2D scanner over an (x, y) grid and acquires a full spectrum at
every position, combining a 2D actuator with a spectrometer to build a
hyperspectral data cube (two spatial dimensions + one spectral dimension).

References its instruments by *role*, not a specific instrument id — bind
"scanner" and "spectrometer" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from labpilot.core.session import Session
from labpilot.core.workflow_templates._common import (
    integration_time_key,
    move_and_settle,
    spectrum_key,
)

REQUIRED_INSTRUMENTS = {
    "scanner": {"kind": "motor", "dimensionality": "ND"},
    "spectrometer": {"kind": "detector", "dimensionality": "1D"},
}
SCANNER_ID = "scanner"
SPECTROMETER_ID = "spectrometer"

# Read by the native desktop window (workflow_window.py) to render a live
# image that fills in as the scan runs. Unlike the final "cube" (a full
# spectrum per pixel — 5x5x4096 floats by default, too heavy to re-send on
# every pixel), the live view is a per-pixel scalar (spectrum sum) reported
# under a separate "live_image" key — see session.report_progress() below.
RESULT_UI = {
    "type": "image2d",
    "value_key": "live_image",
    "x_key": "x_positions_mm",
    "y_key": "y_positions_mm",
    "value_label": "Total counts (live)",
}

# Grid extent and resolution (mm) — kept modest by default so a full scan
# finishes quickly; widen/densify for a real acquisition.
X_POSITIONS = [-4.0, -2.0, 0.0, 2.0, 4.0]
Y_POSITIONS = [-4.0, -2.0, 0.0, 2.0, 4.0]

INTEGRATION_TIME_MS = 50.0

# How close (mm) counts as "arrived", and a safety cap on settle-wait
# polls per pixel so a scanner that never reaches the target (misconfigured
# hardware, or a target outside its travel range) fails loudly instead of
# hanging the workflow forever.
SETTLE_TOLERANCE_MM = 0.02
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    scanner = session.get(SCANNER_ID)
    spectrometer = session.get(SPECTROMETER_ID)

    it_key = integration_time_key(spectrometer)
    if it_key:
        await spectrometer.write({it_key: INTEGRATION_TIME_MS})
    value_key = spectrum_key(spectrometer)

    # Pre-allocated (not built via row-append) so both the cube and its
    # live-progress summary are a well-formed 2D/3D shape at every point
    # during the scan, not just at the end.
    cube: list[list[list[float] | None]] = [[None] * len(Y_POSITIONS) for _ in X_POSITIONS]
    live_image: list[list[float | None]] = [[None] * len(Y_POSITIONS) for _ in X_POSITIONS]
    total = len(X_POSITIONS) * len(Y_POSITIONS)
    completed = 0
    await spectrometer.stage()
    try:
        for i, x in enumerate(X_POSITIONS):
            for j, y in enumerate(Y_POSITIONS):
                await move_and_settle(scanner, {"x": x, "y": y}, SETTLE_TOLERANCE_MM, MAX_SETTLE_POLLS)

                spectrum = await spectrometer.read()
                pixel = list(spectrum[value_key])
                cube[i][j] = pixel
                live_image[i][j] = float(sum(pixel))
                completed += 1
                await session.report_progress({
                    "live_image": live_image,
                    "x_positions_mm": X_POSITIONS,
                    "y_positions_mm": Y_POSITIONS,
                    "completed": completed,
                    "total": total,
                })
    finally:
        await spectrometer.unstage()

    return {
        "scanner": SCANNER_ID,
        "spectrometer": SPECTROMETER_ID,
        "x_positions_mm": X_POSITIONS,
        "y_positions_mm": Y_POSITIONS,
        "cube_shape": [len(X_POSITIONS), len(Y_POSITIONS), len(cube[0][0]) if cube and cube[0] else 0],
        "cube": cube,  # cube[i][j] = spectrum acquired at (X_POSITIONS[i], Y_POSITIONS[j])
    }
