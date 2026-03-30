"""Base adapter class for wrapping third-party instrument libraries.

Adapters convert synchronous driver code (pymeasure, pylablib) into async LabPilot
Protocol implementations. All hardware calls are automatically offloaded to threads
via anyio.to_thread.run_sync().

This enables:
- Zero-blocking async/await API for all instruments
- No changes needed to third-party driver code
- Automatic integration with LabPilot Session + EventBus
- Type-safe protocols (Readable/Movable/Triggerable)
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

import anyio

from labpilot_core.device.protocols import Readable
from labpilot_core.device.schema import DeviceSchema

__all__ = ["AdapterBase", "adapter_registry"]


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

    @property
    @abstractmethod
    def schema(self) -> DeviceSchema:
        """Device schema describing capabilities and metadata.

        Returns:
            DeviceSchema with name, kind, readable/settable axes, units, limits, tags.
        """
        ...

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

    @staticmethod
    async def _to_thread(func, *args, **kwargs) -> Any:
        """Run synchronous function in thread pool.

        Uses anyio.to_thread.run_sync() which integrates with anyio's cancellation
        system. Cancelled tasks will attempt to interrupt the thread.

        Args:
            func: Synchronous callable to run in thread.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Return value of func.
        """
        return await anyio.to_thread.run_sync(func, *args, **kwargs)

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
        >>> from labpilot_core.adapters import adapter_registry
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
            Dict mapping adapter keys to DeviceSchema instances.

        Note:
            Creates temporary instances to get schemas. Does not connect.
        """
        schemas = {}
        for key, adapter_cls in self._registry.items():
            # Instantiate with no args - adapters must have no-arg __init__
            # or handle missing args gracefully for schema introspection
            try:
                instance = adapter_cls()
                schemas[key] = instance.schema
            except Exception:
                # Skip adapters that can't be instantiated without args
                continue
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
