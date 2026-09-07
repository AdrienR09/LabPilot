"""`InstrumentHandle` — one live instrument in this process.

The ephemeral half of the spec/handle split. A handle is a spec that has
been instantiated: it owns the adapter object, whether it is connected,
what it is doing right now and how it last failed. All of that is true only
of this process and this moment, which is precisely why none of it belongs
in `InstrumentSpec` and none of it is ever written to a config file.

It is also the identity a caller can hold on to. `lab["stage"]` returns the
same handle every time, so a console name, a UI panel and a workflow
binding all refer to one object rather than to three lookups that agree by
convention.

There is deliberately no lock here. The obvious place for one, and what the
roadmap sketched, is an `asyncio.Lock` per handle — but the race it would
guard (two reads interleaved on one VISA session) happens in the *driver*,
below the event loop, and `AdapterBase` already serialises there with a
`threading.Lock` taken inside the worker thread. A second lock at this
level would serialise callers that the first one already protects, and
would deadlock the one operation that must never wait: `stop()`, whose
entire job is to interrupt a move that is holding the device.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from labpilot.core.device.kinds import wrap as wrap_instrument
from labpilot.core.errors import NotConnectedError, UnsupportedOperationError

if TYPE_CHECKING:
    from labpilot.core.device.schema import DeviceSchema
    from labpilot.core.lab.spec import InstrumentSpec

__all__ = ["InstrumentHandle"]


class InstrumentHandle:
    """A live adapter, its spec, and its current runtime state."""

    def __init__(self, spec: InstrumentSpec, adapter: Any, dimensionality: str = "0D") -> None:
        self.spec = spec
        self.adapter = adapter
        self.dimensionality = dimensionality
        self.status: str = "idle"  # idle | busy | error
        self.error: str | None = None

    # --- Identity ---------------------------------------------------------

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def adapter_key(self) -> str:
        return self.spec.adapter_key

    @property
    def schema(self) -> DeviceSchema:
        return self.adapter.schema

    @property
    def kind(self) -> str:
        return self.adapter.schema.kind

    @property
    def connected(self) -> bool:
        return bool(self.adapter.connected)

    @property
    def device(self) -> Any:
        """The kind-typed wrapper — `Motor`, `Detector`, `Source`, ... — the
        same object `session.get()` hands a workflow script."""
        return wrap_instrument(self.adapter)

    # --- Operations -------------------------------------------------------
    #
    # Each sets `status`/`error` around the call, so "what is this
    # instrument doing" is a property of the handle rather than something
    # every caller remembers to record.

    async def connect(self) -> None:
        """Connect, then apply the spec's startup settings.

        The settings are applied here rather than at instantiation because
        most adapters only build their underlying instrument handle in
        `connect()` — before that there is nothing to write to. A settings
        failure is reported but does not fail the connection: the device
        *is* connected, and leaving it marked disconnected would be a
        worse lie than a stale setting.
        """
        self.status = "busy"
        self.error = None
        try:
            await self.adapter.connect()
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            raise
        if self.spec.defaults:
            try:
                await self.adapter.write(dict(self.spec.defaults))
            except Exception as e:
                print(f"⚠️  Could not apply saved settings for {self.id}: {e}")
        self.status = "idle"

    async def disconnect(self) -> None:
        self.status = "busy"
        try:
            await self.adapter.disconnect()
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            raise
        self.status = "idle"
        self.error = None

    async def read(self) -> dict[str, Any]:
        self._require_connected()
        return await self.adapter.read()

    def validate_write(self, values: dict[str, Any]) -> dict[str, Any]:
        """Check values against the schema's limits and choices, and return
        the coerced ones — without touching hardware, so a setting can be
        checked while the instrument is disconnected."""
        return self.adapter.validate_write(values)

    async def write(self, values: dict[str, Any]) -> None:
        self._require_connected()
        await self.adapter.write(values)

    async def set_staged(self, staged: bool) -> None:
        self._require_connected()
        await (self.adapter.stage() if staged else self.adapter.unstage())

    async def call(self, action: str) -> None:
        if action not in self.schema.actions:
            raise KeyError(f"Instrument {self.id} declares no action {action!r}")
        self._require_connected()
        await getattr(self.adapter, action)()

    async def stop(self) -> None:
        """Stop a moving instrument where it is.

        Not gated on anything this handle holds: a stop that queues behind
        the move it is meant to interrupt is not a stop.
        """
        self._require_connected()
        stop = getattr(self.device, "stop", None)
        if stop is None:
            raise UnsupportedOperationError(
                f"{self.id} is not something that moves, so it cannot be stopped",
                device=self.id,
            )
        await stop()

    def _require_connected(self) -> None:
        if not self.connected:
            raise NotConnectedError(f"{self.id} is not connected", device=self.id)

    def __repr__(self) -> str:
        state = "connected" if self.connected else "disconnected"
        return f"<InstrumentHandle {self.id!r} {self.adapter_key} {state}>"
