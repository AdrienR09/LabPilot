"""Example: Simple 1D scan with mock devices.

This example demonstrates a complete scan workflow using mock devices.
Replace with real drivers for actual hardware.
"""

from __future__ import annotations

from typing import Any

import anyio
import numpy as np

from labpilot import Session
from labpilot.core.events import EventKind
from labpilot.device.schema import DeviceSchema
from labpilot.drivers._base import BaseDriver
from labpilot.plans import ScanPlan
from labpilot.plans.scan import scan


class MockMotor(BaseDriver):
    """Mock motor for demonstration."""

    schema = DeviceSchema(
        name="mock_motor",
        kind="motor",
        readable={"position": "float64"},
        settable={"position": "float64"},
        units={"position": "um"},
        limits={"position": (0.0, 100.0)},
        trigger_modes=["software"],
        tags=["demo", "mock"],
    )

    def __init__(self) -> None:
        """Initialize mock motor."""
        super().__init__()
        self._position = 0.0

    async def connect(self) -> None:
        """Connect to motor."""
        self._connected = True
        print("Motor connected")

    async def disconnect(self) -> None:
        """Disconnect from motor."""
        self._connected = False
        print("Motor disconnected")

    async def stage(self) -> None:
        """Stage motor."""
        print("Motor staged")

    async def unstage(self) -> None:
        """Unstage motor."""
        print("Motor unstaged")

    async def set(self, value: float, *, timeout: float = 10.0) -> None:
        """Move to position."""
        print(f"Motor moving to {value:.2f} µm")
        self._position = value
        await anyio.sleep(0.05)  # Simulate motion time

    async def stop(self) -> None:
        """Stop motion."""
        pass

    async def where(self) -> float:
        """Get position."""
        return self._position

    async def read(self) -> dict[str, Any]:
        """Read position."""
        return {"position": self._position}


class MockDetector(BaseDriver):
    """Mock detector for demonstration."""

    schema = DeviceSchema(
        name="mock_detector",
        kind="detector",
        readable={"intensity": "float64", "temperature": "float64"},
        settable={},
        units={"intensity": "counts", "temperature": "K"},
        limits={},
        trigger_modes=["software"],
        tags=["demo", "mock"],
    )

    async def connect(self) -> None:
        """Connect to detector."""
        self._connected = True
        print("Detector connected")

    async def disconnect(self) -> None:
        """Disconnect from detector."""
        self._connected = False
        print("Detector disconnected")

    async def stage(self) -> None:
        """Stage detector."""
        print("Detector staged")

    async def unstage(self) -> None:
        """Unstage detector."""
        print("Detector unstaged")

    async def read(self) -> dict[str, Any]:
        """Read detector (simulated Gaussian peak)."""
        # Simulate a Gaussian peak centered at 50 µm
        position = np.random.uniform(0, 100)
        intensity = 1000 * np.exp(-((position - 50) ** 2) / (2 * 10**2))
        intensity += np.random.normal(0, 50)  # Add noise

        return {
            "intensity": max(0, intensity),
            "temperature": 295.0 + np.random.normal(0, 0.1),
        }


async def main() -> None:
    """Run example scan."""
    print("=" * 60)
    print("LabPilot Example: 1D Scan with Mock Devices")
    print("=" * 60)
    print()

    # Create session
    session = Session()

    # Create and connect devices
    motor = MockMotor()
    detector = MockDetector()

    await motor.connect()
    await detector.connect()

    # Register devices
    session.register(motor)
    session.register(detector)

    print()
    print("Devices registered:")
    for name in session.devices:
        print(f"  - {name}")
    print()

    # Create scan plan
    plan = ScanPlan(
        name="example_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=20.0,
        stop=80.0,
        num=20,
        dwell=0.05,
        metadata={
            "sample": "demo_sample",
            "user": "scientist",
            "experiment": "peak_finding",
        },
    )

    print("Scan plan:")
    print(f"  Name: {plan.name}")
    print(f"  Motor: {plan.motor}")
    print(f"  Detector: {plan.detector}")
    print(f"  Range: {plan.start} to {plan.stop} {motor.schema.units['position']}")
    print(f"  Points: {plan.num}")
    print(f"  Dwell: {plan.dwell} s")
    print()

    # Save plan
    plan.to_toml("example_scan.toml")
    print("Scan plan saved to: example_scan.toml")
    print()

    # Run scan with live output
    print("Starting scan...")
    print("-" * 60)

    max_intensity = 0.0
    max_position = 0.0

    async for event in scan(plan, motor, detector, session.bus):
        if event.kind == EventKind.READING:
            pos = event.data["motor_position"]
            intensity = event.data["intensity"]
            temp = event.data["temperature"]

            print(
                f"Point {event.data['point_index']:2d}: "
                f"pos={pos:5.1f} µm, "
                f"intensity={intensity:7.1f} counts, "
                f"temp={temp:.2f} K"
            )

            if intensity > max_intensity:
                max_intensity = intensity
                max_position = pos

        elif event.kind == EventKind.PROGRESS:
            fraction = event.data["fraction"]
            eta = event.data["eta_seconds"]
            if event.data["point_index"] % 5 == 0:  # Print every 5 points
                print(f"  Progress: {fraction*100:.0f}%, ETA: {eta:.1f}s")

        elif event.kind == EventKind.STOP:
            print("-" * 60)
            print("Scan completed successfully!")

    print()
    print("Results:")
    print(f"  Maximum intensity: {max_intensity:.1f} counts")
    print(f"  Peak position: {max_position:.1f} µm")
    print()

    # Clean up
    await motor.disconnect()
    await detector.disconnect()

    print("=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    anyio.run(main)
