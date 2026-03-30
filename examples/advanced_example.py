"""Advanced example: Multiple event subscribers for storage and live plotting.

This shows how to use the EventBus to have multiple consumers:
- Main script (for console output)
- HDF5 writer (for data storage)
- Future: GUI live plotting
- Future: Remote monitoring
"""

import anyio
from labpilot import Session
from labpilot.core.events import EventKind
from labpilot.plans import ScanPlan
from labpilot.plans.scan import scan
from labpilot.storage.hdf5 import HDF5Writer
from labpilot.storage.catalogue import Catalogue

# Using mock devices for demo
from examples.simple_scan import MockMotor, MockDetector


async def main() -> None:
    """Run scan with parallel data storage and live output."""

    print("=" * 70)
    print("Advanced Example: Parallel Event Subscribers")
    print("=" * 70)
    print()

    # Create session
    session = Session()

    # Connect devices
    motor = MockMotor()
    detector = MockDetector()
    await motor.connect()
    await detector.connect()
    session.register(motor)
    session.register(detector)

    # Create scan plan
    plan = ScanPlan(
        name="advanced_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=100.0,
        num=50,
        dwell=0.05,
        metadata={
            "sample": "advanced_sample",
            "user": "scientist",
            "experiment": "parallel_processing_demo",
        }
    )

    print("✓ Scan configured:")
    print(f"  • Name: {plan.name}")
    print(f"  • Points: {plan.num}")
    print(f"  • Expected duration: ~{plan.num * plan.dwell:.1f}s")
    print()

    # ========================================
    # Setup parallel subscribers
    # ========================================

    # 1. HDF5 Writer - saves data to file in real-time
    hdf5_writer = HDF5Writer(
        path="data/advanced_scan.h5",
        compression="gzip",
        chunk_size=10
    )

    # 2. Catalogue - indexes metadata in SQLite
    catalogue = Catalogue("data/catalogue.db")
    await catalogue.connect()

    print("✓ Data storage configured:")
    print(f"  • HDF5: data/advanced_scan.h5")
    print(f"  • Catalogue: data/catalogue.db")
    print()

    # ========================================
    # Run scan with multiple subscribers
    # ========================================

    print("Starting scan...")
    print("-" * 70)

    # This task group runs everything in parallel
    async with anyio.create_task_group() as tg:
        # Start HDF5 writer in background
        async def run_hdf5_writer() -> None:
            """Subscribe to events and write to HDF5."""
            await hdf5_writer.start(session.bus)

        tg.start_soon(run_hdf5_writer)

        # Wait a moment for writer to start
        await anyio.sleep(0.1)

        # Main scan loop
        run_uid = None
        point_count = 0

        async for event in scan(plan, motor, detector, session.bus):

            if event.kind == EventKind.DESCRIPTOR:
                run_uid = event.run_uid
                print(f"Run UID: {run_uid}")
                print("-" * 70)

            elif event.kind == EventKind.READING:
                point_count += 1
                pos = event.data["motor_position"]
                intensity = event.data["intensity"]

                # Live console output (every 10 points)
                if point_count % 10 == 0:
                    print(f"Point {point_count:2d}: pos={pos:6.2f}, "
                          f"intensity={intensity:7.1f}")

            elif event.kind == EventKind.STOP:
                print("-" * 70)
                print("✓ Scan completed!")
                break

        # Stop HDF5 writer
        await hdf5_writer.stop()

        # Add to catalogue
        if run_uid:
            await catalogue.add_run(
                run_uid=run_uid,
                plan_name=plan.name,
                metadata=plan.metadata,
                data_path="data/advanced_scan.h5"
            )

    print()
    print("✓ Data saved and indexed")
    print()

    # ========================================
    # Query the catalogue
    # ========================================
    print("Querying catalogue...")
    results = await catalogue.search(limit=5)

    print(f"Found {len(results)} scans in catalogue:")
    for result in results:
        print(f"  • {result['run_uid'][:8]}... - {result['plan_name']}")
        print(f"    Sample: {result['metadata'].get('sample', 'unknown')}")
        print(f"    User: {result['metadata'].get('user', 'unknown')}")

    print()

    # Cleanup
    await catalogue.disconnect()
    await motor.disconnect()
    await detector.disconnect()

    print("=" * 70)
    print("Advanced example complete!")
    print()
    print("Next steps:")
    print("  1. Examine: data/advanced_scan.h5 (HDF5 data file)")
    print("  2. Query: data/catalogue.db (SQLite metadata)")
    print("  3. Add: Live plotting subscriber (matplotlib/plotly)")
    print("  4. Add: Remote GUI subscriber (ZMQ bridge)")
    print("=" * 70)


if __name__ == "__main__":
    anyio.run(main)
