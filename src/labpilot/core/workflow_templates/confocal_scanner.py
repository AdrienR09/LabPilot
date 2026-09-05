"""Confocal scanner.

Rasters an XY actuator over a 2D grid and records a 0D detector's reading
at every pixel, building a 2D intensity image — the standard confocal
microscopy acquisition pattern (a point detector + a raster-scanned
focal spot).

References its instruments by *role*, not a specific instrument id — bind
"xy_actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from labpilot.core.session import Session
from labpilot.core.workflow_templates._common import move_and_settle

REQUIRED_INSTRUMENTS = {
    "xy_actuator": {"kind": "motor", "dimensionality": "ND"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
SCANNER_ID = "xy_actuator"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live,
# qudi-style image view that fills in as the scan runs — see
# session.report_progress() calls below and core/workflow/instrument_roles.py.
RESULT_UI = {
    "type": "image2d",
    "value_key": "image",
    "x_key": "x_positions_mm",
    "y_key": "y_positions_mm",
    "value_label": "Counts",
    # Opt-in: draws a crosshair on the image tracking the bound role's live
    # (x_axis, y_axis) position, and clicking the image moves it there —
    # the qudi-style confocal-scanner behavior. Only meaningful for a
    # workflow whose scan axes are also its actual live 2D position (skip
    # this key for templates where that's not true, e.g. grating_spectrometer).
    "crosshair": {"role": "xy_actuator", "x_axis": "x", "y_axis": "y"},
}

# Grid extent and resolution (mm) — kept modest by default so a full scan
# finishes quickly; widen/densify for a real acquisition.
X_POSITIONS = [-4.0, -2.0, 0.0, 2.0, 4.0]
Y_POSITIONS = [-4.0, -2.0, 0.0, 2.0, 4.0]

# How close (mm) counts as "arrived", and a safety cap on settle-wait
# polls per pixel so a scanner that never reaches the target (misconfigured
# hardware, or a target outside its travel range) fails loudly instead of
# hanging the workflow forever.
SETTLE_TOLERANCE_MM = 0.02
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    scanner = session.get(SCANNER_ID)
    detector = session.get(DETECTOR_ID)
    value_key = next(iter(detector.schema.readable.keys()))

    # Pre-allocated (not built via row-append) so the grid is always a
    # well-formed 2D shape at every point during the scan, not just at the
    # end — report_progress() below sends this same array on every pixel.
    image: list[list[float | None]] = [[None] * len(Y_POSITIONS) for _ in X_POSITIONS]
    total = len(X_POSITIONS) * len(Y_POSITIONS)
    completed = 0
    await detector.stage()
    try:
        for i, x in enumerate(X_POSITIONS):
            for j, y in enumerate(Y_POSITIONS):
                await move_and_settle(scanner, {"x": x, "y": y}, SETTLE_TOLERANCE_MM, MAX_SETTLE_POLLS)

                data = await detector.read()
                image[i][j] = float(data[value_key])
                completed += 1
                await session.report_progress({
                    "image": image,
                    "x_positions_mm": X_POSITIONS,
                    "y_positions_mm": Y_POSITIONS,
                    "completed": completed,
                    "total": total,
                })
    finally:
        await detector.unstage()

    return {
        "scanner": SCANNER_ID,
        "detector": DETECTOR_ID,
        "x_positions_mm": X_POSITIONS,
        "y_positions_mm": Y_POSITIONS,
        "image_shape": [len(X_POSITIONS), len(Y_POSITIONS)],
        "image": image,  # image[i][j] = detector reading at (X_POSITIONS[i], Y_POSITIONS[j])
    }
