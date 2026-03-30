"""Temperature monitoring and control panel.

This example shows environmental monitoring with:
- Real-time temperature trend plot
- Multi-zone temperature display
- PID control parameters
- Alarm thresholds and alerts

Use case: Sample temperature control, environmental chambers, cryostat monitoring.
Devices: Temperature controllers (Lakeshore, ITC, custom PID controllers).
"""

from labpilot_core.qt.dsl import *

# Create temperature monitoring window
w = window("Temperature Control", layout="vertical")

# Temperature trend plot
w.add(waveform_plot(
    source="controller.temperature_history",
    n_samples=1000,
    channels=["Sample", "Setpoint", "Ambient"],
    xlabel="Time (min)"
))

# Current temperatures display
w.add(row(
    value_display(
        "Sample Temp", "controller.sample_temperature",
        format="{:.2f}", unit="K"
    ),
    value_display(
        "Setpoint", "controller.setpoint",
        format="{:.2f}", unit="K"
    ),
    value_display(
        "Heater Power", "controller.heater_power",
        format="{:.1f}", unit="%"
    ),
    value_display(
        "Stability", "controller.stability",
        format="{:.3f}", unit="K"
    )
))

# Control parameters
w.add(row(
    slider(
        "Setpoint", "controller", "setpoint",
        min=4.0, max=300.0, step=0.1
    ),
    slider(
        "P Gain", "controller", "p_gain",
        min=0.0, max=1000.0, step=1.0
    ),
    slider(
        "I Time", "controller", "i_time",
        min=0.0, max=1000.0, step=1.0
    ),
    slider(
        "D Time", "controller", "d_time",
        min=0.0, max=100.0, step=1.0
    )
))

# Status and controls
w.add(row(
    toggle("PID Control", "controller", "control_enabled"),
    toggle("Auto Tune", "controller", "auto_tune"),
    button("Ramp to SP", "start", "controller"),
    dropdown("Ramp Rate", "controller", "ramp_rate",
             ["0.1 K/min", "0.5 K/min", "1 K/min", "5 K/min", "10 K/min"])
))

# Alarm status
w.add(row(
    text_display("Status", "controller.status"),
    value_display(
        "Time to SP", "controller.time_to_setpoint",
        format="{:.1f}", unit="min"
    ),
    toggle("High Alarm", "controller", "high_alarm_active"),
    toggle("Low Alarm", "controller", "low_alarm_active")
))

# Display the window
show(w)
