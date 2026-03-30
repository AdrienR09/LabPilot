"""Lock-in amplifier X/Y waveform display.

This example shows real-time waveform monitoring with:
- Dual-channel X/Y signal display
- Rolling buffer for continuous monitoring
- Trigger level and time/div controls
- Signal statistics and RMS calculations

Use case: Monitoring lock-in amplifier signals, PID loops, or time-series data.
Devices: Works with lock-in amplifiers (SR830, SR860, Zurich Instruments, etc.)
"""

from labpilot_core.qt.dsl import *

# Create main window for waveform display
w = window("Lock-in X/Y Signals", layout="vertical")

# Real-time waveform plot with dual channels
w.add(waveform_plot(
    source="lockin.xy_data",
    n_samples=2000,
    channels=["X", "Y"],
    xlabel="Time (s)"
))

# Time base and trigger controls
w.add(row(
    slider(
        "Time/Div", "lockin", "time_constant",
        min=0.001, max=10.0, step=0.001
    ),
    slider(
        "Trigger Level", "lockin", "trigger_level",
        min=-1.0, max=1.0, step=0.01
    ),
    button("Auto Scale", "start", "lockin"),
    toggle("Freeze", "lockin", "freeze_display")
))

# Signal statistics
w.add(row(
    value_display(
        "X RMS", "lockin.x_rms",
        format="{:.4f}", unit="V"
    ),
    value_display(
        "Y RMS", "lockin.y_rms",
        format="{:.4f}", unit="V"
    ),
    value_display(
        "R", "lockin.magnitude",
        format="{:.4f}", unit="V"
    ),
    value_display(
        "θ", "lockin.phase",
        format="{:.1f}", unit="°"
    )
))

# Lock-in settings
w.add(row(
    dropdown("Sensitivity", "lockin", "sensitivity",
             ["1 mV", "2 mV", "5 mV", "10 mV", "20 mV", "50 mV", "100 mV"]),
    dropdown("Time Constant", "lockin", "time_constant",
             ["1 ms", "3 ms", "10 ms", "30 ms", "100 ms", "300 ms", "1 s"]),
    dropdown("Filter Slope", "lockin", "filter_slope",
             ["6 dB/oct", "12 dB/oct", "18 dB/oct", "24 dB/oct"])
))

# Display the window
show(w)
