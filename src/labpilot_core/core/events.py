"""Event system for LabPilot.

Provides a typed, async-native event bus for communication between scan engines,
storage subscribers, and GUI clients. All events are msgpack-serialisable for
future ZMQ-based remote GUI support.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

__all__ = ["Event", "EventBus", "EventKind"]


class EventKind(Enum):
    """Event types emitted during scan execution and system operations."""

    # Scan/workflow events
    STATE_CHANGE = auto()  # FSM transition fired
    DESCRIPTOR = auto()  # Schema emitted at scan start (one per run)
    READING = auto()  # One data point from detector(s)
    PROGRESS = auto()  # Fraction complete + ETA seconds
    WARNING = auto()  # Non-fatal anomaly
    ERROR = auto()  # Fatal, scan will stop
    STOP = auto()  # Scan finished cleanly

    # Workflow execution events
    WORKFLOW_STARTED = auto()  # Workflow execution started
    WORKFLOW_STOPPED = auto()  # Workflow execution stopped
    WORKFLOW_COMPLETED = auto()  # Workflow execution completed successfully
    WORKFLOW_ERROR = auto()  # Workflow execution failed
    WORKFLOW_NODE_STARTED = auto()  # Individual node started
    WORKFLOW_NODE_COMPLETED = auto()  # Individual node completed
    WORKFLOW_NODE_ERROR = auto()  # Individual node failed

    # AI system events
    AI_INITIALIZED = auto()  # AI system initialized with provider
    AI_SHUTDOWN = auto()  # AI system shutdown
    AI_MESSAGE_RECEIVED = auto()  # AI response received from provider
    AI_TOOL_CALLED = auto()  # AI tool execution requested
    AI_TOOL_COMPLETED = auto()  # AI tool execution completed


@dataclass(frozen=True)
class Event:
    """Immutable event record.

    All fields must be msgpack-serialisable. Numpy arrays in `data` should be
    converted to bytes+dtype+shape metadata before emission.

    Attributes:
        kind: Event type classification.
        uid: Unique identifier (UUID4 string).
        timestamp: Unix timestamp (seconds since epoch).
        data: Event payload. Keys and values must be serialisable.
        run_uid: Run identifier this event belongs to (None for system events).
    """

    kind: EventKind
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    run_uid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to msgpack-serialisable dictionary."""
        return {
            "kind": self.kind.name,
            "uid": self.uid,
            "timestamp": self.timestamp,
            "data": self.data,
            "run_uid": self.run_uid,
        }


class EventBus:
    """Thread-safe event bus with filtered subscription support.

    Uses asyncio.Queue for fan-out to multiple subscribers. Each subscriber
    receives only events matching their requested EventKind filters.

    Example:
        >>> bus = EventBus()
        >>> async for event in bus.subscribe(EventKind.READING, EventKind.PROGRESS):
        ...     print(event.data)
    """

    def __init__(self) -> None:
        """Initialize empty event bus."""
        self._subscribers: list[tuple[asyncio.Queue[Event], set[EventKind]]] = []
        self._lock = asyncio.Lock()

    async def emit(self, event: Event) -> None:
        """Broadcast event to all matching subscribers.

        Thread-safe: may be called from anyio.to_thread.run_sync contexts.

        Args:
            event: Event to broadcast.
        """
        async with self._lock:
            # Copy subscriber list to avoid modification during iteration
            subscribers = self._subscribers.copy()

        for queue, filters in subscribers:
            # If no filters specified, subscriber gets all events
            if not filters or event.kind in filters:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Log or handle full queue - for now, skip
                    # In production, might want configurable backpressure strategy
                    pass

    async def subscribe(self, *kinds: EventKind) -> AsyncIterator[Event]:
        """Subscribe to events matching specified kinds.

        Creates an asyncio.Queue for this subscriber and yields events until
        the iterator is closed. Queue is automatically cleaned up on exit.

        Args:
            *kinds: EventKind filters. If empty, receives all events.

        Yields:
            Events matching the specified kinds.

        Example:
            >>> async for event in bus.subscribe(EventKind.READING):
            ...     intensities = event.data["intensities"]
            ...     print(f"Peak: {intensities.max()}")
        """
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
        filters = set(kinds) if kinds else set()

        async with self._lock:
            self._subscribers.append((queue, filters))

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Clean up subscriber on exit (even if cancelled)
            async with self._lock:
                try:
                    self._subscribers.remove((queue, filters))
                except ValueError:
                    # Already removed, ignore
                    pass

    def subscriber_count(self) -> int:
        """Return current number of active subscribers.

        Useful for health checks and debugging.

        Returns:
            Number of active subscriber queues.
        """
        return len(self._subscribers)
