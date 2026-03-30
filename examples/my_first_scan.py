"""My first LabPilot scan - customize this for your hardware!"""

import anyio
from labpilot import Session
from labpilot.core.events import EventKind
from labpilot.plans import ScanPlan
from labpilot.plans.scan import scan

# Import your drivers here. Examples:
# from labpilot.drivers.visa.ocean_insight import OceanInsight
# from labpilot.drivers.ni.daq import NIAnalogInput, NIAnalogOutput
# from labpilot.drivers.serial._base import SerialDriver

# For now, let's use mock devices (replace with real ones)
from examples.simple_scan import MockMotor, MockDetector


async def main() -> None:
    """Run your custom scan."""

    # ========================================
    # 1. CREATE SESSION
    # ========================================
    session = Session()

    # ========================================
    # 2. CONNECT YOUR HARDWARE
    # ========================================
    # Replace these with your actual devices!

    # Example: Real VISA spectrometer
    # detector = OceanInsight(
    #     resource="USB0::0x2457::0x101E::1::INSTR",
    #     integration_time_ms=50.0
    # )

    # Example: Real NI DAQ
    # detector = NIAnalogInput(
    #     device="Dev1",
    #     channels="ai0:3",
    #     voltage_range=(-10.0, 10.0)
    # )

    # For now, using mock devices
    motor = MockMotor()
    detector = MockDetector()

    await motor.connect()
    await detector.connect()

    # ========================================
    # 3. REGISTER DEVICES IN SESSION
    # ========================================
    session.register(motor)
    session.register(detector)

    print("✓ Connected devices:")
    for name, device in session.devices.items():
        print(f"  • {name} ({device.schema.kind})")
    print()

    # ========================================
    # 4. CREATE SCAN PLAN
    # ========================================
    plan = ScanPlan(
        name="my_custom_scan",
        motor="mock_motor",        # Must match device schema name
        detector="mock_detector",   # Must match device schema name
        start=0.0,                  # Start position
        stop=50.0,                  # End position
        num=25,                     # Number of points
        dwell=0.1,                  # Dwell time per point (seconds)
        metadata={
            "sample": "my_sample_001",
            "user": "your_name",
            "temperature_K": 295,
            "notes": "Initial characterization",
        }
    )

    # ========================================
    # 5. RUN SCAN WITH LIVE DATA OUTPUT
    # ========================================
    print(f"Starting scan: {plan.name}")
    print(f"Range: {plan.start} → {plan.stop} (num={plan.num})")
    print("=" * 60)

    # Store data for post-processing
    positions = []
    intensities = []

    async for event in scan(plan, motor, detector, session.bus):

        # Handle different event types
        if event.kind == EventKind.DESCRIPTOR:
            # Scan starting - metadata available
            print(f"Run UID: {event.run_uid}")
            print("-" * 60)

        elif event.kind == EventKind.READING:
            # New data point acquired
            pos = event.data["motor_position"]
            intensity = event.data["intensity"]  # Adjust key for your detector

            positions.append(pos)
            intensities.append(intensity)

            # Live output
            print(f"Point {event.data['point_index']:2d}: "
                  f"pos={pos:6.2f} µm, intensity={intensity:8.1f}")

        elif event.kind == EventKind.PROGRESS:
            # Progress update
            frac = event.data["fraction"]
            eta = event.data["eta_seconds"]
            if event.data["point_index"] % 10 == 0:
                print(f"  → Progress: {frac*100:.0f}% (ETA: {eta:.1f}s)")

        elif event.kind == EventKind.STOP:
            # Scan finished
            print("-" * 60)
            print("✓ Scan completed!")

        elif event.kind == EventKind.ERROR:
            # Error occurred
            print(f"✗ Error: {event.data['error_message']}")

    # ========================================
    # 6. POST-PROCESSING
    # ========================================
    print()
    print("Results:")
    print(f"  • Points collected: {len(positions)}")
    print(f"  • Max intensity: {max(intensities):.1f}")
    print(f"  • Position at max: {positions[intensities.index(max(intensities))]:.2f} µm")
    print()

    # ========================================
    # 7. SAVE PLAN FOR REPRODUCIBILITY
    # ========================================
    plan.to_toml("my_custom_scan.toml")
    print(f"✓ Scan plan saved: my_custom_scan.toml")
    print()

    # ========================================
    # 8. CLEANUP
    # ========================================
    await motor.disconnect()
    await detector.disconnect()
    print("✓ Disconnected all devices")


if __name__ == "__main__":
    anyio.run(main)
