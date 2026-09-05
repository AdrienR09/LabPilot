"""Base adapter class for wrapping third-party instrument libraries.

Adapters convert synchronous driver code (pymeasure, pylablib) into async LabPilot
Protocol implementations. All hardware calls are automatically offloaded to threads
via anyio.to_thread.run_sync().

This enables:
- Zero-blocking async/await API for all instruments
- No changes needed to third-party driver code
- Automatic integration with LabPilot Session + EventBus
- One `Readable` protocol, plus a schema that says what each device can do
"""

from __future__ import annotations

import functools
import inspect
import threading
from abc import abstractmethod
from typing import Any

import anyio

from labpilot.core.device.protocols import Readable
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import (
    NotSettableError,
    UnsupportedOperationError,
)

__all__ = ["AdapterBase", "adapter_registry"]


# Placeholder values for a probe construction, by parameter annotation.
# Only ever reach a disconnected object that is thrown away — see
# `AdapterBase.describe`.
_PLACEHOLDERS: dict[Any, Any] = {
    str: "", int: 0, float: 0.0, bool: False,
}


def _placeholder_kwargs(cls: type) -> dict[str, Any]:
    """Arguments that let `cls` be constructed for schema introspection.

    Every required parameter of `__init__` gets a value inferred from its
    annotation (`resource: str` -> `""`), defaulting to `""` — which is
    what an unannotated `resource` in a hand-written adapter almost always
    wants. Parameters with defaults are left alone so the adapter's own
    defaults (notably `name`) are what shows up in the schema.
    """
    try:
        signature = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return {}

    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD
        ):
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        annotation = parameter.annotation
        if isinstance(annotation, str):
            # `from __future__ import annotations` is in force across the
            # adapter tree, so annotations arrive as source text. Matching
            # the few scalar spellings by name avoids resolving them, which
            # would need each adapter module's globals and could import
            # driver types that are not installed.
            annotation = {"str": str, "int": int, "float": float, "bool": bool}.get(
                annotation.strip(), str
            )
        kwargs[name] = _PLACEHOLDERS.get(annotation, "")
    return kwargs


class AdapterBase(Readable):
    """Base class for all instrument adapters.

    Adapters wrap third-party instrument drivers and expose them via LabPilot
    protocols. Key responsibilities:

    1. Schema definition - describe device capabilities via DeviceSchema
    2. Sync → Async wrapping - use _to_thread() for all hardware calls
    3. Connection lifecycle - implement connect() / disconnect()
    4. Protocol methods - implement read(), stage(), unstage(), etc.

    Subclasses must implement:
    - schema (property) - DeviceSchema describing this device
    - _connect_sync() - synchronous connection logic
    - _disconnect_sync() - synchronous disconnection logic
    - _read_sync() - synchronous read implementation
    - _stage_sync() / _unstage_sync() - setup/teardown logic

    Example subclass:
        >>> class Keithley2400Adapter(AdapterBase):
        ...     def __init__(self, resource: str):
        ...         self._resource = resource
        ...         self._instrument: Keithley2400 | None = None
        ...
        ...     @property
        ...     def schema(self) -> DeviceSchema:
        ...         return DeviceSchema(
        ...             name="keithley_2400",
        ...             kind="source",
        ...             readable={"voltage": "float64", "current": "float64"},
        ...             settable={"voltage": "float64"},
        ...             units={"voltage": "V", "current": "A"},
        ...             limits={"voltage": (-210.0, 210.0)},
        ...             tags=["Keithley", "SMU", "VISA"],
        ...         )
        ...
        ...     def _connect_sync(self) -> None:
        ...         self._instrument = Keithley2400(self._resource)
        ...
        ...     def _disconnect_sync(self) -> None:
        ...         if self._instrument:
        ...             self._instrument.shutdown()
        ...
        ...     def _read_sync(self) -> dict[str, Any]:
        ...         return {
        ...             "voltage": float(self._instrument.voltage),
        ...             "current": float(self._instrument.current),
        ...         }
    """

    def __init__(self) -> None:
        """Initialize adapter in disconnected state."""
        self._connected = False
        # Serialises every hardware call on this device. anyio's thread pool
        # is process-global (40 workers by default) and imposes no per-device
        # ordering, so two concurrent read()s on one VISA session — a poller
        # and a workflow, say — could interleave a write and a read on the
        # same connection. One lock per adapter instance makes each device's
        # traffic sequential while leaving different devices fully parallel.
        #
        # A threading.Lock, taken *inside* the worker thread, rather than an
        # asyncio.Lock around the await: asyncio primitives are bound to the
        # loop that first awaits them, and an adapter is legitimately reached
        # from more than one loop (the server's, and the workflow runner's own
        # — see core/workflow/engine.py). Holding it on the worker thread also
        # means a queued call never blocks an event loop.
        self._io_lock = threading.Lock()

    @property
    @abstractmethod
    def schema(self) -> DeviceSchema:
        """Device schema describing capabilities and metadata.

        Returns:
            DeviceSchema with name, kind, readable/settable axes, units, limits, tags.
        """
        ...

    @classmethod
    def describe(cls) -> DeviceSchema | None:
        """This adapter's schema without a live instance, or None.

        `adapter_registry.list_with_schemas()` used to call `cls()` with no
        arguments inside a bare try/except, so it saw the schema of **90 of
        301 adapters** — every adapter needing a `resource=` argument (i.e.
        every VISA instrument) simply vanished, and `search(tags=)`, which
        is built on it, structurally could not find one.

        The fix is to supply placeholder arguments rather than none.
        Adapters in this repo follow a strict rule: `__init__` records its
        arguments and `_connect_sync` opens the connection, so constructing
        one touches no hardware and a nonsense resource string is
        harmless — the object is discarded without ever being connected.
        `tests/test_adapter_contracts.py` asserts that holds for every
        registered adapter.

        Override this in an adapter whose schema genuinely cannot be known
        without hardware; returning None means "not describable offline"
        and the caller will simply omit it.
        """
        cached = cls.__dict__.get("_described_schema")
        if cached is not None:
            return cached[0]
        try:
            schema = cls(**_placeholder_kwargs(cls)).schema
        except Exception:
            schema = None
        # Cached on the class itself (not an inherited attribute) — one
        # probe construction per adapter class, not per listing call, and
        # the listing is on the instrument-browser path.
        cls._described_schema = (schema,)
        return schema

    async def connect(self) -> None:
        """Establish hardware connection (async wrapper).

        Calls _connect_sync() in a thread pool. Safe to call multiple times.

        Raises:
            ConnectionError: If hardware not found or communication fails.
            TimeoutError: If connection attempt times out.
        """
        if not self._connected:
            await self._to_thread(self._connect_sync)
            self._connected = True

    async def disconnect(self) -> None:
        """Close hardware connection (async wrapper).

        Calls _disconnect_sync() in a thread pool. Safe to call multiple times
        and even if connect() failed.
        """
        if self._connected:
            await self._to_thread(self._disconnect_sync)
            self._connected = False

    async def read(self) -> dict[str, Any]:
        """Read current device state (async wrapper).

        Returns:
            Dict mapping axis names to values. Keys must match schema.readable.
        """
        return await self._to_thread(self._read_sync)

    def validate_write(self, values: dict[str, Any]) -> dict[str, Any]:
        """Check a write against this device's schema; return it coerced.

        Every value is checked against its own `Parameter` — that the
        parameter exists, that it is settable, that the value is of the
        right type, within `limits`, and among `choices` — and returned
        converted to the declared element type (so the integer `5`
        arriving from JSON for a float parameter becomes `5.0`).

        Nothing enforced limits before this. `DeviceSchema.limits` was
        declared by a number of adapters and checked by exactly two mock
        ones, by hand; a real adapter would forward an out-of-range
        setpoint straight to hardware. Validating here rather than in each
        `set_<key>` means every adapter gets it, including the 209 that
        are generated.

        Subclasses that override `write()` (because their settings API
        doesn't fit the `set_<key>` convention) should call this first —
        it is public for exactly that reason.

        Raises:
            UnknownParameterError: no parameter of that name.
            NotSettableError: the parameter is read-only.
            LimitError / ChoiceError / ParameterError: bad value.
        """
        schema = self.schema
        checked: dict[str, Any] = {}
        for key, value in values.items():
            parameter = schema.require(key)
            if not parameter.settable:
                raise NotSettableError(
                    f"{key!r} on {schema.name!r} is read-only",
                    device=schema.name, parameter=key,
                )
            checked[key] = parameter.validate(value, device=schema.name)
        return checked

    async def write(self, values: dict[str, Any]) -> None:
        """Write one or more settable parameters (async wrapper).

        Validates via `validate_write()`, then dispatches each key to a
        same-named `set_<key>(value)` coroutine method on this adapter —
        the convention every adapter in instruments/test_fixtures.py and
        instruments/mock/ already follows for its schema.settable keys
        (e.g. a schema declaring `settable={"position": ...}` pairs with an
        `async def set_position(self, value)`). Subclasses whose settings
        API doesn't fit this convention (e.g. wrapping a third-party object
        with a different settings API, or preferring the narrower
        a narrower `set()` method instead) should override this method
        entirely — and call `validate_write()` themselves.

        Args:
            values: Dict mapping parameter names (must be settable in
                this device's schema) to their new values.

        Raises:
            ParameterError: See `validate_write()`.
            UnsupportedOperationError: If this adapter defines no matching
                `set_<key>` method for one of `values`' keys.
        """
        for key, value in self.validate_write(values).items():
            setter = getattr(self, f"set_{key}", None)
            if setter is None:
                raise UnsupportedOperationError(
                    f"{type(self).__name__} has no set_{key}() method — "
                    f"cannot write '{key}' generically",
                    device=self.schema.name,
                )
            await setter(value)

    async def stage(self) -> None:
        """Prepare device for acquisition (async wrapper)."""
        await self._to_thread(self._stage_sync)

    async def unstage(self) -> None:
        """Clean up after acquisition (async wrapper)."""
        await self._to_thread(self._unstage_sync)

    async def self_test(self) -> bool:
        """Test device connectivity without affecting hardware state.

        Returns:
            True if device responds correctly, False otherwise.
        """
        try:
            await self._to_thread(self._self_test_sync)
            return True
        except Exception:
            return False

    # --- Synchronous implementations (subclasses override these) ---

    @abstractmethod
    def _connect_sync(self) -> None:
        """Connect to hardware (synchronous, runs in thread).

        Raises:
            ConnectionError: If hardware not found or communication fails.
        """
        ...

    @abstractmethod
    def _disconnect_sync(self) -> None:
        """Disconnect from hardware (synchronous, runs in thread)."""
        ...

    @abstractmethod
    def _read_sync(self) -> dict[str, Any]:
        """Read device state (synchronous, runs in thread).

        Returns:
            Dict of axis_name -> value matching schema.readable.
        """
        ...

    def _stage_sync(self) -> None:
        """Setup before acquisition (synchronous, runs in thread).

        Default: no-op. Override if device needs setup (e.g., start_acquisition).
        """
        pass

    def _unstage_sync(self) -> None:
        """Teardown after acquisition (synchronous, runs in thread).

        Default: no-op. Override if device needs cleanup (e.g., stop_acquisition).
        """
        pass

    def _self_test_sync(self) -> None:
        """Test connectivity (synchronous, runs in thread).

        Default: perform a read. Override for custom test logic.
        Must NOT change hardware state (no motion, no writes).
        """
        _ = self._read_sync()

    # --- Utility ---

    async def _to_thread(self, func, *args, **kwargs) -> Any:
        """Run synchronous function in thread pool, serialised per device.

        Uses anyio.to_thread.run_sync() which integrates with anyio's cancellation
        system. Cancelled tasks will attempt to interrupt the thread.

        An instance method rather than a staticmethod so it can take this
        adapter's own I/O lock — see __init__.

        Args:
            func: Synchronous callable to run in thread.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Return value of func.
        """
        # anyio.to_thread.run_sync only accepts *args for the wrapped
        # function — it has no keyword-argument passthrough of its own
        # (any-kwargs here would instead be parsed as run_sync's own
        # abandon_on_cancel/limiter options and raise TypeError, found by
        # an adapter actually calling this with a keyword argument for
        # func, e.g. pylablib's set_voltage(value, channel="x")). Binding
        # kwargs via partial() first makes func a zero-kwarg callable so
        # they reach the intended function instead.
        if kwargs:
            func = functools.partial(func, **kwargs)

        lock = self._io_lock

        def _locked_call(*call_args):
            with lock:
                return func(*call_args)

        return await anyio.to_thread.run_sync(_locked_call, *args)

    @property
    def connected(self) -> bool:
        """Check if adapter is connected to hardware."""
        return self._connected


# --- Global adapter registry ---

class AdapterRegistry:
    """Global registry mapping adapter keys to adapter classes.

    Populated via auto-discovery on import and explicit register() calls.
    Used by:
    - Session to instantiate adapters from config
    - AI context builder to list available instruments
    - UI to show instrument browser

    Example usage:
        >>> from instruments import adapter_registry
        >>> adapter_cls = adapter_registry.get("keithley_2400")
        >>> adapter = adapter_cls(resource="GPIB::24")
        >>> await adapter.connect()
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._registry: dict[str, type[AdapterBase]] = {}

    def register(self, key: str, adapter_cls: type[AdapterBase]) -> None:
        """Register adapter class under a unique key.

        Args:
            key: Unique adapter identifier (e.g., "keithley_2400").
            adapter_cls: Adapter class (must inherit from AdapterBase).

        Raises:
            ValueError: If key already registered.
            TypeError: If adapter_cls does not inherit from AdapterBase.
        """
        if key in self._registry:
            raise ValueError(
                f"Adapter '{key}' already registered to {self._registry[key]}"
            )
        if not issubclass(adapter_cls, AdapterBase):
            raise TypeError(
                f"Adapter class {adapter_cls} must inherit from AdapterBase"
            )
        self._registry[key] = adapter_cls

    def get(self, key: str) -> type[AdapterBase]:
        """Get adapter class by key.

        Args:
            key: Adapter identifier.

        Returns:
            Adapter class.

        Raises:
            KeyError: If key not found in registry.
        """
        return self._registry[key]

    def list(self) -> dict[str, type[AdapterBase]]:
        """List all registered adapters.

        Returns:
            Dict mapping keys to adapter classes.
        """
        return self._registry.copy()

    def list_with_schemas(self) -> dict[str, DeviceSchema]:
        """List all adapters with their schemas.

        Returns:
            Dict mapping adapter keys to DeviceSchema instances. Adapters
            whose schema cannot be determined without hardware are omitted.

        Note:
            Creates temporary, never-connected instances — see
            `AdapterBase.describe`, which also caches per class.
        """
        schemas = {}
        for key, adapter_cls in self._registry.items():
            schema = adapter_cls.describe()
            if schema is not None:
                schemas[key] = schema
        return schemas

    def search(self, tags: list[str]) -> dict[str, DeviceSchema]:
        """Search adapters by tags.

        Args:
            tags: List of tags to search for (e.g., ["camera", "Andor"]).

        Returns:
            Dict of matching adapters with their schemas.
        """
        results = {}
        all_schemas = self.list_with_schemas()
        for key, schema in all_schemas.items():
            if any(tag in schema.tags for tag in tags):
                results[key] = schema
        return results


# Global singleton registry
adapter_registry = AdapterRegistry()
