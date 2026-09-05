"""Grating spectrometer scan.

Steps a grating-position actuator through a series of positions and, at
each one, reads a 2D camera and collapses it to a 1D intensity trace
(summed over the spatial axis), converting camera pixel column to
wavelength via a linear grating calibration and stitching each step's
window into one broadband spectrum — the standard technique for covering
more spectral range than a single camera frame captures at one grating
position (a CCD + rotating grating spectrometer).

References its instruments by *role*, not a specific instrument id — bind
"grating_actuator" and "camera" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

import numpy as np

from labpilot.core.session import Session
from labpilot.core.workflow_templates._common import move_and_settle

REQUIRED_INSTRUMENTS = {
    "grating_actuator": {"kind": "motor", "dimensionality": "1D"},
    "camera": {"kind": "detector", "dimensionality": "2D"},
}
GRATING_ID = "grating_actuator"
CAMERA_ID = "camera"

# Read by the native desktop window (workflow_window.py) to render a live
# spectrum view that grows as each grating position is stitched in — see
# session.report_progress() calls below and core/workflow/instrument_roles.py.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "wavelengths_nm",
    "y_key": "spectrum",
    "x_label": "Wavelength (nm)",
    "y_label": "Intensity",
}

# Grating positions (degrees, or whatever unit the real actuator reports)
# to step through — each one centers a different wavelength window on
# the camera.
GRATING_POSITIONS = [0.0, 5.0, 10.0, 15.0]

# Linear pixel-column -> wavelength calibration. Replace with your
# spectrometer's real calibration (from a known reference source) before
# using this for anything but a mock/simulated camera.
GRATING_SLOPE_NM_PER_POS = 20.0   # nm shift in the window's center per unit of grating motion
GRATING_INTERCEPT_NM = 500.0      # window center wavelength at position 0
PIXEL_DISPERSION_NM = 0.05        # nm per camera pixel column, around the window center

# How close counts as "arrived", and a safety cap on settle-wait polls per
# position so a grating that never settles (misconfigured hardware, or a
# target outside its travel range) fails loudly instead of hanging the
# workflow forever.
SETTLE_TOLERANCE = 0.05
MAX_SETTLE_POLLS = 5000


async def run(session: Session) -> dict:
    grating = session.get(GRATING_ID)
    camera = session.get(CAMERA_ID)
    position_key = next(iter(grating.schema.readable.keys()))
    image_key = next(iter(camera.schema.readable.keys()))

    stitched: dict[float, float] = {}  # wavelength_nm -> intensity, last write wins on overlap
    total = len(GRATING_POSITIONS)
    await camera.stage()
    try:
        for step, position in enumerate(GRATING_POSITIONS):
            await move_and_settle(grating, {position_key: position}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)

            frame = await camera.read()
            image = np.asarray(frame[image_key], dtype=float)
            trace = image.sum(axis=0)  # collapse the spatial axis -> one intensity value per column

            center_nm = GRATING_SLOPE_NM_PER_POS * position + GRATING_INTERCEPT_NM
            n = len(trace)
            wavelengths = center_nm + PIXEL_DISPERSION_NM * (np.arange(n) - n / 2)
            for wl, value in zip(wavelengths, trace):
                stitched[float(wl)] = float(value)

            wavelengths_so_far = sorted(stitched)
            await session.report_progress({
                "wavelengths_nm": wavelengths_so_far,
                "spectrum": [stitched[wl] for wl in wavelengths_so_far],
                "completed": step + 1,
                "total": total,
            })
    finally:
        await camera.unstage()

    wavelengths_sorted = sorted(stitched)
    return {
        "grating_actuator": GRATING_ID,
        "camera": CAMERA_ID,
        "grating_positions": GRATING_POSITIONS,
        "wavelengths_nm": wavelengths_sorted,
        "spectrum": [stitched[wl] for wl in wavelengths_sorted],
    }
