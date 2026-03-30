"""Live camera view with ROI analysis and controls.

This example shows a complete camera control panel with:
- Real-time image display with false color
- ROI (Region of Interest) selection and statistics
- Exposure time and gain controls
- Temperature monitoring for cooled cameras

Use case: Live imaging for alignment, focusing, or monitoring experiments.
Devices: Works with any camera adapter (Andor, Hamamatsu, Thorlabs, etc.)
"""

from labpilot_core.qt.dsl import *

# Create main window
w = window("Live Camera View", layout="vertical")

# Main image display with histogram and ROI
w.add(image_view(
    source="camera.frame",
    colormap="inferno",
    show_histogram=True,
    show_roi=True
))

# Camera controls (exposure, gain, temperature)
w.add(row(
    slider(
        "Exposure", "camera", "exposure_ms",
        min=0.1, max=5000, step=0.1
    ),
    slider(
        "Gain", "camera", "gain",
        min=1, max=100, step=1
    ),
    value_display(
        "Temperature", "camera.temperature",
        format="{:.1f}", unit="°C"
    )
))

# ROI statistics display
w.add(row(
    value_display(
        "ROI Mean", "camera.roi_mean",
        format="{:.1f}", unit="counts"
    ),
    value_display(
        "ROI Max", "camera.roi_max",
        format="{:.0f}", unit="counts"
    ),
    value_display(
        "ROI Std", "camera.roi_std",
        format="{:.2f}", unit="counts"
    )
))

# Action buttons and mode controls
w.add(row(
    button("Snap", "trigger", "camera"),
    button("Start Live", "start", "camera"),
    button("Stop", "stop", "camera"),
    toggle("Cooling", "camera", "cooling_enabled"),
    dropdown("Binning", "camera", "binning", ["1x1", "2x2", "4x4"])
))

# Display the window
show(w)
