"""Live spectrum display with peak finding and controls.

This example shows a complete spectrometer control panel with:
- Real-time spectrum plot with peak detection
- Integration time control via slider
- Peak position and intensity displays
- Auto-scale and trigger controls

Use case: Real-time monitoring of laser spectra, fluorescence, or Raman signals.
Devices: Works with any spectrometer adapter (Ocean Insight, Andor, etc.)
"""

from labpilot_core.qt.dsl import *

# Create main window with vertical layout
w = window("Live Spectrometer", layout="vertical")

# Main spectrum plot with peak finding enabled
w.add(spectrum_plot(
    source="spectrometer.intensities",
    xlabel="Wavelength (nm)",
    ylabel="Intensity (counts)",
    show_peak=True,
    log_y=False
))

# Control panel with integration time and displays
w.add(row(
    slider(
        "Integration Time", "spectrometer", "integration_time_ms",
        min=1, max=10000, step=1
    ),
    value_display(
        "Peak λ", "spectrometer.peak_wavelength",
        format="{:.2f}", unit="nm"
    ),
    value_display(
        "Peak Intensity", "spectrometer.peak_intensity",
        format="{:.0f}", unit="counts"
    )
))

# Action buttons
w.add(row(
    button("Acquire", "trigger", "spectrometer"),
    button("Auto Scale", "start", "spectrometer"),
    toggle("Continuous", "spectrometer", "continuous_mode")
))

# Display the window
show(w)
