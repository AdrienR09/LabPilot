"""Generic 2D scan.

Rasters any XY-capable actuator over a 2D grid and records any 0D
detector's reading at every pixel, building a 2D image — pyMoDAQ's
`DAQ_Scan` module generalized to its 2D case (any actuator + any 0D
detector), not confocal-microscopy-specific the way confocal_scanner.py is
(no crosshair, no assumption the scanned axes are a live focal-spot
position).

References its instruments by *role*, not a specific instrument id — bind
"actuator" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from core.session import Session
from core.workflow_templates._common import move_and_settle

REQUIRED_INSTRUMENTS = {
    "actuator": {"kind": "motor", "dimensionality": "ND"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
ACTUATOR_ID = "actuator"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live,
# qudi-style image view that fills in as the scan runs — see
# session.report_progress() calls below.
RESULT_UI = {
    "type": "image2d",
    "value_key": "image",
    "x_key": "x_positions",
    "y_key": "y_positions",
    "value_label": "Detector reading",
    # Draws a draggable qudi-scanner-style crosshair on the image, tracking
    # the bound actuator's live (x_axis, y_axis) position; dragging it (or
    # clicking anywhere on the image) moves the actuator there. Meaningful
    # here since this template's scanned axes ARE the actuator's real live
    # 2D position (unlike e.g. grating_spectrometer's image, which doesn't
    # get one).
    "crosshair": {"role": "actuator", "x_axis": "x", "y_axis": "y"},
}

# Grid extent and resolution — units are whatever the bound actuator's own
# schema reports for its "x"/"y" axes. Kept modest by default so a full
# scan finishes quickly; widen/densify for a real acquisition.
X_POSITIONS = [-4.0, -2.0, 0.0, 2.0, 4.0]
Y_POSITIONS = [-4.0, -2.0, 0.0, 2.0, 4.0]

# How close counts as "arrived", and a safety cap on settle-wait polls per
# pixel so an actuator that never reaches the target (misconfigured
# hardware, or a target outside its travel range) fails loudly instead of
# hanging the workflow forever.
SETTLE_TOLERANCE = 0.02
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    actuator = session.get(ACTUATOR_ID)
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
                await move_and_settle(actuator, {"x": x, "y": y}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)

                data = await detector.read()
                image[i][j] = float(data[value_key])
                completed += 1
                await session.report_progress({
                    "image": image,
                    "x_positions": X_POSITIONS,
                    "y_positions": Y_POSITIONS,
                    "completed": completed,
                    "total": total,
                })
    finally:
        await detector.unstage()

    return {
        "actuator": ACTUATOR_ID,
        "detector": DETECTOR_ID,
        "x_positions": X_POSITIONS,
        "y_positions": Y_POSITIONS,
        "image_shape": [len(X_POSITIONS), len(Y_POSITIONS)],
        "image": image,  # image[i][j] = detector reading at (X_POSITIONS[i], Y_POSITIONS[j])
    }
