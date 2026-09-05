"""Kind-typed instrument wrappers — the object-oriented scripting surface.

`Session.get(role)` (core/session.py) returns one of these instead of the
raw adapter, chosen by `wrap()` from the bound adapter's own
`schema.kind` — every adapter already declares this today (see
core/device/schema.py), so no adapter needs to change to get wrapped. Each
wrapper is built entirely on the existing generic `read()`/`write()`/
`stage()`/`unstage()` contract (`instruments/_base.py`'s `AdapterBase`) plus
`__getattr__` passthrough, so it adds ergonomic per-kind methods
(`move_abs()`, `get_position()`, `read_value()`, ...) without taking
anything away: every existing workflow template/capability class that calls
`.read()`/`.write()`/`.schema` directly on a `session.get()` result keeps
working completely unmodified.

Lives under `core/device/` (alongside `motion.py`, for the same reason —
see that module's docstring) rather than under `instruments/`, even though
conceptually it's about instruments: importing ANY submodule under
`instruments.` runs `instruments/__init__.py`, which eagerly
auto-discovers (imports) every adapter module in the whole tree, including
real hardware driver wrappers. That's fine for something that already needs
a live instrument (`core/api/dashboard.py` already pays this cost), but
`core/session.py` needs this module unconditionally at its OWN import
time — far earlier/broader than dashboard.py's usage. Confirmed via a real
pytest regression during development: putting this module under
`instruments/` made a plain `import core.session` (e.g. a lightweight test
process that never touches real hardware) silently trigger full adapter
discovery too, which surfaced an already-latent resource leak in that
discovery (some driver import leaves an unclosed socket/event loop) as a
newly-deterministic test failure. `Scanner`'s own need for
`instruments.hardware_scan_mixin.HardwareScanMixin` is satisfied with a
local import inside `wrap()` instead, deferred until an actual
`kind="generic"` instrument is being wrapped — by then, something has
necessarily already imported `instruments` for real (there'd be no adapter
to wrap otherwise), so this adds no new eager cost.

Generalizes two existing-but-unused precedents in this codebase:
`instruments/mixins.py`'s `MotorMixin`/`DetectorMixin`/`SourceMixin` (opt-in
per-adapter sugar over read/write, single-axis-only for motors — adopted by
zero adapters), and `instruments/hardware_scan_mixin.py`'s
`HardwareScanMixin` (a real, currently-used typed contract for hardware-timed
scanners). Rather than requiring each adapter to opt in, `wrap()` makes the
generic surface available to every adapter automatically, since `schema.kind`
is already mandatory metadata.

See docs/scripting.md for the full per-kind method reference.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from labpilot.core.device.motion import move_and_settle
from labpilot.core.errors import UnsupportedOperationError

__all__ = ["Motor", "Detector", "Source", "Scanner", "GenericInstrument", "wrap"]


def _numeric_axes(schema) -> list[str]:
    """Axis names this device can both read back and command.

    Now just the parameters the adapter's schema marks `role=POSITION` —
    which is where the "readable and settable and not a bool" rule this
    used to reimplement has moved (`Parameter.from_legacy`). Two things
    changed with it: a motor's velocity or step size is no longer offered
    as something to move (it is a SETTING, so `MockBasicActuator1D`'s
    single axis is now genuinely single), and an adapter that knows its
    own axes can declare them outright instead of being inferred at."""
    return list(schema.position_axes)


class _InstrumentWrapper:
    """Base: holds the real adapter, exposes the same surface it always
    had (`schema`, `connected`, `read()`/`write()`/`stage()`/`unstage()`/
    `connect()`/`disconnect()`), and delegates anything else (adapter-
    specific extras, `schema.actions` methods like `cw_on()`) via
    `__getattr__` — so nothing a caller could already do with the raw
    adapter stops working once it's wrapped."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    @property
    def schema(self):
        return self._adapter.schema

    @property
    def connected(self) -> bool:
        return self._adapter.connected

    async def connect(self) -> None:
        await self._adapter.connect()

    async def disconnect(self) -> None:
        await self._adapter.disconnect()

    async def read(self) -> dict[str, Any]:
        return await self._adapter.read()

    async def write(self, values: dict[str, Any]) -> None:
        await self._adapter.write(values)

    async def stage(self) -> None:
        await self._adapter.stage()

    async def unstage(self) -> None:
        await self._adapter.unstage()

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes not defined above/on the subclass —
        # normal Python attribute lookup order, not overriding anything.
        return getattr(self._adapter, name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._adapter.schema.name!r})"


class Motor(_InstrumentWrapper):
    """A `kind="motor"` device — one or more continuous, settable axes.
    `get_position()`/`move_abs()`/`move_rel()` degrade to a single-value
    calling convention for a genuinely single-axis device (e.g.
    `MockMotor`'s "position"), and require naming the axis for a
    multi-axis one (e.g. `MockXYZStage`'s x/y/z) — see docs/scripting.md
    for worked examples of both."""

    @property
    def axes(self) -> list[str]:
        return _numeric_axes(self._adapter.schema)

    async def get_position(self, axis: Optional[str] = None) -> Union[float, dict[str, float]]:
        data = await self._adapter.read()
        axes = self.axes
        if axis is not None:
            if axis not in axes:
                raise KeyError(f"'{axis}' is not a numeric axis of {self._adapter.schema.name} (axes: {axes})")
            return float(data[axis])
        if len(axes) == 1:
            return float(data[axes[0]])
        return {ax: float(data[ax]) for ax in axes}

    async def move_abs(
        self, *args: Any, tolerance: float = 0.02, max_polls: int = 5000, **kwargs: float,
    ) -> Union[float, dict[str, float]]:
        """Three equivalent calling conventions:
        `move_abs(5.0)` (only valid for a single-axis device),
        `move_abs("x", 5.0)`, or `move_abs(x=5.0, y=2.0)` (any subset of
        axes, moved together). Blocks until settled (or raises
        RuntimeError — see `core.device.motion.move_and_settle`)."""
        targets = self._resolve_targets(args, kwargs)
        position = await move_and_settle(self._adapter, targets, tolerance, max_polls)
        if len(targets) == 1:
            axis = next(iter(targets))
            return float(position[axis])
        return {ax: float(position[ax]) for ax in targets}

    async def move_rel(
        self, *args: Any, tolerance: float = 0.02, max_polls: int = 5000, **kwargs: float,
    ) -> Union[float, dict[str, float]]:
        """Same calling conventions as `move_abs()`, but each value is a
        delta from the device's current position rather than an absolute
        target."""
        deltas = self._resolve_targets(args, kwargs)
        current = await self._adapter.read()
        targets = {ax: current[ax] + delta for ax, delta in deltas.items()}
        position = await move_and_settle(self._adapter, targets, tolerance, max_polls)
        if len(targets) == 1:
            axis = next(iter(targets))
            return float(position[axis])
        return {ax: float(position[ax]) for ax in targets}

    def _resolve_targets(self, args: tuple, kwargs: dict) -> dict[str, float]:
        axes = self.axes
        if kwargs:
            return {k: float(v) for k, v in kwargs.items()}
        if len(args) == 2 and isinstance(args[0], str):
            return {args[0]: float(args[1])}
        if len(args) == 1:
            if len(axes) != 1:
                raise TypeError(
                    f"move_abs(value)/move_rel(value) need exactly one axis, but "
                    f"{self._adapter.schema.name} has {axes} — use move_abs(axis, value) "
                    f"or move_abs(**{{axis: value}}) instead"
                )
            return {axes[0]: float(args[0])}
        raise TypeError(
            "move_abs()/move_rel() need a value (single-axis device), an (axis, value) "
            "pair, or axis=value keyword arguments"
        )


class Detector(_InstrumentWrapper):
    """A `kind="detector"` (or `"counter"`) device."""

    async def acquire_once(self) -> dict[str, Any]:
        """stage -> read -> unstage, for one one-shot reading. Not
        appropriate around a whole averaged-sweep loop that needs to
        stay staged across many reads — call stage()/unstage() manually
        around that instead (see odmr_sweep.py)."""
        await self._adapter.stage()
        try:
            return await self._adapter.read()
        finally:
            await self._adapter.unstage()

    async def read_value(self, key: Optional[str] = None) -> float:
        """One scalar reading — `key` defaults to this detector's first
        readable key. Raises ValueError if that key's value isn't
        actually scalar (a 1D/2D/ND detector); use `.read()` directly and
        index into the array yourself in that case (see
        `core.workflow_templates._common.detector_axes`, which already
        handles an arbitrary-rank detector reading generically)."""
        data = await self._adapter.read()
        key = key or next(iter(self._adapter.schema.readable.keys()))
        value = data[key]
        if hasattr(value, "__len__"):
            raise ValueError(
                f"'{key}' on {self._adapter.schema.name} is not a scalar reading — use .read() directly"
            )
        return float(value)

    async def set_integration_time(self, ms: float) -> None:
        parameter = self._adapter.schema.integration_time
        if parameter is None:
            raise UnsupportedOperationError(
                f"{self._adapter.schema.name} declares no integration-time parameter",
                device=self._adapter.schema.name,
            )
        await self._adapter.write({parameter.name: ms})


class Source(_InstrumentWrapper):
    """A `kind="source"` device. Deliberately thin beyond passthrough:
    a generic `enable()`/`disable()` doesn't hold up against every real
    source (some use a zero-arg `schema.actions` method like `cw_on()`/
    `off()` instead of a settable on/off key, some have no on/off concept
    at all) — see docs/scripting.md. `.write({...})` for settable values
    and `.actions` (or calling the action name directly via passthrough)
    for everything else remain the real control surface."""

    @property
    def actions(self) -> list[str]:
        return self._adapter.schema.actions


class Scanner(_InstrumentWrapper):
    """A `kind="generic"` device that also implements
    `instruments.hardware_scan_mixin.HardwareScanMixin` (hardware-timed
    scanners, e.g. an NI DAQ card). A typed restatement of that mixin's
    4-method contract — `__getattr__` passthrough already reaches these
    same methods, so this adds no new behavior, only IDE-discoverability
    of the exact method set for this kind."""

    async def configure_scan(
        self, axes: list[str], ranges: dict[str, tuple[float, float]],
        resolution: dict[str, int], frequency: float,
    ) -> None:
        await self._adapter.configure_scan(axes, ranges, resolution, frequency)

    async def start_scan(self) -> None:
        await self._adapter.start_scan()

    async def get_scan_data(self) -> dict[str, Any]:
        return await self._adapter.get_scan_data()

    async def stop_scan(self) -> None:
        await self._adapter.stop_scan()


class GenericInstrument(_InstrumentWrapper):
    """Fallback for a `kind="generic"` device that isn't a hardware-timed
    scanner (e.g. a pulse sequencer) — no kind-specific methods beyond
    passthrough."""


def wrap(adapter: Any) -> _InstrumentWrapper:
    """Chooses the right wrapper for `adapter` based on its own
    `schema.kind` — called by `Session.get()`, not normally by a workflow
    script directly."""
    kind = adapter.schema.kind
    if kind == "motor":
        return Motor(adapter)
    if kind in ("detector", "counter"):
        return Detector(adapter)
    if kind == "source":
        return Source(adapter)
    if kind == "generic":
        # Local import — see this module's own docstring for why this
        # must not be a module-level import.
        from labpilot.instruments.hardware_scan_mixin import HardwareScanMixin
        return Scanner(adapter) if isinstance(adapter, HardwareScanMixin) else GenericInstrument(adapter)
    return GenericInstrument(adapter)
