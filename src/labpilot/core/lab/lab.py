"""`Lab` — which instruments exist, and which of them are live.

"Which instruments does this system have" used to be spread across six
places that agreed only by convention: `Session.devices`, the role aliases,
`DashboardManager.instruments` (a dict of untyped dicts), the saved
instrument-set JSON, `lab_config.toml`, and each workflow's
`instrument_bindings`. Nothing owned the question, so each answer drifted
from the others — most visibly when a runtime write was stored onto the
saved configuration, because the two had no separate representation.

`Lab` owns it. It holds one `InstrumentHandle` per configured instrument,
persists the `InstrumentSpec` half and only that half, and mirrors
connected instruments into the `Session` so a workflow script can resolve
them by id. Three things follow that were not true before:

- **A runtime fact cannot be saved.** Only specs are written, and a spec
  has no field for status, position or last-connected time.
- **A handle is a stable identity.** `lab["stage"]` is the same object
  each time, so the manager UI, the console and a workflow binding refer
  to one instrument rather than three lookups.
- **Saving happens when the configuration changes**, not on every connect,
  action and write. Connecting an instrument no longer rewrites the file.

`bind()` is here too, and delegates to the session's role aliases, which
are task-scoped: two workflows that both bind the role "detector" get
their own binding rather than the last writer's.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Any, Iterator, Mapping

from labpilot.core.config.instrument_sets import (
    InstrumentSetError,
    InstrumentSetPersistence,
)
from labpilot.core.lab.handle import InstrumentHandle
from labpilot.core.lab.spec import InstrumentSpec
from labpilot.instruments import INSTRUMENT_CATALOG
from labpilot.instruments.factory import create_adapter

if TYPE_CHECKING:
    from labpilot.core.session import Session

__all__ = ["Lab", "UnknownInstrumentError"]


class UnknownInstrumentError(KeyError):
    """No instrument with that id. Names the near misses, because ids carry
    a numeric suffix (`fake_apd_2`, not `fake_apd`) and asking for the
    adapter's own name is the usual mistake."""

    def __str__(self) -> str:  # KeyError otherwise reprs the message
        return str(self.args[0]) if self.args else ""


def _dimensionality(adapter_key: str) -> str:
    """The catalogue's 0D/1D/2D/ND label for an adapter, if it has one."""
    return next(
        (
            entry.instrument_type.value.split("_")[-1].upper()
            for entry in INSTRUMENT_CATALOG
            if entry.adapter_key == adapter_key
        ),
        "0D",
    )


class Lab:
    """The configured instruments, live where they are connected."""

    def __init__(
        self,
        store: InstrumentSetPersistence | None = None,
        session: Session | None = None,
    ) -> None:
        self._handles: dict[str, InstrumentHandle] = {}
        self.store = store if store is not None else InstrumentSetPersistence()
        self.active_config: str | None = None
        self.session = session

    def set_session(self, session: Session) -> None:
        """Attach the session that connected instruments are mirrored into."""
        self.session = session

    # --- Membership -------------------------------------------------------

    def __contains__(self, instrument_id: object) -> bool:
        return instrument_id in self._handles

    def __iter__(self) -> Iterator[InstrumentHandle]:
        return iter(self._handles.values())

    def __len__(self) -> int:
        return len(self._handles)

    def __getitem__(self, instrument_id: str) -> InstrumentHandle:
        return self.get(instrument_id)

    @property
    def ids(self) -> list[str]:
        return list(self._handles)

    def get(self, instrument_id: str) -> InstrumentHandle:
        """The handle for one instrument, or `UnknownInstrumentError`."""
        handle = self._handles.get(instrument_id)
        if handle is None:
            close = difflib.get_close_matches(instrument_id, self._handles, n=3, cutoff=0.4)
            hint = f" Did you mean {' or '.join(map(repr, close))}?" if close else ""
            raise UnknownInstrumentError(
                f"Instrument {instrument_id!r} not found.{hint} "
                f"{len(self._handles)} configured."
            )
        return handle

    def specs(self) -> list[InstrumentSpec]:
        """The persistent half of the current instrument set."""
        return [handle.spec for handle in self._handles.values()]

    # --- Lifecycle --------------------------------------------------------

    def add(self, spec: InstrumentSpec) -> InstrumentHandle:
        """Instantiate an instrument from its spec, disconnected.

        The adapter is built before the handle is stored, so a spec the
        factory rejects leaves the lab exactly as it was — including when
        this is re-pointing an existing instrument at new hardware.
        """
        adapter = create_adapter(spec.adapter_key, dict(spec.connection), name=spec.name)
        handle = InstrumentHandle(spec, adapter, _dimensionality(spec.adapter_key))
        self._handles[spec.id] = handle
        return handle

    def update_spec(self, instrument_id: str, spec: InstrumentSpec) -> InstrumentHandle:
        """Replace an instrument's spec in place, keeping its live adapter.

        For a change the running adapter can absorb — a startup setting,
        a rename. A new *connection* needs a new adapter: `add()` it.
        """
        handle = self.get(instrument_id)
        handle.spec = spec
        return handle

    async def connect(self, instrument_id: str) -> InstrumentHandle:
        """Connect an instrument and make it resolvable from a workflow."""
        handle = self.get(instrument_id)
        await handle.connect()
        self._register(handle)
        return handle

    async def disconnect(self, instrument_id: str) -> InstrumentHandle:
        handle = self.get(instrument_id)
        try:
            await handle.disconnect()
        finally:
            self._unregister(instrument_id)
        return handle

    async def remove(self, instrument_id: str) -> None:
        """Disconnect if needed, then forget the instrument entirely."""
        handle = self.get(instrument_id)
        if handle.connected:
            try:
                await handle.disconnect()
            except Exception:
                pass  # Remove it regardless — the caller asked it to go.
        self._unregister(instrument_id)
        del self._handles[instrument_id]

    async def clear(self) -> None:
        """Disconnect and drop every instrument — what switching configs does."""
        for instrument_id in list(self._handles):
            await self.remove(instrument_id)

    def bind(self, role: str, instrument_id: str) -> None:
        """Bind a workflow role to an instrument, for this task only.

        `session.get("detector")` then resolves to that instrument. Scoped
        to the calling asyncio task (see `Session.register_alias`), so two
        workflows binding the same role name do not overwrite each other.
        """
        self.get(instrument_id)  # fail on the typo, not at the first read
        if self.session is None:
            raise RuntimeError("Lab has no session to bind roles in")
        self.session.register_alias(role, instrument_id)

    def _register(self, handle: InstrumentHandle) -> None:
        if self.session is not None:
            # replace() rather than duplicate-error, so a reconnect works.
            self.session.unregister(handle.id)
            self.session.register(handle.adapter, name=handle.id)

    def _unregister(self, instrument_id: str) -> None:
        if self.session is not None:
            self.session.unregister(instrument_id)

    # --- Configurations ---------------------------------------------------

    def save(self) -> None:
        """Write the current specs to the active config, if there is one."""
        if self.active_config is None:
            return
        try:
            self.store.save(self.active_config, self.specs())
        except InstrumentSetError as e:
            print(f"⚠️  Could not save instrument config {self.active_config!r}: {e}")

    def save_as(self, name: str) -> None:
        """Snapshot the current instrument set under a new name, and make it
        active."""
        self.store.save(name, self.specs())
        self._activate(name)

    async def load(self, name: str) -> None:
        """Tear down the current instrument set and load a named config.

        Instruments that fail to instantiate are reported and skipped: one
        adapter whose vendor SDK is missing must not cost you the rest of
        the lab.
        """
        specs = self.store.load(name)  # raises InstrumentSetError if missing
        await self.clear()
        for spec in specs:
            try:
                self.add(spec)
            except Exception as e:
                print(f"❌ Could not load {spec.id!r} from config {name!r}: {e}")
        self._activate(name)

    async def new(self, name: str) -> None:
        """Start a new, empty named config; instruments added later save into it."""
        await self.clear()
        self.store.save(name, [])
        self._activate(name)

    async def import_specs(self, name: str, entries: list[Mapping[str, Any]]) -> None:
        """Save an uploaded config's entries under `name` and load it."""
        self.store.save(name, [InstrumentSpec.from_dict(e) for e in entries])
        await self.load(name)

    async def initialize(self, seed_manufacturer: str = "MockBasic") -> None:
        """Load the active config, or seed a fresh one from the catalogue.

        The seed comes from real adapter code in `instruments/`, never from
        a hardcoded list in `core/`.
        """
        active = self.store.get_active_name()
        if active is not None:
            try:
                await self.load(active)
                return
            except InstrumentSetError as e:
                print(f"⚠️  Could not load active config {active!r}, reseeding: {e}")

        for entry in INSTRUMENT_CATALOG:
            if entry.manufacturer != seed_manufacturer:
                continue
            spec = InstrumentSpec(
                id=entry.adapter_key,
                adapter_key=entry.adapter_key,
                name=entry.display_name,
            )
            try:
                self.add(spec)
            except Exception as e:
                print(f"❌ Failed to register {entry.display_name}: {e}")

        self._activate(InstrumentSetPersistence.DEFAULT_NAME)
        self.save()

    def _activate(self, name: str) -> None:
        self.active_config = name
        self.store.set_active_name(name)

    def __repr__(self) -> str:
        live = sum(1 for handle in self._handles.values() if handle.connected)
        return f"<Lab {len(self._handles)} instruments, {live} connected>"
