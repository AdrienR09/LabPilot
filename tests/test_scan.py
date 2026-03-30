"""Tests for scan execution with mock devices."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from labpilot.core.events import EventBus, EventKind
from labpilot.device.schema import DeviceSchema
from labpilot.plans.base import ScanPlan
from labpilot.plans.scan import scan


class MockMotor:
    """Mock motor implementing Movable protocol."""

    schema = DeviceSchema(
        name="mock_motor",
        kind="motor",
        readable={"position": "float64"},
        settable={"position": "float64"},
        units={"position": "um"},
        limits={"position": (0.0, 100.0)},
        trigger_modes=["software"],
        tags=["mock"],
    )

    def __init__(self) -> None:
        """Initialize mock motor."""
        self._position = 0.0
        self._staged = False

    async def stage(self) -> None:
        """Stage motor."""
        self._staged = True

    async def unstage(self) -> None:
        """Unstage motor."""
        self._staged = False

    async def set(self, value: float, *, timeout: float = 10.0) -> None:
        """Move to position."""
        if not (0.0 <= value <= 100.0):
            raise ValueError(f"Position {value} outside limits (0, 100)")
        self._position = value

    async def stop(self) -> None:
        """Stop motion."""
        pass

    async def where(self) -> float:
        """Get current position."""
        return self._position

    async def read(self) -> dict[str, Any]:
        """Read position."""
        return {"position": self._position}


class MockDetector:
    """Mock detector implementing Readable protocol."""

    schema = DeviceSchema(
        name="mock_detector",
        kind="detector",
        readable={"counts": "float64"},
        settable={},
        units={"counts": "counts"},
        limits={},
        trigger_modes=["software"],
        tags=["mock"],
    )

    def __init__(self) -> None:
        """Initialize mock detector."""
        self._staged = False

    async def stage(self) -> None:
        """Stage detector."""
        self._staged = True

    async def unstage(self) -> None:
        """Unstage detector."""
        self._staged = False

    async def read(self) -> dict[str, Any]:
        """Read detector (returns random counts)."""
        return {"counts": np.random.uniform(100, 1000)}


@pytest.mark.anyio
async def test_scan_basic() -> None:
    """Test basic scan execution."""
    motor = MockMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=10.0,
        stop=20.0,
        num=5,
        dwell=0.01,
    )

    events = []
    async for event in scan(plan, motor, detector, bus):
        events.append(event)

    # Should emit: DESCRIPTOR + (READING + PROGRESS) * 5 + STOP
    # = 1 + 10 + 1 = 12 events
    assert len(events) == 12

    # First event should be DESCRIPTOR
    assert events[0].kind == EventKind.DESCRIPTOR
    assert events[0].data["num_points"] == 5
    assert "plan" in events[0].data

    # Should have 5 readings
    readings = [e for e in events if e.kind == EventKind.READING]
    assert len(readings) == 5

    # Check reading data
    assert "motor_position" in readings[0].data
    assert "counts" in readings[0].data

    # Check positions are correct
    positions = [r.data["motor_position"] for r in readings]
    expected_positions = np.linspace(10.0, 20.0, 5)
    np.testing.assert_allclose(positions, expected_positions)

    # Should have 5 progress events
    progress_events = [e for e in events if e.kind == EventKind.PROGRESS]
    assert len(progress_events) == 5

    # Check progress fractions
    fractions = [p.data["fraction"] for p in progress_events]
    assert fractions[0] == 0.2  # 1/5
    assert fractions[-1] == 1.0  # 5/5

    # Last event should be STOP
    assert events[-1].kind == EventKind.STOP


@pytest.mark.anyio
async def test_scan_motor_staged_unstaged() -> None:
    """Test that devices are staged and unstaged properly."""
    motor = MockMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=10.0,
        num=3,
        dwell=0.01,
    )

    # Devices should not be staged initially
    assert not motor._staged
    assert not detector._staged

    events = []
    async for event in scan(plan, motor, detector, bus):
        events.append(event)

    # Devices should be unstaged after scan completes
    assert not motor._staged
    assert not detector._staged


@pytest.mark.anyio
async def test_scan_run_uid_consistency() -> None:
    """Test that all events have same run_uid."""
    motor = MockMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=10.0,
        num=3,
        dwell=0.01,
    )

    events = []
    async for event in scan(plan, motor, detector, bus):
        events.append(event)

    # All events should have same run_uid
    run_uids = {e.run_uid for e in events}
    assert len(run_uids) == 1
    assert None not in run_uids


@pytest.mark.anyio
async def test_scan_broadcasts_to_bus() -> None:
    """Test that scan events are broadcast on EventBus."""
    motor = MockMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=10.0,
        num=3,
        dwell=0.01,
    )

    # Subscribe to bus
    bus_events = []

    async def bus_subscriber() -> None:
        async for event in bus.subscribe():
            bus_events.append(event)
            if event.kind == EventKind.STOP:
                break

    import asyncio

    async with asyncio.TaskGroup() as tg:
        tg.create_task(bus_subscriber())

        # Give subscriber time to start
        await asyncio.sleep(0.01)

        # Run scan
        async for _ in scan(plan, motor, detector, bus):
            pass

    # Bus should have received same events as scan generator
    # DESCRIPTOR + (READING + PROGRESS) * 3 + STOP = 10 events
    assert len(bus_events) == 10


@pytest.mark.anyio
async def test_scan_single_point() -> None:
    """Test scan with single point."""
    motor = MockMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=50.0,
        stop=50.0,
        num=1,
        dwell=0.01,
    )

    events = []
    async for event in scan(plan, motor, detector, bus):
        events.append(event)

    # DESCRIPTOR + READING + PROGRESS + STOP = 4 events
    assert len(events) == 4

    readings = [e for e in events if e.kind == EventKind.READING]
    assert len(readings) == 1
    assert readings[0].data["motor_position"] == 50.0


@pytest.mark.anyio
async def test_scan_metadata_in_descriptor() -> None:
    """Test that plan metadata appears in DESCRIPTOR event."""
    motor = MockMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=10.0,
        num=3,
        dwell=0.01,
        metadata={"sample": "test_sample", "user": "alice"},
    )

    events = []
    async for event in scan(plan, motor, detector, bus):
        events.append(event)

    descriptor = events[0]
    assert descriptor.kind == EventKind.DESCRIPTOR
    assert descriptor.data["plan"]["metadata"]["sample"] == "test_sample"
    assert descriptor.data["plan"]["metadata"]["user"] == "alice"


@pytest.mark.anyio
async def test_scan_error_handling() -> None:
    """Test scan error handling when motor fails."""

    class FailingMotor(MockMotor):
        """Motor that fails on set."""

        async def set(self, value: float, *, timeout: float = 10.0) -> None:
            """Fail on set."""
            raise RuntimeError("Motor hardware error")

    motor = FailingMotor()
    detector = MockDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=10.0,
        num=3,
        dwell=0.01,
    )

    events = []
    with pytest.raises(RuntimeError, match="Motor hardware error"):
        async for event in scan(plan, motor, detector, bus):
            events.append(event)

    # Should have emitted DESCRIPTOR and ERROR
    assert any(e.kind == EventKind.DESCRIPTOR for e in events)
    assert any(e.kind == EventKind.ERROR for e in events)

    # Error event should have traceback
    error_event = [e for e in events if e.kind == EventKind.ERROR][0]
    assert "error_type" in error_event.data
    assert error_event.data["error_type"] == "RuntimeError"
    assert "traceback" in error_event.data


@pytest.mark.anyio
async def test_scan_unstages_on_error() -> None:
    """Test that devices are unstaged even when scan fails."""

    class FailingDetector(MockDetector):
        """Detector that fails on read."""

        async def read(self) -> dict[str, Any]:
            """Fail on read."""
            raise RuntimeError("Detector read error")

    motor = MockMotor()
    detector = FailingDetector()
    bus = EventBus()

    plan = ScanPlan(
        name="test_scan",
        motor="mock_motor",
        detector="mock_detector",
        start=0.0,
        stop=10.0,
        num=3,
        dwell=0.01,
    )

    with pytest.raises(RuntimeError, match="Detector read error"):
        async for _ in scan(plan, motor, detector, bus):
            pass

    # Devices should be unstaged even after error
    assert not motor._staged
    assert not detector._staged
