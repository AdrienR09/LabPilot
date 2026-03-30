"""Serial device driver base with anyio async wrapping.

Provides async wrappers around pyserial blocking I/O operations using
anyio.to_thread.run_sync(). All serial-based drivers should inherit from
SerialDriver.
"""

from __future__ import annotations

from typing import Any

import anyio

from labpilot_core.drivers._base import BaseDriver

__all__ = ["SerialDriver"]


class SerialDriver(BaseDriver):
    """Base class for pyserial-based drivers with async I/O.

    Wraps all pyserial blocking calls with anyio.to_thread.run_sync() to
    prevent blocking the async event loop.

    Example:
        >>> class ThorlabsStage(SerialDriver):
        ...     schema = DeviceSchema(...)
        ...
        ...     async def read(self):
        ...         response = await self._read_until(b'>')
        ...         return {"position": float(response)}
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
        **kwargs: Any,
    ) -> None:
        """Initialize serial driver.

        Args:
            port: Serial port name (e.g., "/dev/ttyUSB0", "COM3").
            baudrate: Baud rate (bits/s).
            timeout: Read timeout in seconds.
            **kwargs: Additional arguments passed to serial.Serial().
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial_kwargs = kwargs
        self._serial: Any = None  # serial.Serial instance

    async def connect(self) -> None:
        """Open serial connection.

        Raises:
            ImportError: If pyserial not installed.
            ConnectionError: If port not found or busy.
        """
        try:
            import serial
        except ImportError as e:
            raise ImportError(
                "pyserial not installed. Install with: pip install 'labpilot[serial]'"
            ) from e

        def _connect() -> Any:
            """Blocking serial connection (runs in thread)."""
            return serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                **self._serial_kwargs,
            )

        try:
            self._serial = await anyio.to_thread.run_sync(_connect)
            self._connected = True
        except Exception as e:
            raise ConnectionError(
                f"Failed to open serial port '{self.port}': {e}"
            ) from e

    async def disconnect(self) -> None:
        """Close serial connection."""
        if self._serial is not None:

            def _disconnect() -> None:
                """Blocking serial disconnect (runs in thread)."""
                try:
                    self._serial.close()
                except Exception:
                    pass

            await anyio.to_thread.run_sync(_disconnect)
            self._serial = None

        self._connected = False

    async def _write(self, data: bytes) -> None:
        """Write bytes to serial port.

        Args:
            data: Bytes to write.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected to serial port")

        await anyio.to_thread.run_sync(self._serial.write, data)

    async def _read(self, size: int = 1) -> bytes:
        """Read bytes from serial port.

        Args:
            size: Number of bytes to read.

        Returns:
            Received bytes (may be less than size if timeout occurs).

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected to serial port")

        return await anyio.to_thread.run_sync(self._serial.read, size)

    async def _read_until(self, terminator: bytes = b"\n") -> bytes:
        """Read until terminator character.

        Args:
            terminator: Byte sequence marking end of message.

        Returns:
            Received bytes including terminator.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected to serial port")

        return await anyio.to_thread.run_sync(self._serial.read_until, terminator)

    async def _readline(self) -> bytes:
        """Read until newline character.

        Returns:
            Received bytes including newline.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected to serial port")

        return await anyio.to_thread.run_sync(self._serial.readline)

    async def _flush_input(self) -> None:
        """Discard all bytes in input buffer.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected to serial port")

        await anyio.to_thread.run_sync(self._serial.reset_input_buffer)

    async def _flush_output(self) -> None:
        """Wait for all bytes in output buffer to be transmitted.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected to serial port")

        await anyio.to_thread.run_sync(self._serial.flush)
