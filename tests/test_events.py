"""Tests for event system (EventKind, Event, EventBus)."""

from __future__ import annotations

import asyncio

import pytest

from labpilot.core.events import Event, EventBus, EventKind


def test_event_kind_enum() -> None:
    """Test EventKind enum has all required members."""
    assert EventKind.STATE_CHANGE
    assert EventKind.DESCRIPTOR
    assert EventKind.READING
    assert EventKind.PROGRESS
    assert EventKind.WARNING
    assert EventKind.ERROR
    assert EventKind.STOP


def test_event_creation() -> None:
    """Test Event creation with defaults."""
    event = Event(kind=EventKind.READING, data={"value": 42})

    assert event.kind == EventKind.READING
    assert event.data["value"] == 42
    assert isinstance(event.uid, str)
    assert len(event.uid) > 0  # UUID4 string
    assert isinstance(event.timestamp, float)
    assert event.timestamp > 0
    assert event.run_uid is None


def test_event_with_run_uid() -> None:
    """Test Event with run_uid specified."""
    event = Event(
        kind=EventKind.DESCRIPTOR,
        run_uid="test-run-123",
        data={"plan": "scan1"},
    )

    assert event.run_uid == "test-run-123"


def test_event_to_dict() -> None:
    """Test Event serialization to dict."""
    event = Event(
        kind=EventKind.ERROR,
        data={"error": "Test error"},
        run_uid="run-456",
    )

    data = event.to_dict()

    assert data["kind"] == "ERROR"
    assert data["uid"] == event.uid
    assert data["timestamp"] == event.timestamp
    assert data["data"] == {"error": "Test error"}
    assert data["run_uid"] == "run-456"


@pytest.mark.anyio
async def test_eventbus_emit_subscribe() -> None:
    """Test basic emit and subscribe flow."""
    bus = EventBus()
    received_events = []

    # Subscribe to READING events
    async def subscriber() -> None:
        async for event in bus.subscribe(EventKind.READING):
            received_events.append(event)
            if len(received_events) >= 3:
                break

    # Run subscriber in background
    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscriber())

        # Give subscriber time to start
        await asyncio.sleep(0.01)

        # Emit events
        await bus.emit(Event(kind=EventKind.READING, data={"value": 1}))
        await bus.emit(Event(kind=EventKind.READING, data={"value": 2}))
        await bus.emit(Event(kind=EventKind.READING, data={"value": 3}))

    # Check received events
    assert len(received_events) == 3
    assert received_events[0].data["value"] == 1
    assert received_events[1].data["value"] == 2
    assert received_events[2].data["value"] == 3


@pytest.mark.anyio
async def test_eventbus_filtered_subscription() -> None:
    """Test filtered subscription (only specific EventKinds)."""
    bus = EventBus()
    received_events = []

    # Subscribe to READING and PROGRESS only
    async def subscriber() -> None:
        async for event in bus.subscribe(EventKind.READING, EventKind.PROGRESS):
            received_events.append(event)
            if len(received_events) >= 2:
                break

    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscriber())
        await asyncio.sleep(0.01)

        # Emit mixed events
        await bus.emit(Event(kind=EventKind.DESCRIPTOR, data={}))  # Filtered out
        await bus.emit(Event(kind=EventKind.READING, data={"value": 1}))  # Received
        await bus.emit(Event(kind=EventKind.WARNING, data={}))  # Filtered out
        await bus.emit(Event(kind=EventKind.PROGRESS, data={"frac": 0.5}))  # Received

    # Should only receive READING and PROGRESS
    assert len(received_events) == 2
    assert received_events[0].kind == EventKind.READING
    assert received_events[1].kind == EventKind.PROGRESS


@pytest.mark.anyio
async def test_eventbus_multiple_subscribers() -> None:
    """Test fan-out to multiple subscribers."""
    bus = EventBus()
    received_1 = []
    received_2 = []

    async def subscriber_1() -> None:
        async for event in bus.subscribe(EventKind.READING):
            received_1.append(event)
            if len(received_1) >= 2:
                break

    async def subscriber_2() -> None:
        async for event in bus.subscribe(EventKind.READING):
            received_2.append(event)
            if len(received_2) >= 2:
                break

    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscriber_1())
        tg.create_task(subscriber_2())
        await asyncio.sleep(0.01)

        # Emit events
        await bus.emit(Event(kind=EventKind.READING, data={"value": 1}))
        await bus.emit(Event(kind=EventKind.READING, data={"value": 2}))

    # Both subscribers should receive both events
    assert len(received_1) == 2
    assert len(received_2) == 2
    assert received_1[0].data["value"] == 1
    assert received_2[0].data["value"] == 1


@pytest.mark.anyio
async def test_eventbus_subscriber_cleanup() -> None:
    """Test subscriber cleanup on task cancellation."""
    bus = EventBus()

    # Start subscriber
    async def subscriber() -> None:
        async for event in bus.subscribe(EventKind.READING):
            await asyncio.sleep(0.1)

    async with asyncio.TaskGroup() as tg:
        task = tg.create_task(subscriber())
        await asyncio.sleep(0.01)

        # Should have one subscriber
        assert bus.subscriber_count() == 1

        # Cancel task
        task.cancel()

    # Give cleanup time to happen
    await asyncio.sleep(0.01)

    # Subscriber should be cleaned up
    assert bus.subscriber_count() == 0


@pytest.mark.anyio
async def test_eventbus_no_filter() -> None:
    """Test subscription with no filters (receives all events)."""
    bus = EventBus()
    received_events = []

    async def subscriber() -> None:
        async for event in bus.subscribe():  # No filters = all events
            received_events.append(event)
            if len(received_events) >= 3:
                break

    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscriber())
        await asyncio.sleep(0.01)

        # Emit different event types
        await bus.emit(Event(kind=EventKind.DESCRIPTOR, data={}))
        await bus.emit(Event(kind=EventKind.READING, data={}))
        await bus.emit(Event(kind=EventKind.STOP, data={}))

    # Should receive all events
    assert len(received_events) == 3
    assert received_events[0].kind == EventKind.DESCRIPTOR
    assert received_events[1].kind == EventKind.READING
    assert received_events[2].kind == EventKind.STOP
