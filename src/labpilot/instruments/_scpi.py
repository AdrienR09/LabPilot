"""A minimal SCPI transport: raw TCP, or VISA when pyvisa is installed.

Nothing in this repo spoke SCPI directly before now — the 183 pymeasure
adapters let pymeasure do it, which means pymeasure (and therefore a VISA
backend) has to be installed for any of them. For a lab PC that only
needs to reach one bench instrument over the network, that is a lot of
installation for a text protocol over a socket.

So the default here is **raw TCP on port 5025**, the IEEE-standard
SCPI-over-LAN socket that Siglent, Keysight, Rohde & Schwarz and most
other bench instruments listen on. It needs nothing installed: the
instrument's IP address is the whole configuration, which is the right
answer for a machine that has just been unboxed.

VISA stays available for the instruments that only speak it (GPIB, USBTMC)
and is used when a `resource=` is given instead of a `host=`. pyvisa is
imported inside `open()`, like every other driver in this tree, so an
adapter remains describable and probeable on a machine that has never
had it.

Two details that matter more than they look:

- **Every exchange is one lock.** A query is a write followed by a read,
  and two of them interleaved on one socket returns the other's answer.
  `AdapterBase` already serialises per device, but this lock is held
  inside the transport so a driver that reaches it by another path cannot
  interleave either.
- **A query that times out raises rather than returning `""`.** An empty
  string parsed as a float is a `ValueError` several frames away from the
  cause; naming the command that went unanswered is the difference
  between a five-minute and an hour-long diagnosis.
"""

from __future__ import annotations

import contextlib
import socket
import threading
from typing import TYPE_CHECKING

from labpilot.core.errors import DeviceError, NotConnectedError

if TYPE_CHECKING:
    from typing import Any

__all__ = ["SCPI_PORT", "ScpiTransport"]

#: The port assigned to SCPI raw sockets; every instrument here uses it.
SCPI_PORT = 5025


class ScpiTransport:
    """One instrument's SCPI connection, over TCP or VISA.

    Synchronous by design: an adapter calls it from `_connect_sync` /
    `_read_sync`, which `AdapterBase` already runs on a worker thread.
    """

    def __init__(
        self,
        *,
        host: str = "",
        port: int = SCPI_PORT,
        resource: str = "",
        timeout: float = 5.0,
        device: str = "",
    ) -> None:
        if not host and not resource:
            raise ValueError("an SCPI instrument needs either host= or resource=")
        self.host = host
        self.port = int(port)
        self.resource = resource
        self.timeout = float(timeout)
        self.device = device
        self._socket: socket.socket | None = None
        self._visa: Any = None
        self._lock = threading.Lock()

    # --- Lifecycle --------------------------------------------------------

    def open(self) -> None:
        if self.resource:
            self._open_visa()
        else:
            self._open_tcp()

    def _open_tcp(self) -> None:
        try:
            self._socket = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
        except OSError as error:
            raise DeviceError(
                f"No SCPI instrument answered at {self.host}:{self.port} — {error}. "
                f"Check the address on the instrument's own LAN screen, and that "
                f"its remote interface is enabled.",
                device=self.device,
            ) from error

    def _open_visa(self) -> None:
        try:
            import pyvisa
        except ImportError as error:  # pragma: no cover - depends on the machine
            raise DeviceError(
                "A VISA resource string was given but pyvisa is not installed. "
                "Install pyvisa (plus a backend), or reach the instrument over "
                "the network with host= instead, which needs nothing.",
                device=self.device,
            ) from error
        try:
            self._visa = pyvisa.ResourceManager().open_resource(self.resource)
            self._visa.timeout = int(self.timeout * 1000)
        except Exception as error:
            raise DeviceError(
                f"VISA could not open {self.resource!r} — {error}", device=self.device
            ) from error

    def close(self) -> None:
        """Idempotent, and never raises: this runs from `_disconnect_sync`
        and from a `finally` after a failure, where a second exception
        would replace the one worth reading."""
        for handle in (self._socket, self._visa):
            if handle is not None:
                with contextlib.suppress(Exception):
                    handle.close()
        self._socket = self._visa = None

    @property
    def connected(self) -> bool:
        return self._socket is not None or self._visa is not None

    # --- Exchanges --------------------------------------------------------

    def write(self, command: str) -> None:
        """Send one command and expect no answer."""
        with self._lock:
            self._write(command)

    def query(self, command: str) -> str:
        """Send one command and return its answer, stripped.

        Locked as a unit — a write and a read that interleave with another
        exchange return each other's answers, and the values are plausible
        enough that nothing downstream notices.
        """
        with self._lock:
            self._write(command)
            return self._read(command)

    def query_float(self, command: str) -> float:
        """`query`, parsed. SCPI floats come back as `2.870000000E+09`."""
        answer = self.query(command)
        try:
            return float(answer)
        except ValueError as error:
            raise DeviceError(
                f"{command} answered {answer!r}, which is not a number",
                device=self.device,
            ) from error

    def query_bool(self, command: str) -> bool:
        """`ON`/`OFF` and `1`/`0` both occur, sometimes on one instrument."""
        answer = self.query(command).strip().upper()
        return answer in ("1", "ON", "TRUE")

    # --- The wire ---------------------------------------------------------

    def _write(self, command: str) -> None:
        if self._visa is not None:
            self._visa.write(command)
            return
        if self._socket is None:
            raise NotConnectedError(
                f"{command} was sent before the instrument was connected",
                device=self.device,
            )
        self._socket.sendall(f"{command}\n".encode("ascii"))

    def _read(self, command: str) -> str:
        if self._visa is not None:
            return str(self._visa.read()).strip()
        assert self._socket is not None  # _write would have raised
        chunks: list[bytes] = []
        while True:
            try:
                chunk = self._socket.recv(4096)
            except TimeoutError as error:
                raise DeviceError(
                    f"{command} went unanswered for {self.timeout:g} s. An empty "
                    f"answer parsed as a number fails far from here, so this "
                    f"stops at the command instead.",
                    device=self.device,
                ) from error
            if not chunk:
                raise DeviceError(
                    f"The instrument closed the connection during {command}",
                    device=self.device,
                )
            chunks.append(chunk)
            if chunk.endswith(b"\n"):
                break
        return b"".join(chunks).decode("ascii", "replace").strip()
