"""Session: top-level runtime object for LabPilot.

Session manages:
- Device registry (all connected hardware)
- Event bus (for GUI/storage subscription)
- FSM state (current scan status)
- Configuration loading from TOML

All scan operations go through Session methods to ensure state consistency.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from labpilot_core.core.events import Event, EventBus, EventKind
from labpilot_core.core.fsm import ScanState, State
from labpilot_core.device.protocols import Readable
from labpilot_core.plans.base import ScanPlan
from labpilot_core.plans.scan import scan as scan_generator

__all__ = ["Session"]


class Session:
    """Top-level runtime object managing devices, events, and scan execution.

    Example:
        >>> session = await Session.load("lab_config.toml")
        >>> session.register(motor)
        >>> session.register(detector)
        >>> run_uid = await session.run(plan)
        >>> # GUI subscribes to session.bus for live updates
    """

    def __init__(self) -> None:
        """Initialize empty session with idle state."""
        self.bus = EventBus()
        self.state = ScanState.idle()
        self.devices: dict[str, Readable] = {}
        self._current_run_uid: str | None = None

    @classmethod
    async def load(cls, path: str | Path) -> Session:
        """Load session configuration from TOML file.

        TOML format:
            [session]
            name = "my_lab_session"

            [session.metadata]
            lab = "Quantum Optics Lab"
            user = "alice"

        Args:
            path: Path to TOML configuration file.

        Returns:
            Session instance with loaded configuration.

        Note:
            Devices must be registered separately after loading. This method
            only loads session-level configuration, not device instances.
        """
        session = cls()
        path = Path(path)

        if path.exists():
            with path.open("rb") as f:
                config = tomllib.load(f)

            # Store configuration as session metadata
            if "session" in config:
                session_config = config["session"]
                session.state = ScanState(
                    state=State.IDLE,
                    message="Loaded from config",
                    metadata=session_config.get("metadata", {}),
                )

        return session

    def register(self, device: Readable) -> None:
        """Register device in session registry.

        Args:
            device: Device implementing Readable protocol.

        Raises:
            ValueError: If device name already registered.

        Example:
            >>> motor = ThorlabsMDT693B(port="/dev/ttyUSB0")
            >>> await motor.connect()
            >>> session.register(motor)
        """
        name = device.schema.name
        if name in self.devices:
            raise ValueError(
                f"Device '{name}' already registered. Use unique names for all devices."
            )
        self.devices[name] = device

    def get(self, name: str) -> Readable:
        """Retrieve device from registry by name.

        Args:
            name: Device name (from DeviceSchema.name).

        Returns:
            Device instance.

        Raises:
            KeyError: If device name not found, with helpful message listing
                     available devices.

        Example:
            >>> motor = session.get("thorlabs_mdt693b")
        """
        if name not in self.devices:
            available = ", ".join(self.devices.keys())
            raise KeyError(
                f"Device '{name}' not found in session. "
                f"Available devices: {available or 'none'}"
            )
        return self.devices[name]

    async def run(self, plan: ScanPlan) -> str:
        """Execute scan plan and return run UID.

        Transitions FSM through states:
        IDLE → CONFIGURING → ARMED → RUNNING → FINISHING → DONE

        Args:
            plan: ScanPlan to execute.

        Returns:
            Run UID (UUID4 string) for referencing this scan.

        Raises:
            ValueError: If motor/detector names in plan not found in registry.
            InvalidTransitionError: If session not in IDLE state.

        Example:
            >>> plan = ScanPlan(name="scan1", motor="m1", detector="d1", ...)
            >>> run_uid = await session.run(plan)
            >>> print(f"Scan started: {run_uid}")
        """
        # Validate FSM state
        self.state = self.state.transition(State.CONFIGURING, "Loading plan")
        await self._emit_state_change()

        # Resolve device names from plan
        try:
            motor = self.get(plan.motor)
            detector = self.get(plan.detector)
        except KeyError as e:
            self.state = self.state.transition(State.ERROR, str(e))
            await self._emit_state_change()
            raise ValueError(f"Plan validation failed: {e}") from e

        # Transition to ARMED
        self.state = self.state.transition(State.ARMED, "Devices ready")
        await self._emit_state_change()

        # Transition to RUNNING
        self.state = self.state.transition(State.RUNNING, "Scan in progress")
        await self._emit_state_change()

        # Execute scan generator
        run_uid = None
        try:
            async for event in scan_generator(plan, motor, detector, self.bus):
                if event.kind == EventKind.DESCRIPTOR:
                    run_uid = event.run_uid
                    self._current_run_uid = run_uid

                # Check for stop or error events
                if event.kind == EventKind.STOP:
                    self.state = self.state.transition(
                        State.FINISHING, "Cleaning up"
                    )
                    await self._emit_state_change()
                    break
                elif event.kind == EventKind.ERROR:
                    self.state = self.state.transition(
                        State.ERROR, event.data.get("error_message", "Unknown error")
                    )
                    await self._emit_state_change()
                    break

            # Transition to DONE
            if self.state.state == State.FINISHING:
                self.state = self.state.transition(State.DONE, "Scan completed")
                await self._emit_state_change()

        except Exception as e:
            self.state = self.state.transition(State.ERROR, str(e))
            await self._emit_state_change()
            raise

        finally:
            self._current_run_uid = None

        # Return to IDLE after completion or error
        self.state = self.state.transition(State.IDLE, "Ready for next scan")
        await self._emit_state_change()

        return run_uid or "unknown"

    async def pause(self) -> None:
        """Pause currently running scan.

        Raises:
            InvalidTransitionError: If not in RUNNING state.

        Note:
            Pause functionality requires cancellation scope integration in
            scan generators. Currently transitions state but does not yet
            implement actual pause/resume logic.
        """
        self.state = self.state.transition(State.PAUSED, "Scan paused")
        await self._emit_state_change()

    async def resume(self) -> None:
        """Resume paused scan.

        Raises:
            InvalidTransitionError: If not in PAUSED state.
        """
        self.state = self.state.transition(State.RUNNING, "Scan resumed")
        await self._emit_state_change()

    async def abort(self) -> None:
        """Abort currently running scan and transition to ERROR state.

        Can be called from RUNNING or PAUSED states. Triggers cleanup
        (device unstaging) via scan generator finally blocks.

        Note:
            Full abort implementation requires anyio cancellation scope
            integration in scan generators.
        """
        if self.state.state in {State.RUNNING, State.PAUSED}:
            self.state = self.state.transition(State.ERROR, "Aborted by user")
            await self._emit_state_change()

    async def _emit_state_change(self) -> None:
        """Emit STATE_CHANGE event on bus.

        Called automatically after each state transition.
        """
        event = Event(
            kind=EventKind.STATE_CHANGE,
            data=self.state.to_dict(),
            run_uid=self._current_run_uid,
        )
        await self.bus.emit(event)
