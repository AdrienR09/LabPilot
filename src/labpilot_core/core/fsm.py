"""Finite state machine for scan execution lifecycle.

Enforces valid state transitions and prevents unsafe operations (e.g., cannot
pause when not running, cannot configure while running).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

__all__ = ["InvalidTransitionError", "ScanState", "State"]


class State(Enum):
    """Scan execution states."""

    IDLE = auto()  # No scan active, ready to configure
    CONFIGURING = auto()  # Loading plan, registering devices
    ARMED = auto()  # Ready to start, devices staged
    RUNNING = auto()  # Scan in progress
    PAUSED = auto()  # Temporarily stopped, resumable
    FINISHING = auto()  # Unstaging devices, writing final data
    DONE = auto()  # Completed successfully
    ERROR = auto()  # Fatal error occurred


class InvalidTransitionError(Exception):
    """Raised when attempting an illegal state transition."""

    def __init__(self, current: State, requested: State) -> None:
        """Initialize with current and requested states.

        Args:
            current: Current FSM state.
            requested: Requested target state.
        """
        self.current = current
        self.requested = requested
        super().__init__(
            f"Invalid transition from {current.name} to {requested.name}"
        )


# Valid state transitions: {current_state: {allowed_next_states}}
_ALLOWED_TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.CONFIGURING},
    State.CONFIGURING: {State.ARMED, State.ERROR},
    State.ARMED: {State.RUNNING, State.IDLE, State.ERROR},
    State.RUNNING: {State.PAUSED, State.FINISHING, State.ERROR},
    State.PAUSED: {State.RUNNING, State.FINISHING, State.ERROR},
    State.FINISHING: {State.DONE, State.ERROR},
    State.DONE: {State.IDLE},
    State.ERROR: {State.IDLE},
}


@dataclass(frozen=True)
class ScanState:
    """Immutable scan state snapshot.

    Tracks current execution state plus optional metadata (e.g., error message,
    progress fraction). Serialisable to dict for event emission.

    Attributes:
        state: Current FSM state.
        message: Optional human-readable status message.
        metadata: Additional state-specific data.
    """

    state: State
    message: str = ""
    metadata: dict[str, Any] | None = None

    def transition(self, target: State, message: str = "") -> ScanState:
        """Create new state after validating transition.

        Args:
            target: Requested next state.
            message: Optional status message for new state.

        Returns:
            New ScanState instance if transition is valid.

        Raises:
            InvalidTransitionError: If transition is not allowed.
        """
        allowed = _ALLOWED_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise InvalidTransitionError(self.state, target)

        return ScanState(state=target, message=message, metadata=self.metadata)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serialisable dictionary.

        Returns:
            Dictionary with state name, message, and metadata.
        """
        return {
            "state": self.state.name,
            "message": self.message,
            "metadata": self.metadata or {},
        }

    @classmethod
    def idle(cls) -> ScanState:
        """Create initial IDLE state.

        Returns:
            ScanState in IDLE state.
        """
        return cls(state=State.IDLE, message="Ready")
