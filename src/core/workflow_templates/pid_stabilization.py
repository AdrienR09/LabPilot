"""PID stabilization.

Continuously reads a 0D sensor and drives a settable source output (e.g. a
heater/TEC setpoint, a laser current) with a simple PID controller to hold
the sensor's reading at `SETPOINT` — pyMoDAQ's `DAQ_PID` extension pattern
(read error signal, compute a correction, write actuator, repeat).

References its instruments by *role*, not a specific instrument id — bind
"sensor" and "actuator" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

import asyncio
import time

from core.session import Session

REQUIRED_INSTRUMENTS = {
    "sensor": {"kind": "detector", "dimensionality": "0D"},
    "actuator": {"kind": "source", "dimensionality": "SOURCE"},
}
SENSOR_ID = "sensor"
ACTUATOR_ID = "actuator"

# Read by the native desktop window (workflow_window.py) to render a live
# curve of the sensor reading (with the setpoint as a reference) as
# stabilization runs — see session.report_progress() below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "times_s",
    "y_key": "sensor_values",
    "x_label": "Time (s)",
    "y_label": "Sensor reading",
}

SETPOINT = 25.0
KP = 1.0
KI = 0.1
KD = 0.0

DURATION_S = 20.0
DT_S = 0.2

# Actuator output is clamped to this range every tick — a real PID loop
# must never command an actuator outside its safe/settable range just
# because the raw PID math briefly overshoots.
OUTPUT_MIN = 0.0
OUTPUT_MAX = 100.0


async def run(session: Session) -> dict:
    sensor = session.get(SENSOR_ID)
    actuator = session.get(ACTUATOR_ID)
    sensor_key = next(iter(sensor.schema.readable.keys()))
    # The one settable, non-boolean key is the PID's output (a source's
    # other settable key, if any, is typically an on/off enable flag).
    output_key = next(k for k, dt in actuator.schema.settable.items() if dt != "bool")

    times_s: list[float] = []
    sensor_values: list[float] = []
    outputs: list[float] = []

    integral = 0.0
    previous_error = None
    total = max(1, int(DURATION_S / DT_S))
    start = time.monotonic()
    await sensor.stage()
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= DURATION_S:
                break

            data = await sensor.read()
            reading = float(data[sensor_key])
            error = SETPOINT - reading

            integral += error * DT_S
            derivative = 0.0 if previous_error is None else (error - previous_error) / DT_S
            previous_error = error

            output = KP * error + KI * integral + KD * derivative
            output = max(OUTPUT_MIN, min(OUTPUT_MAX, output))
            await actuator.write({output_key: output})

            times_s.append(elapsed)
            sensor_values.append(reading)
            outputs.append(output)
            await session.report_progress({
                "times_s": times_s,
                "sensor_values": sensor_values,
                "outputs": outputs,
                "setpoint": SETPOINT,
                "completed": len(times_s),
                "total": total,
            })

            next_tick_at = start + len(times_s) * DT_S
            remaining = next_tick_at - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
    finally:
        await sensor.unstage()

    return {
        "sensor": SENSOR_ID,
        "actuator": ACTUATOR_ID,
        "setpoint": SETPOINT,
        "times_s": times_s,
        "sensor_values": sensor_values,
        "outputs": outputs,
        "final_error": SETPOINT - sensor_values[-1] if sensor_values else None,
    }
