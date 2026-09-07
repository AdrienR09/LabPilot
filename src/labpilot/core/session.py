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
from typing import Any

from labpilot.core.data.dataset import DatasetPatch, summarise_arrays
from labpilot.core.device.kinds import wrap as _wrap_instrument
from labpilot.core.device.protocols import Readable
from labpilot.core.events import Event, EventBus, EventKind
from labpilot.core.fsm import ScanState, State

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

# Role -> real device name, per running workflow. Also a ContextVar, and for
# exactly the same reason as the progress context above: RunManager applies
# a workflow's bindings immediately before running it and clears them after, so
# on a plain instance attribute two workflows running concurrently share one
# namespace. Both templates using the role "detector" meant the second to start
# silently rebound the first, and whichever finished first unbound the other
# mid-run.
_aliases_var: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "labpilot_role_aliases", default=None
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
        # Role aliases are NOT stored here — see _aliases_var above: they are
        # per-execution state, and two concurrently running workflows would
        # otherwise clobber each other's role bindings.
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
        core/workflow/instrument_roles.py.

        Scoped to the calling asyncio task, so concurrent workflows each see
        only their own bindings."""
        aliases = _aliases_var.get()
        if aliases is None:
            aliases = {}
            _aliases_var.set(aliases)
        aliases[role] = real_name

    def clear_aliases(self) -> None:
        _aliases_var.set(None)

    def set_progress_context(self, workflow_id: str, execution_id: str, sink: dict[str, dict]) -> None:
        """Called by RunManager right before running a script (inside
        that execution's own asyncio task — see _progress_context_var), so
        any `session.report_progress(...)` call inside it knows which
        workflow/execution it belongs to and where to store the latest
        report for polling clients."""
        _progress_context_var.set((workflow_id, execution_id, sink))

    def clear_progress_context(self) -> None:
        _progress_context_var.set(None)

    def progress_context_id(self) -> str | None:
        """The workflow id this task is running under, if any.

        What a `Run` registers itself against so that a Stop or Pause
        arriving on the server loop can find it (`core/run/run.py`).
        """
        ctx = _progress_context_var.get()
        return ctx[0] if ctx else None

    async def report_progress(self, data: dict) -> None:
        """Publish the full accumulated result so far from inside a running
        workflow script — e.g. the whole scan array to date.

        `data` is stored verbatim for REST polling
        (`RunManager.get_live_progress`), which is cheap: a dict
        reference, not a copy. What goes **on the bus** is
        `summarise_arrays(data)` — every array replaced by its length.

        The bus reaches every connected client on every tick, so a growing
        result array does not belong on it. That used to be enforced at the
        socket by `server.py::_strip_oversized_fields`, which dropped any
        list longer than 4096 elements from every outgoing event; it
        existed because one un-thinned completion frame for a 30x30 scan
        produced a ~70 MB frame and killed the WebSocket. Deciding here
        instead makes it a rule rather than a threshold, and puts it where
        the meaning of each field is known.

        Clients already work this way — a progress event is a "something
        changed" signal, and the data arrives either as a `DatasetPatch`
        per point (see `report_reading`) or by re-fetching the snapshot
        over REST. A no-op outside a workflow execution, so scripts can
        call it unconditionally.
        """
        ctx = _progress_context_var.get()
        if ctx is None:
            return
        workflow_id, execution_id, sink = ctx
        if sink is not None:
            sink[workflow_id] = data
        await self.bus.emit(
            Event(
                kind=EventKind.WORKFLOW_PROGRESS,
                data={
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    **summarise_arrays(data),
                },
            )
        )

    async def report_reading(
        self, patch: DatasetPatch | dict, **meta: Any
    ) -> None:
        """Publish ONE new data point as it is acquired.

        A `DatasetPatch` is the whole point: it is the size of the new
        data, not of the scan so far, so a listener can apply every single
        one without throttling however far the scan has progressed —
        unlike `report_progress`, whose payload grows. This mirrors how
        qudi's `ScanningProbeLogic` and pyMoDAQ's `DAQ_Viewer` push live
        updates carrying just the new values.

        `meta` is the run-level description a client needs in order to
        place the patch (shape, axis names, axis positions). Send it on the
        first reading of a run and omit it afterwards: repeating it costs
        an axis array per point, which for a 1800-channel spectrometer is
        most of the traffic the patch was introduced to avoid. Clients
        merge whatever is present and keep the rest.

        A plain dict is still accepted, for a workflow instance saved as
        source before `DatasetPatch` existed. Not stored anywhere —
        `report_progress` already owns the durable, REST-facing state.
        A no-op outside a workflow execution.
        """
        ctx = _progress_context_var.get()
        if ctx is None:
            return
        workflow_id, execution_id, _sink = ctx
        payload = patch.to_wire() if isinstance(patch, DatasetPatch) else dict(patch)
        await self.bus.emit(
            Event(
                kind=EventKind.READING,
                data={
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    **payload,
                    **meta,
                },
            )
        )

    def has(self, name: str) -> bool:
        """Whether `get(name)` would succeed — a literal registered
        device, or a role with an active alias (`register_alias`). Lets a
        role-based template check an *optional* role (see
        `REQUIRED_INSTRUMENTS`'s `"optional": True`,
        core/workflow/instrument_roles.py) is actually bound before
        calling `get()` on it, without relying on a try/except KeyError."""
        return name in self.devices or name in (_aliases_var.get() or {})

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
        aliases = _aliases_var.get() or {}
        if name not in self.devices and name in aliases:
            name = aliases[name]
        if name not in self.devices:
            available = ", ".join(self.devices.keys())
            raise KeyError(
                f"Device '{name}' not found in session. "
                f"Available devices: {available or 'none'}"
            )
        return self.devices[name]

    async def execute(self, plan: Any) -> dict[str, Any]:
        """Run a plan to completion and return its result.

        The scripting entry point: `await session.execute(plan)` is what a
        template, the console and a notebook all call, and it is the same
        object in each. Replaces `Session.run(plan)`, which drove
        `core/plans/scan.py` — a second, orphaned scan engine that no REST
        route, template or UI ever reached, whose cancellation checks were
        no-ops precisely because nothing ran them.

        `pause()`, `resume()` and `abort()` live on the `Run`
        (`core/run/run.py`) rather than here, because they need the loop
        between points to mean anything. The versions that used to sit on
        this class moved the FSM and nothing else, which their own
        docstrings admitted.
        """
        from labpilot.core.run import execute as _execute

        return await _execute(self, plan)

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
