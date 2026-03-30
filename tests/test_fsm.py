"""Tests for finite state machine (State, ScanState, transitions)."""

from __future__ import annotations

import pytest

from labpilot.core.fsm import InvalidTransitionError, ScanState, State


def test_state_enum() -> None:
    """Test State enum has all required states."""
    assert State.IDLE
    assert State.CONFIGURING
    assert State.ARMED
    assert State.RUNNING
    assert State.PAUSED
    assert State.FINISHING
    assert State.DONE
    assert State.ERROR


def test_scan_state_creation() -> None:
    """Test ScanState creation."""
    state = ScanState(state=State.IDLE, message="Ready", metadata={"key": "value"})

    assert state.state == State.IDLE
    assert state.message == "Ready"
    assert state.metadata == {"key": "value"}


def test_scan_state_idle_factory() -> None:
    """Test ScanState.idle() factory method."""
    state = ScanState.idle()

    assert state.state == State.IDLE
    assert state.message == "Ready"
    assert state.metadata is None


def test_scan_state_immutable() -> None:
    """Test ScanState is frozen (immutable)."""
    state = ScanState.idle()

    with pytest.raises(Exception):  # FrozenInstanceError in Python 3.11+
        state.state = State.RUNNING  # type: ignore


def test_valid_transition_idle_to_configuring() -> None:
    """Test valid transition from IDLE to CONFIGURING."""
    state = ScanState.idle()
    new_state = state.transition(State.CONFIGURING, "Loading plan")

    assert new_state.state == State.CONFIGURING
    assert new_state.message == "Loading plan"
    assert state.state == State.IDLE  # Original unchanged


def test_valid_transition_configuring_to_armed() -> None:
    """Test valid transition from CONFIGURING to ARMED."""
    state = ScanState(state=State.CONFIGURING)
    new_state = state.transition(State.ARMED, "Ready to start")

    assert new_state.state == State.ARMED
    assert new_state.message == "Ready to start"


def test_valid_transition_running_to_paused() -> None:
    """Test valid transition from RUNNING to PAUSED."""
    state = ScanState(state=State.RUNNING)
    new_state = state.transition(State.PAUSED, "Paused by user")

    assert new_state.state == State.PAUSED


def test_valid_transition_paused_to_running() -> None:
    """Test valid transition from PAUSED to RUNNING."""
    state = ScanState(state=State.PAUSED)
    new_state = state.transition(State.RUNNING, "Resuming")

    assert new_state.state == State.RUNNING


def test_valid_transition_running_to_finishing() -> None:
    """Test valid transition from RUNNING to FINISHING."""
    state = ScanState(state=State.RUNNING)
    new_state = state.transition(State.FINISHING, "Cleaning up")

    assert new_state.state == State.FINISHING


def test_valid_transition_finishing_to_done() -> None:
    """Test valid transition from FINISHING to DONE."""
    state = ScanState(state=State.FINISHING)
    new_state = state.transition(State.DONE, "Completed")

    assert new_state.state == State.DONE


def test_valid_transition_done_to_idle() -> None:
    """Test valid transition from DONE back to IDLE."""
    state = ScanState(state=State.DONE)
    new_state = state.transition(State.IDLE, "Ready for next scan")

    assert new_state.state == State.IDLE


def test_valid_transition_to_error() -> None:
    """Test valid transitions to ERROR state from various states."""
    # From CONFIGURING
    state = ScanState(state=State.CONFIGURING)
    new_state = state.transition(State.ERROR, "Configuration failed")
    assert new_state.state == State.ERROR

    # From RUNNING
    state = ScanState(state=State.RUNNING)
    new_state = state.transition(State.ERROR, "Hardware error")
    assert new_state.state == State.ERROR

    # From PAUSED
    state = ScanState(state=State.PAUSED)
    new_state = state.transition(State.ERROR, "Error during pause")
    assert new_state.state == State.ERROR


def test_valid_transition_error_to_idle() -> None:
    """Test valid transition from ERROR back to IDLE."""
    state = ScanState(state=State.ERROR, message="Hardware error")
    new_state = state.transition(State.IDLE, "Reset")

    assert new_state.state == State.IDLE
    assert new_state.message == "Reset"


def test_invalid_transition_idle_to_running() -> None:
    """Test invalid transition from IDLE directly to RUNNING."""
    state = ScanState.idle()

    with pytest.raises(InvalidTransitionError) as exc_info:
        state.transition(State.RUNNING)

    assert exc_info.value.current == State.IDLE
    assert exc_info.value.requested == State.RUNNING
    assert "IDLE" in str(exc_info.value)
    assert "RUNNING" in str(exc_info.value)


def test_invalid_transition_running_to_done() -> None:
    """Test invalid transition from RUNNING directly to DONE."""
    state = ScanState(state=State.RUNNING)

    with pytest.raises(InvalidTransitionError) as exc_info:
        state.transition(State.DONE)

    assert exc_info.value.current == State.RUNNING
    assert exc_info.value.requested == State.DONE


def test_invalid_transition_done_to_running() -> None:
    """Test invalid transition from DONE to RUNNING."""
    state = ScanState(state=State.DONE)

    with pytest.raises(InvalidTransitionError):
        state.transition(State.RUNNING)


def test_invalid_transition_armed_to_finishing() -> None:
    """Test invalid transition from ARMED to FINISHING."""
    state = ScanState(state=State.ARMED)

    with pytest.raises(InvalidTransitionError):
        state.transition(State.FINISHING)


def test_scan_state_to_dict() -> None:
    """Test ScanState serialization to dict."""
    state = ScanState(
        state=State.RUNNING,
        message="In progress",
        metadata={"run_uid": "abc123"},
    )

    data = state.to_dict()

    assert data["state"] == "RUNNING"
    assert data["message"] == "In progress"
    assert data["metadata"] == {"run_uid": "abc123"}


def test_scan_state_to_dict_no_metadata() -> None:
    """Test ScanState.to_dict() with None metadata."""
    state = ScanState(state=State.IDLE)

    data = state.to_dict()

    assert data["state"] == "IDLE"
    assert data["metadata"] == {}


def test_full_scan_lifecycle() -> None:
    """Test complete scan state lifecycle."""
    # Start in IDLE
    state = ScanState.idle()
    assert state.state == State.IDLE

    # Configure
    state = state.transition(State.CONFIGURING)
    assert state.state == State.CONFIGURING

    # Arm
    state = state.transition(State.ARMED)
    assert state.state == State.ARMED

    # Start running
    state = state.transition(State.RUNNING)
    assert state.state == State.RUNNING

    # Finish
    state = state.transition(State.FINISHING)
    assert state.state == State.FINISHING

    # Complete
    state = state.transition(State.DONE)
    assert state.state == State.DONE

    # Back to idle
    state = state.transition(State.IDLE)
    assert state.state == State.IDLE


def test_pause_resume_lifecycle() -> None:
    """Test scan lifecycle with pause/resume."""
    state = ScanState.idle()

    # Start scan
    state = state.transition(State.CONFIGURING)
    state = state.transition(State.ARMED)
    state = state.transition(State.RUNNING)
    assert state.state == State.RUNNING

    # Pause
    state = state.transition(State.PAUSED)
    assert state.state == State.PAUSED

    # Resume
    state = state.transition(State.RUNNING)
    assert state.state == State.RUNNING

    # Complete
    state = state.transition(State.FINISHING)
    state = state.transition(State.DONE)
    state = state.transition(State.IDLE)
    assert state.state == State.IDLE


def test_error_recovery_lifecycle() -> None:
    """Test scan lifecycle with error and recovery."""
    state = ScanState.idle()

    # Start scan
    state = state.transition(State.CONFIGURING)
    state = state.transition(State.ARMED)
    state = state.transition(State.RUNNING)

    # Error occurs
    state = state.transition(State.ERROR, "Hardware fault")
    assert state.state == State.ERROR
    assert state.message == "Hardware fault"

    # Recover to idle
    state = state.transition(State.IDLE, "Reset after error")
    assert state.state == State.IDLE
