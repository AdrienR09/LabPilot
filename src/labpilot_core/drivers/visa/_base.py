"""VISA driver base with anyio async wrapping.

Provides async wrappers around pyvisa blocking I/O operations using
anyio.to_thread.run_sync(). All VISA-based drivers should inherit from
VISADriver.
"""

from __future__ import annotations

from typing import Any

import anyio

from labpilot_core.drivers._base import BaseDriver

__all__ = ["VISADriver"]


class VISADriver(BaseDriver):
    """Base class for PyVISA-based drivers with async I/O.

    Wraps all pyvisa blocking calls with anyio.to_thread.run_sync() to
    prevent blocking the async event loop.

    Example:
        >>> class MyInstrument(VISADriver):
        ...     schema = DeviceSchema(...)
        ...
        ...     async def read(self):
        ...         response = await self._query("READ?")
        ...         return {"value": float(response)}
    """

    def __init__(self, resource: str, timeout: float = 5.0) -> None:
        """Initialize VISA driver.

        Args:
            resource: VISA resource string (e.g., "USB0::0x1313::0x8078::1::INSTR").
            timeout: Communication timeout in seconds.
        """
        super().__init__()
        self.resource = resource
        self.timeout = timeout
        self._instrument: Any = None  # pyvisa.resources.MessageBasedResource

    async def connect(self) -> None:
        """Open VISA connection using pyvisa-py backend.

        Raises:
            ImportError: If pyvisa not installed.
            ConnectionError: If resource not found or busy.
        """
        try:
            import pyvisa
        except ImportError as e:
            raise ImportError(
                "pyvisa not installed. Install with: pip install 'labpilot[visa]'"
            ) from e

        def _connect() -> Any:
            """Blocking VISA connection (runs in thread)."""
            rm = pyvisa.ResourceManager("@py")  # Use pyvisa-py backend
            inst = rm.open_resource(self.resource)
            inst.timeout = int(self.timeout * 1000)  # Convert to milliseconds
            return inst

        try:
            self._instrument = await anyio.to_thread.run_sync(_connect)
            self._connected = True
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to VISA resource '{self.resource}': {e}"
            ) from e

    async def disconnect(self) -> None:
        """Close VISA connection."""
        if self._instrument is not None:

            def _disconnect() -> None:
                """Blocking VISA disconnect (runs in thread)."""
                try:
                    self._instrument.close()
                except Exception:
                    pass  # Ignore errors during disconnect

            await anyio.to_thread.run_sync(_disconnect)
            self._instrument = None

        self._connected = False

    async def _write(self, command: str) -> None:
        """Write SCPI command to instrument.

        Args:
            command: SCPI command string.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._instrument is None:
            raise RuntimeError("Not connected to instrument")

        await anyio.to_thread.run_sync(self._instrument.write, command)

    async def _read(self) -> str:
        """Read response from instrument.

        Returns:
            Response string with whitespace stripped.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._instrument is None:
            raise RuntimeError("Not connected to instrument")

        response = await anyio.to_thread.run_sync(self._instrument.read)
        return response.strip()

    async def _query(self, command: str) -> str:
        """Write command and read response (query).

        Args:
            command: SCPI command string.

        Returns:
            Response string with whitespace stripped.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._instrument is None:
            raise RuntimeError("Not connected to instrument")

        response = await anyio.to_thread.run_sync(self._instrument.query, command)
        return response.strip()

    async def _read_binary(self) -> bytes:
        """Read binary data from instrument.

        Returns:
            Raw binary data bytes.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._instrument is None:
            raise RuntimeError("Not connected to instrument")

        return await anyio.to_thread.run_sync(self._instrument.read_raw)
