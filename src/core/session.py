"""Session: top-level runtime object for LabPilot.

Session manages:
- Device registry (all connected hardware)
- Event bus (for GUI/storage subscription)
- FSM state (current scan status)
- Configuration loading from TOML

All scan operations go through Session methods to ensure state consistency.
"""

from __future__ import annotations

import contextvars
import tomllib
from pathlib import Path

from core.events import Event, EventBus, EventKind
from core.fsm import ScanState, State
from core.device.protocols import Readable
from core.plans.base import ScanPlan
from core.plans.scan import scan as scan_generator
from core.device.kinds import wrap as _wrap_instrument

__all__ = ["Session"]

# Module-level (not per-instance): asyncio.create_task() copies the current
# context for the new task, so a ContextVar.set() inside one running
# workflow's task is invisible to a *different* workflow's task running
# concurrently on the same shared Session — unlike a plain instance
# attribute, which two concurrent tasks would clobber on each other (each
# task calling set_progress_context() on the one shared `session` object).
# Holds (workflow_id, execution_id, live-progress sink dict) or None.
_progress_context_var: contextvars.ContextVar[tuple[str, str, dict] | None] = contextvars.ContextVar(
    "labpilot_progress_context", default=None
)


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
        # Role name -> real registered device name (e.g. "xy_actuator" ->
        # "scanner_2d_1"), applied by WorkflowEngine immediately before
        # running a workflow whose script was written against role names
        # (see core/workflow/instrument_roles.py) rather than literal
        # instrument ids, and cleared again right after — scoped to one
        # execution, never left registered between runs.
        self._aliases: dict[str, str] = {}
        # Live-progress context (which workflow/execution report_progress()
        # calls belong to) is NOT stored here — see _progress_context_var
        # above: it needs to be per-asyncio-task, and a plain instance
        # attribute on this one shared Session would let two concurrently
        # running workflows clobber each other's context.

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

    def register(self, device: Readable, name: str | None = None) -> None:
        """Register device in session registry.

        Args:
            device: Device implementing Readable protocol.
            name: Registry key to use. Defaults to `device.schema.name`, but
                callers registering multiple instances of the same adapter
                type (e.g. several instruments of the same model connected
                through the dashboard, each with its own instrument_id) must
                pass an explicit unique name — schema.name is the same for
                every instance of a given adapter class.

        Raises:
            ValueError: If name already registered.

        Example:
            >>> motor = ThorlabsMDT693B(port="/dev/ttyUSB0")
            >>> await motor.connect()
            >>> session.register(motor)
        """
        name = name or device.schema.name
        if name in self.devices:
            raise ValueError(
                f"Device '{name}' already registered. Use unique names for all devices."
            )
        self.devices[name] = device

    def unregister(self, name: str) -> None:
        """Remove a device from the registry, if present (no-op otherwise —
        e.g. a workflow-referenced instrument that was never connected)."""
        self.devices.pop(name, None)

    def register_alias(self, role: str, real_name: str) -> None:
        """Make `get(role)` resolve to whatever's registered as
        `real_name` — used to run a role-based workflow script (one
        written against a role name like "xy_actuator" rather than a
        literal instrument id) against whichever real instrument is
        currently bound to that role. See
        core/workflow/instrument_roles.py."""
        self._aliases[role] = real_name

    def clear_aliases(self) -> None:
        self._aliases.clear()

    def set_progress_context(self, workflow_id: str, execution_id: str, sink: dict[str, dict]) -> None:
        """Called by WorkflowEngine right before running a script (inside
        that execution's own asyncio task — see _progress_context_var), so
        any `session.report_progress(...)` call inside it knows which
        workflow/execution it belongs to and where to store the latest
        report for polling clients."""
        _progress_context_var.set((workflow_id, execution_id, sink))

    def clear_progress_context(self) -> None:
        _progress_context_var.set(None)

    async def report_progress(self, data: dict) -> None:
        """Publish incremental progress from inside a running workflow
        script — e.g. one more pixel of a scan. Stored for REST polling
        (WorkflowEngine.get_live_progress) and emitted on the bus for any
        subscriber. A no-op outside of a workflow execution, so scripts can
        call it unconditionally without checking context first.

        `data` is expected to carry the FULL accumulated result so far
        (e.g. an ND scan's whole flat data array to date) — cheap to store
        here (a dict/list reference, not a copy), but server.py's
        _event_broadcaster deliberately strips oversized fields before
        broadcasting this on the bus's WebSocket-facing side, since
        resending the whole, ever-growing array on every call would be
        broadcast to any subscriber every time. A script producing point-
        by-point data at a rate where that matters (e.g. omniscan.py)
        should ALSO call report_reading() below for each new point — a
        deliberately small, bounded-size companion built for exactly that
        live per-point path."""
        ctx = _progress_context_var.get()
        if ctx is None:
            return
        workflow_id, execution_id, sink = ctx
        if sink is not None:
            sink[workflow_id] = data
        await self.bus.emit(
            Event(
                kind=EventKind.WORKFLOW_PROGRESS,
                data={"workflow_id": workflow_id, "execution_id": execution_id, **data},
            )
        )

    async def report_reading(self, data: dict) -> None:
        """Publish ONE new data point from inside a running workflow
        script — e.g. one grid point of a scan, as it's acquired.

        Unlike report_progress() above, `data` here is expected to be
        small and the SAME size on every call (this one point's own
        contribution, not the growing whole) — mirrors how qudi's
        ScanningProbeLogic and pyMoDAQ's DAQ_Viewer push live updates via
        Qt signals carrying just the new data, and this codebase's own
        EventKind.READING ("one data point from detector(s)"), which
        existed but wasn't wired to anything until this. Because each
        call is bounded in size regardless of how far the scan has
        progressed, a listener (see backend_client.py's
        WorkflowStatePoller) can genuinely apply every single one — no
        throttling, no refetching a snapshot — the way report_progress()
        needs server-side thinning + client-side debounced refetching to
        stay cheap. Not stored anywhere (report_progress already owns the
        durable/REST-facing accumulated state) — purely a live broadcast.
        A no-op outside of a workflow execution, matching report_progress().
        """
        ctx = _progress_context_var.get()
        if ctx is None:
            return
        workflow_id, execution_id, _sink = ctx
        await self.bus.emit(
            Event(
                kind=EventKind.READING,
                data={"workflow_id": workflow_id, "execution_id": execution_id, **data},
            )
        )

    def has(self, name: str) -> bool:
        """Whether `get(name)` would succeed — a literal registered
        device, or a role with an active alias (`register_alias`). Lets a
        role-based template check an *optional* role (see
        `REQUIRED_INSTRUMENTS`'s `"optional": True`,
        core/workflow/instrument_roles.py) is actually bound before
        calling `get()` on it, without relying on a try/except KeyError."""
        return name in self.devices or name in self._aliases

    def get(self, name: str) -> Readable:
        """Retrieve device from registry by name — or, if `name` isn't a
        literal registered device but a role with an active alias (see
        `register_alias`), by resolving through that alias instead.

        Returns a kind-typed wrapper (`instruments.kinds.Motor`/`Detector`/
        `Source`/`Scanner`/`GenericInstrument`, chosen from the device's own
        `schema.kind`) rather than the raw adapter — see docs/scripting.md.
        The wrapper still exposes `.read()`/`.write()`/`.schema`/`.stage()`/
        `.unstage()` exactly as the raw adapter did (plus `__getattr__`
        passthrough for anything else), so this is purely additive: every
        existing template/capability calling only that surface keeps
        working unmodified. Use `get_raw()` to bypass the wrapper entirely.

        Args:
            name: Device name (from DeviceSchema.name) or an aliased role.

        Returns:
            Kind-typed wrapper around the device instance.

        Raises:
            KeyError: If device name not found, with helpful message listing
                     available devices.

        Example:
            >>> motor = session.get("thorlabs_mdt693b")
            >>> await motor.move_abs(5.0)
        """
        return _wrap_instrument(self.get_raw(name))

    def get_raw(self, name: str) -> Readable:
        """Like `get()`, but returns the literal registered adapter,
        unwrapped — an escape hatch for the rare caller that needs the
        adapter's own identity or an attribute the kind wrapper doesn't
        forward some other way."""
        if name not in self.devices and name in self._aliases:
            name = self._aliases[name]
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
