"""Complete laser spectroscopy control panel.

This example shows a complex multi-instrument panel with:
- Tabbed interface for different instrument groups
- Laser control with wavelength and power
- Spectrometer monitoring with peak tracking
- Stage positioning for sample alignment
- Integrated workflow controls

Use case: Complete control panel for laser spectroscopy experiments.
Devices: Tunable laser, spectrometer, XY stage, power meter.
"""

from labpilot_core.qt.dsl import *

# Create main window with tabbed layout
w = window("Laser Spectroscopy Control", layout="vertical")

# Create tabbed interface for different instrument groups
w.add(tabs(
    # Laser Control Tab
    Laser=column(
        row(
            slider(
                "Wavelength", "laser", "wavelength_nm",
                min=400, max=1000, step=0.1
            ),
            slider(
                "Power", "laser", "power_percent",
                min=0, max=100, step=1
            )
        ),
        row(
            value_display(
                "Current λ", "laser.current_wavelength",
                format="{:.2f}", unit="nm"
            ),
            value_display(
                "Output Power", "laser.output_power",
                format="{:.1f}", unit="mW"
            ),
            value_display(
                "Temperature", "laser.temperature",
                format="{:.1f}", unit="°C"
            )
        ),
        row(
            toggle("Output Enable", "laser", "output_enabled"),
            button("Tune", "start", "laser"),
            button("Emergency Stop", "stop", "laser")
        )
    ),

    # Spectrometer Tab
    Spectrometer=column(
        spectrum_plot(
            source="spectrometer.spectrum",
            xlabel="Wavelength (nm)",
            ylabel="Intensity (counts)",
            show_peak=True
        ),
        row(
            slider(
                "Integration", "spectrometer", "integration_time_ms",
                min=1, max=10000, step=1
            ),
            value_display(
                "Peak λ", "spectrometer.peak_wavelength",
                format="{:.2f}", unit="nm"
            ),
            value_display(
                "Peak Int.", "spectrometer.peak_intensity",
                format="{:.0f}", unit="counts"
            )
        )
    ),

    # Stage Control Tab
    Stage=column(
        row(
            slider(
                "X Position", "stage", "x_position",
                min=-50, max=50, step=0.1
            ),
            slider(
                "Y Position", "stage", "y_position",
                min=-50, max=50, step=0.1
            )
        ),
        row(
            value_display(
                "X", "stage.x_position",
                format="{:.3f}", unit="mm"
            ),
            value_display(
                "Y", "stage.y_position",
                format="{:.3f}", unit="mm"
            ),
            button("Home", "zero", "stage"),
            button("Stop", "stop", "stage")
        )
    ),

    # Monitoring Tab
    Monitor=column(
        scatter_plot(
            x_source="laser.wavelength_nm",
            y_source="spectrometer.peak_intensity",
            xlabel="Laser Wavelength (nm)",
            ylabel="Signal Intensity (counts)"
        ),
        row(
            value_display(
                "Scan Progress", "workflow.progress",
                format="{:.1f}", unit="%"
            ),
            text_display("Status", "workflow.status"),
            button("Start Scan", "start", "workflow"),
            button("Pause", "stop", "workflow")
        )
    )
))

# Global status bar
w.add(row(
    text_display("System Status", "system.status"),
    value_display(
        "Elapsed Time", "workflow.elapsed_time",
        format="{:.1f}", unit="s"
    ),
    button("Save Data", "trigger", "system"),
    toggle("Auto Save", "system", "auto_save_enabled")
))

# Display the window
show(w)
