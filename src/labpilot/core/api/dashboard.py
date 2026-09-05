"""Dashboard API endpoints for LabPilot.

Provides browser-based dashboard for managing instruments and workflows:
- Pre-connected fake instruments organized by dimensionality
- Workflow execution and monitoring
- Real-time data streaming via WebSockets
- Block diagram visualization
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from labpilot.core.config import DeviceConfig
from labpilot.core.config.instrument_sets import (
    InstrumentSetError,
    InstrumentSetPersistence,
)
from labpilot.core.config.instrument_ui_prefs import (
    get_display_pref_schema,
    get_instrument_ui_prefs,
    set_instrument_ui_prefs,
)
from labpilot.core.errors import (
    NotConnectedError,
    ParameterError,
    UnsupportedOperationError,
)
from labpilot.core.session import Session
from labpilot.instruments import INSTRUMENT_CATALOG, adapter_registry, available_catalog
from labpilot.instruments.factory import UnknownAdapterError, create_adapter


def _jsonable_read(data: dict[str, Any]) -> dict[str, Any]:
    """Convert an adapter's read() dict (numpy arrays/scalars) to JSON-safe values."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, np.ndarray):
            result[key] = value.tolist()
        elif isinstance(value, np.generic):
            result[key] = value.item()
        else:
            result[key] = value
    return result


class InstrumentStatus(BaseModel):
    """Status of a connected instrument."""

    id: str
    name: str
    adapter_type: str
    kind: str  # detector or actuator
    dimensionality: str  # 0D, 1D, 2D, 3D
    tags: list[str]
    connected: bool
    status: str = "idle"  # idle | busy | error
    error: str | None = None
    data: dict[str, Any] | None = None
    connection_params: dict[str, Any] = {}
    custom_settings: dict[str, Any] = {}


class CreateInstrumentRequest(BaseModel):
    """Request to instantiate a new instrument from the catalog."""

    adapter_key: str  # e.g. "keithley_2400", must exist in adapter_registry
    id: str | None = None  # defaults to adapter_key + suffix if omitted
    name: str | None = None
    connection_params: dict[str, Any] = {}


class WriteSettingsRequest(BaseModel):
    """Request to set one or more of an instrument's settable parameters.

    `persist` distinguishes a configuration change (the Settings UI: remember
    this and restore it on the next connect) from an ordinary runtime write
    (a console loop or a jog control moving a stage). Defaults to True to keep
    the historical behaviour for existing callers; LabPilotClient.write()
    defaults to False, which is the right default for scripted motion.
    """

    values: dict[str, Any]
    persist: bool = True


class UIPrefsRequest(BaseModel):
    """Request to save an instrument's native-UI display preferences (see
    core/config/instrument_ui_prefs.py) — never written to the instrument
    itself."""

    prefs: dict[str, Any]


class UpdateConnectionRequest(BaseModel):
    """Request to replace an instrument's connection parameters."""

    connection_params: dict[str, Any]


class NewInstrumentConfigRequest(BaseModel):
    """Request to create a new, blank instrument-set config."""

    name: str


class UploadInstrumentConfigRequest(BaseModel):
    """Request to load a config from an uploaded file's contents."""

    name: str | None = None  # defaults to the name embedded in the file
    devices: list[dict[str, Any]] = []


class DashboardState(BaseModel):
    """Overall dashboard state. Workflows are a separate, real system —
    see core/workflow/ and the /api/workflows* routes in server.py."""

    instruments: list[InstrumentStatus]


class DashboardManager:
    """Manages dashboard state, instruments, and workflows."""

    def __init__(self):
        self.instruments: dict[str, Any] = {}  # id -> adapter instance
        self.websockets: list[WebSocket] = []
        self.instrument_data_streams: dict[str, asyncio.Task] = {}
        self.config_store = InstrumentSetPersistence()
        self.active_config_name: str | None = None
        # Set once at server startup (see server.py) so a connected
        # instrument is also resolvable by name from a workflow node
        # (WorkflowEngine reads through Session, not this dict) — optional
        # so this module stays usable standalone (e.g. in tests) without a
        # full server.
        self.session: Session | None = None

    def set_session(self, session: Session) -> None:
        """Attach the shared Session so connect/disconnect can mirror
        instrument availability into it (see connect_instrument/
        disconnect_instrument)."""
        self.session = session

    def _instantiate(self, adapter_key: str, instrument_id: str, name: str,
                      connection_params: dict[str, Any],
                      custom_settings: dict[str, Any] | None = None) -> None:
        """Instantiate one adapter and add it to self.instruments, disconnected.

        `custom_settings` (config-only settable params staged via the
        Settings UI, e.g. integration time) are remembered here even though
        they can't be written to hardware yet — connect_instrument() writes
        them the moment the adapter actually connects.
        """
        adapter = create_adapter(adapter_key, connection_params, name=name)
        dim = next(
            (m.instrument_type.value.split("_")[-1].upper() for m in INSTRUMENT_CATALOG
             if m.adapter_key == adapter_key),
            "0D",
        )
        self.instruments[instrument_id] = {
            "adapter": adapter,
            "name": name,
            "adapter_type": adapter_key,
            "connection_params": connection_params,
            "custom_settings": dict(custom_settings) if custom_settings else {},
            "dimensionality": dim,
            "schema": adapter.schema,
            "status": "idle",
            "error": None,
        }

    def _snapshot(self) -> list[DeviceConfig]:
        """Build DeviceConfig entries from the current live instrument set."""
        entries = []
        for inst_id, inst in self.instruments.items():
            entries.append(DeviceConfig(
                id=inst_id,
                name=inst["name"],
                adapter_type=inst["adapter_type"],
                connection_params=inst.get("connection_params", {}),
                custom_settings=inst.get("custom_settings", {}),
                status=inst.get("status"),
                last_connected=time.time() if inst["adapter"].connected else None,
            ))
        return entries

    def _save_active_config(self) -> None:
        """Persist the current instrument set under the active config name, if any."""
        if self.active_config_name is None:
            return
        try:
            self.config_store.save(self.active_config_name, self._snapshot())
        except InstrumentSetError as e:
            print(f"⚠️ Failed to save instrument config {self.active_config_name!r}: {e}")

    async def initialize_instruments(self):
        """Load the active instrument-set config, or seed a fresh "default"
        one from the catalog (instruments.MockBasic) if none exists yet.

        Either way, instruments come from real `instruments/` adapter code —
        never a hardcoded list living in `core/`.
        """
        active = self.config_store.get_active_name()
        if active is not None:
            try:
                await self.load_instrument_set(active)
                return
            except InstrumentSetError as e:
                print(f"⚠️ Failed to load active config {active!r}, reseeding: {e}")

        seed_manufacturer = "MockBasic"
        seed_entries = [m for m in INSTRUMENT_CATALOG if m.manufacturer == seed_manufacturer]
        for entry in seed_entries:
            try:
                self._instantiate(entry.adapter_key, entry.adapter_key, entry.display_name, {})
                print(f"✅ Registered {entry.display_name} ({entry.adapter_key}) - disconnected")
            except Exception as e:
                print(f"❌ Failed to register {entry.display_name}: {e}")

        self.active_config_name = InstrumentSetPersistence.DEFAULT_NAME
        self.config_store.set_active_name(self.active_config_name)
        self._save_active_config()

    async def load_instrument_set(self, name: str) -> None:
        """Tear down the current instrument set and load a named config."""
        for inst_id in list(self.instruments.keys()):
            adapter = self.instruments[inst_id]["adapter"]
            if adapter.connected:
                try:
                    await adapter.disconnect()
                except Exception:
                    pass
            if self.session is not None:
                self.session.unregister(inst_id)
        self.instruments.clear()

        entries = self.config_store.load(name)  # raises InstrumentSetError if missing/corrupt
        for entry in entries:
            try:
                self._instantiate(entry.adapter_type, entry.id or entry.name, entry.name,
                                   entry.connection_params, entry.custom_settings)
                print(f"✅ Loaded {entry.name} ({entry.id}) from config {name!r}")
            except Exception as e:
                print(f"❌ Failed to load {entry.name} from config {name!r}: {e}")

        self.active_config_name = name
        self.config_store.set_active_name(name)

    def save_instrument_set_as(self, name: str) -> None:
        """Snapshot the current instrument set to a (new or existing) named config
        and make it the active one."""
        self.config_store.save(name, self._snapshot())
        self.active_config_name = name
        self.config_store.set_active_name(name)

    async def create_blank_instrument_set(self, name: str) -> None:
        """Tear down the current instrument set and start a new, empty
        named config — instruments added afterward save into it."""
        for inst_id in list(self.instruments.keys()):
            adapter = self.instruments[inst_id]["adapter"]
            if adapter.connected:
                try:
                    await adapter.disconnect()
                except Exception:
                    pass
            if self.session is not None:
                self.session.unregister(inst_id)
        self.instruments.clear()

        self.config_store.save(name, [])
        self.active_config_name = name
        self.config_store.set_active_name(name)

    async def import_instrument_set(self, name: str, device_dicts: list[dict[str, Any]]) -> None:
        """Load an uploaded config's device list, save it under `name`, and
        make it active — same effect as `load_instrument_set`, but the
        source is an upload rather than an already-known config file."""
        entries = [DeviceConfig(**d) for d in device_dicts]
        self.config_store.save(name, entries)
        await self.load_instrument_set(name)

    def get_instrument_status(self, instrument_id: str) -> InstrumentStatus:
        """Get current status of an instrument."""
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        schema = inst["schema"]
        adapter = inst["adapter"]

        return InstrumentStatus(
            id=instrument_id,
            name=inst["name"],
            adapter_type=inst["adapter_type"],
            kind=schema.kind,
            dimensionality=inst["dimensionality"],
            tags=schema.tags,
            connected=adapter.connected,
            status=inst.get("status", "idle"),
            error=inst.get("error"),
            data=None,  # Will be populated by real-time stream
            connection_params=inst.get("connection_params", {}),
            custom_settings=inst.get("custom_settings", {}),
        )

    async def connect_instrument(self, instrument_id: str) -> InstrumentStatus:
        """Connect an instrument's adapter to real hardware.

        Any config values staged via write_instrument_settings() while
        disconnected (or loaded from a saved config) are applied right
        after — the earliest point a real adapter can actually accept a
        write, since most only construct their underlying `_instrument`
        handle in connect().
        """
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        inst["status"] = "busy"
        inst["error"] = None
        try:
            await inst["adapter"].connect()
            custom_settings = inst.get("custom_settings") or {}
            if custom_settings:
                try:
                    await inst["adapter"].write(custom_settings)
                except Exception as e:
                    print(f"⚠️ Failed to apply saved settings for {instrument_id}: {e}")
            inst["status"] = "idle"
            # Make this instrument resolvable by a workflow node
            # (AcquireNode.device / SetNode.device) under its dashboard id —
            # a no-op if no session is attached (see set_session()).
            if self.session is not None:
                self.session.unregister(instrument_id)  # replace(), not duplicate-error on reconnect
                self.session.register(inst["adapter"], name=instrument_id)
        except Exception as e:
            inst["status"] = "error"
            inst["error"] = str(e)
            raise
        finally:
            self._save_active_config()
            await self.broadcast_to_websockets({
                "type": "instrument_status",
                "instrument_id": instrument_id,
                "data": self.get_instrument_status(instrument_id).model_dump(),
            })
        return self.get_instrument_status(instrument_id)

    async def disconnect_instrument(self, instrument_id: str) -> InstrumentStatus:
        """Disconnect an instrument's adapter from hardware."""
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        inst["status"] = "busy"
        try:
            await inst["adapter"].disconnect()
            inst["status"] = "idle"
            inst["error"] = None
            if self.session is not None:
                self.session.unregister(instrument_id)
        except Exception as e:
            inst["status"] = "error"
            inst["error"] = str(e)
            raise
        finally:
            self._save_active_config()
            await self.broadcast_to_websockets({
                "type": "instrument_status",
                "instrument_id": instrument_id,
                "data": self.get_instrument_status(instrument_id).model_dump(),
            })
        return self.get_instrument_status(instrument_id)

    async def write_instrument_settings(
        self, instrument_id: str, values: dict[str, Any], *, persist: bool = True
    ) -> InstrumentStatus:
        """Set one or more of an instrument's settable parameters.

        With `persist` (the default, used by the Settings UI) the values are
        also remembered as custom_settings and written to the active
        instrument-set config, so they are restored the next time this
        instrument connects.

        `persist=False` is for ordinary runtime writes — a console loop
        stepping a stage, a workflow moving an actuator. Those used to take
        the same path, so every point of a scan rewrote the instrument-set
        JSON to disk and left the last scan position saved as that
        instrument's startup setting, replayed on the next connect.
        """
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        adapter = inst["adapter"]

        # Validate first, and validate even when the instrument is
        # disconnected: this endpoint saves settings for later application,
        # so without this an out-of-range value would be stored, reported
        # as saved, and then fail on the next connect — far from where the
        # user typed it. Needs no hardware, only the schema.
        checked = adapter.validate_write(values)

        if adapter.connected:
            await adapter.write(values)

        if persist:
            # The coerced values, not the raw ones, so what gets replayed
            # on the next connect is what the device actually accepted.
            inst.setdefault("custom_settings", {}).update(checked)
            self._save_active_config()
        return self.get_instrument_status(instrument_id)

    async def set_instrument_staged(self, instrument_id: str, staged: bool) -> InstrumentStatus:
        """Stage or unstage an instrument for acquisition.

        `stage()`/`unstage()` are part of every adapter's contract and are
        what a real acquisition loop brackets its reads with (arm the
        camera, allocate the counter's buffer), but they had no route, so
        the console and any other out-of-process client could only read and
        write. Without them a scan driven from a notebook silently ran
        every point unstaged.
        """
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        adapter = self.instruments[instrument_id]["adapter"]
        if not adapter.connected:
            raise NotConnectedError(
                f"{instrument_id} is not connected", device=instrument_id
            )
        await (adapter.stage() if staged else adapter.unstage())
        return self.get_instrument_status(instrument_id)

    async def call_instrument_action(self, instrument_id: str, action_name: str) -> InstrumentStatus:
        """Invoke one of an instrument's declared `DeviceSchema.actions` —
        a zero-argument adapter method that isn't a settable-parameter
        write (e.g. a microwave source's `cw_on`/`off`, a pulse
        sequencer's `start`/`stop`). Requires the instrument to be
        connected — unlike write_instrument_settings, an action can't be
        staged for later since it's a state transition, not a value."""
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        schema = inst["schema"]
        if action_name not in schema.actions:
            raise KeyError(f"Instrument {instrument_id} declares no action {action_name!r}")
        if not inst["adapter"].connected:
            raise ConnectionError("Instrument is not connected")

        method = getattr(inst["adapter"], action_name)
        await method()
        self._save_active_config()
        await self.broadcast_to_websockets({
            "type": "instrument_status",
            "instrument_id": instrument_id,
            "data": self.get_instrument_status(instrument_id).model_dump(),
        })
        return self.get_instrument_status(instrument_id)

    async def update_instrument_connection(
        self, instrument_id: str, connection_params: dict[str, Any]
    ) -> InstrumentStatus:
        """Replace an instrument's connection parameters (e.g. a new VISA
        address) by re-instantiating its adapter under the same id/name.

        Disconnects first if currently connected — repointing a live adapter
        at different hardware mid-connection isn't safe. If the new params
        are rejected, the previous entry is left in place (untouched, since
        `_instantiate` only replaces `self.instruments[instrument_id]` after
        the new adapter is constructed successfully) so the instrument isn't
        left in a half-broken state — just disconnected, as if you'd hit
        Disconnect.
        """
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        adapter_key = inst["adapter_type"]
        name = inst["name"]
        custom_settings = inst.get("custom_settings", {})

        if inst["adapter"].connected:
            try:
                await inst["adapter"].disconnect()
            except Exception:
                pass  # Best-effort — we're about to replace the adapter anyway

        self._instantiate(adapter_key, instrument_id, name, connection_params, custom_settings)
        self._save_active_config()
        await self.broadcast_to_websockets({
            "type": "instrument_status",
            "instrument_id": instrument_id,
            "data": self.get_instrument_status(instrument_id).model_dump(),
        })
        return self.get_instrument_status(instrument_id)

    async def remove_instrument(self, instrument_id: str) -> None:
        """Disconnect (if needed) and remove an instrument from the dashboard."""
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        adapter = self.instruments[instrument_id]["adapter"]
        if adapter.connected:
            try:
                await adapter.disconnect()
            except Exception:
                pass  # Remove regardless of disconnect failure
        del self.instruments[instrument_id]
        self._save_active_config()

    def create_instrument(
        self,
        adapter_key: str,
        instrument_id: str | None,
        name: str | None,
        connection_params: dict[str, Any],
    ) -> InstrumentStatus:
        """Instantiate (but don't connect) a new instrument from the catalog."""
        instrument_id = instrument_id or f"{adapter_key}_{len(self.instruments) + 1}"
        if instrument_id in self.instruments:
            raise ValueError(f"Instrument id {instrument_id!r} already exists")

        try:
            self._instantiate(adapter_key, instrument_id, name or adapter_key, connection_params)
        except UnknownAdapterError as e:
            raise ValueError(str(e)) from e

        self._save_active_config()
        return self.get_instrument_status(instrument_id)

    def get_dashboard_state(self) -> DashboardState:
        """Get complete dashboard state.

        Workflows are a separate, real system (core/workflow/ + the
        /api/workflows* routes in server.py) — not part of dashboard state.
        """
        instruments = [
            self.get_instrument_status(inst_id) for inst_id in self.instruments.keys()
        ]
        return DashboardState(instruments=instruments)

    async def stream_instrument_data(self, instrument_id: str, websocket: WebSocket):
        """Stream real-time data from an instrument to a WebSocket."""
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        adapter = inst["adapter"]

        try:
            while True:
                # Read from instrument
                data = await adapter.read()

                # Send to WebSocket
                message = {
                    "type": "instrument_data",
                    "instrument_id": instrument_id,
                    "data": _jsonable_read(data),
                    "timestamp": time.time(),
                }
                await websocket.send_json(message)

                # Update rate: 10 Hz
                await asyncio.sleep(0.1)

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"Error streaming {instrument_id}: {e}")

    async def broadcast_to_websockets(self, message: dict[str, Any]):
        """Broadcast message to all connected WebSockets."""
        disconnected = []
        for ws in self.websockets:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        # Remove disconnected WebSockets
        for ws in disconnected:
            self.websockets.remove(ws)


# Create router
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Global dashboard manager instance
_dashboard_manager: DashboardManager | None = None


def get_dashboard_manager() -> DashboardManager:
    """Get or create dashboard manager."""
    global _dashboard_manager
    if _dashboard_manager is None:
        _dashboard_manager = DashboardManager()
    return _dashboard_manager


@router.get("/state")
async def get_dashboard_state():
    """Get complete dashboard state."""
    manager = get_dashboard_manager()
    state = manager.get_dashboard_state()
    return {"success": True, "data": state.model_dump()}


@router.get("/instruments")
async def list_instruments():
    """List all connected instruments."""
    manager = get_dashboard_manager()
    instruments = [
        manager.get_instrument_status(inst_id).model_dump()
        for inst_id in manager.instruments.keys()
    ]
    return {"success": True, "data": instruments}


@router.get("/instruments/{instrument_id}/schema")
async def get_instrument_schema(instrument_id: str):
    """Get an instrument's real DeviceSchema (readable/settable/units/limits),
    for rendering an instrument-specific settings form."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    schema = manager.instruments[instrument_id]["schema"]
    # The whole schema, not a hand-picked subset: this listed eight keys by
    # name, so `parameters` — with the roles, tags and choices every client
    # needs to stop guessing from key names — would have been invisible on
    # the wire until someone remembered to add a ninth line. `mode="json"`
    # renders tuples as lists and enums as their values.
    return {"success": True, "data": schema.model_dump(mode="json")}


@router.get("/instruments/{instrument_id}/data")
async def read_instrument_data(instrument_id: str):
    """One-shot read of an instrument's current values (must be connected)."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    inst = manager.instruments[instrument_id]
    if not inst["adapter"].connected:
        raise HTTPException(status_code=409, detail="Instrument is not connected")
    try:
        data = await inst["adapter"].read()
        return {"success": True, "data": _jsonable_read(data)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Read failed: {e}")


@router.post("/instruments/{instrument_id}/settings")
async def write_instrument_settings(instrument_id: str, request: WriteSettingsRequest):
    """Set one or more of an instrument's settable parameters.

    Works whether or not the instrument is connected right now: values are
    always saved (as custom_settings) and automatically re-applied the next
    time it connects; if it happens to be connected already, they're also
    applied immediately.
    """
    manager = get_dashboard_manager()
    if instrument_id not in manager.instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    was_connected = manager.instruments[instrument_id]["adapter"].connected
    try:
        await manager.write_instrument_settings(
            instrument_id, request.values, persist=request.persist
        )
        message = "Settings applied" if was_connected else "Settings saved — will apply when connected"
        return {"success": True, "data": {"message": message}}
    except ParameterError as e:
        # An unknown name, a read-only parameter, an out-of-range or
        # non-numeric value — always the caller's fault, so it must not
        # come back as a 502 that reads like the instrument failed.
        raise HTTPException(status_code=422, detail=str(e)) from e
    except (UnsupportedOperationError, NotImplementedError) as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except NotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Write failed: {e}")


@router.post("/instruments/{instrument_id}/stage")
async def stage_instrument(instrument_id: str):
    """Prepare a connected instrument for acquisition (`adapter.stage()`)."""
    return await _set_staged(instrument_id, True)


@router.post("/instruments/{instrument_id}/unstage")
async def unstage_instrument(instrument_id: str):
    """Release a connected instrument after acquisition (`adapter.unstage()`)."""
    return await _set_staged(instrument_id, False)


async def _set_staged(instrument_id: str, staged: bool):
    manager = get_dashboard_manager()
    try:
        status = await manager.set_instrument_staged(instrument_id, staged)
        return {"success": True, "data": status.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        verb = "Stage" if staged else "Unstage"
        raise HTTPException(status_code=502, detail=f"{verb} failed: {e}") from e


@router.post("/instruments/{instrument_id}/actions/{action_name}")
async def call_instrument_action(instrument_id: str, action_name: str):
    """Invoke one of an instrument's declared non-settable actions (see
    DeviceSchema.actions) — e.g. a microwave source's `cw_on`, a pulse
    sequencer's `start`. Requires the instrument to be connected."""
    manager = get_dashboard_manager()
    try:
        status = await manager.call_instrument_action(instrument_id, action_name)
        return {"success": True, "data": status.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Action failed: {e}")


@router.get("/instruments/{instrument_id}/ui_prefs")
async def read_instrument_ui_prefs(instrument_id: str):
    """This instrument's native-UI display preferences (e.g. an
    actuator's "use a live slider" toggle) — set via this instrument's
    Settings modal, not a device parameter. See
    core/config/instrument_ui_prefs.py."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    return {"success": True, "data": get_instrument_ui_prefs(instrument_id)}


@router.get("/instruments/{instrument_id}/ui_prefs_schema")
async def read_instrument_ui_prefs_schema(instrument_id: str):
    """Which display preferences this instrument's native-UI kind
    declares (e.g. "use_slider" for a motor/source), so the Settings modal
    can render its "Native UI" section generically instead of one-off JSX
    per preference. See core/config/instrument_ui_prefs.py."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    schema = manager.instruments[instrument_id]["schema"]
    return {"success": True, "data": get_display_pref_schema(schema.kind)}


@router.put("/instruments/{instrument_id}/ui_prefs")
async def write_instrument_ui_prefs(instrument_id: str, request: UIPrefsRequest):
    """Save this instrument's native-UI display preferences."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.instruments:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    set_instrument_ui_prefs(instrument_id, request.prefs)
    return {"success": True, "data": {"message": "UI preferences saved"}}




@router.get("/catalog")
async def get_catalog():
    """List the instrument catalog (manufacturer/model/type), for the
    device-creation UI.

    Serves `available_catalog()` rather than the raw `INSTRUMENT_CATALOG`: the
    catalogue is a static table, but whether a driver imports depends on the
    vendor SDKs installed here. An entry whose adapter never registered — a
    broken vendor C extension, a missing runtime — would otherwise be offered
    in the Devices tab and then fail with `UnknownAdapterError` on create.
    """
    catalog = [
        {
            "adapter_key": m.adapter_key,
            "manufacturer": m.manufacturer,
            "model": m.model,
            "display_name": m.display_name,
            "instrument_type": m.instrument_type.value,
            "backend": m.backend.value,
            "connection_types": m.connection_types,
            "tags": m.tags,
        }
        for m in available_catalog()
    ]
    return {"success": True, "data": catalog}


@router.post("/instruments", status_code=201)
async def create_instrument(request: CreateInstrumentRequest):
    """Instantiate a new instrument from the catalog (not connected yet)."""
    manager = get_dashboard_manager()
    try:
        status = manager.create_instrument(
            request.adapter_key, request.id, request.name, request.connection_params
        )
        return {"success": True, "data": status.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TypeError as e:
        # Adapter's __init__ rejected the connection_params we gave it
        raise HTTPException(status_code=422, detail=f"Invalid connection parameters: {e}")


@router.post("/instruments/{instrument_id}/connect")
async def connect_instrument(instrument_id: str):
    """Connect an instrument to real hardware."""
    manager = get_dashboard_manager()
    try:
        status = await manager.connect_instrument(instrument_id)
        return {"success": True, "data": status.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection failed: {e}")


@router.post("/instruments/{instrument_id}/disconnect")
async def disconnect_instrument(instrument_id: str):
    """Disconnect an instrument from hardware."""
    manager = get_dashboard_manager()
    try:
        status = await manager.disconnect_instrument(instrument_id)
        return {"success": True, "data": status.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Disconnect failed: {e}")


@router.patch("/instruments/{instrument_id}/connection")
async def update_instrument_connection(instrument_id: str, request: UpdateConnectionRequest):
    """Replace an instrument's connection parameters (e.g. a new VISA
    address or IP), re-instantiating its adapter under the same id. Safe to
    call while connected — it disconnects first."""
    manager = get_dashboard_manager()
    try:
        status = await manager.update_instrument_connection(instrument_id, request.connection_params)
        return {"success": True, "data": status.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid connection parameters: {e}")


@router.delete("/instruments/{instrument_id}")
async def remove_instrument(instrument_id: str):
    """Remove an instrument from the dashboard (disconnecting it first if needed)."""
    manager = get_dashboard_manager()
    try:
        await manager.remove_instrument(instrument_id)
        return {"success": True, "data": {"message": f"Removed {instrument_id}"}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/configs")
async def list_instrument_configs():
    """List saved instrument-set configs and which one is active."""
    manager = get_dashboard_manager()
    return {
        "success": True,
        "data": {
            "configs": manager.config_store.list_configs(),
            "active": manager.active_config_name,
        },
    }


@router.post("/configs/new")
async def new_instrument_config(request: NewInstrumentConfigRequest):
    """Create a new, blank instrument-set config and make it active."""
    manager = get_dashboard_manager()
    if manager.config_store.exists(request.name):
        raise HTTPException(status_code=400, detail=f"A config named {request.name!r} already exists")
    try:
        await manager.create_blank_instrument_set(request.name)
        return {"success": True, "data": {"active": request.name, "instruments": []}}
    except InstrumentSetError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/configs/upload")
async def upload_instrument_config(request: UploadInstrumentConfigRequest):
    """Load a config from an uploaded file's contents (parsed client-side)
    and make it active."""
    manager = get_dashboard_manager()
    name = request.name
    if not name:
        raise HTTPException(status_code=400, detail="Missing config name")
    try:
        await manager.import_instrument_set(name, request.devices)
        instruments = [
            manager.get_instrument_status(i).model_dump() for i in manager.instruments
        ]
        return {"success": True, "data": {"active": name, "instruments": instruments}}
    except (InstrumentSetError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid config file: {e}")


@router.post("/configs/{name}/activate")
async def activate_instrument_config(name: str):
    """Tear down the current instrument set and load a different named config."""
    manager = get_dashboard_manager()
    try:
        await manager.load_instrument_set(name)
        instruments = [
            manager.get_instrument_status(i).model_dump() for i in manager.instruments
        ]
        return {"success": True, "data": {"active": name, "instruments": instruments}}
    except InstrumentSetError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/configs/{name}")
async def delete_instrument_config(name: str):
    """Delete a saved instrument-set config (not the currently active one)."""
    manager = get_dashboard_manager()
    if name == manager.active_config_name:
        raise HTTPException(status_code=400, detail="Cannot delete the active config — activate a different one first")
    try:
        manager.config_store.delete(name)
        return {"success": True, "data": {"message": f"Deleted {name!r}"}}
    except InstrumentSetError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.websocket("/ws/instruments/{instrument_id}")
async def instrument_data_stream(websocket: WebSocket, instrument_id: str):
    """WebSocket endpoint for real-time instrument data."""
    manager = get_dashboard_manager()
    await websocket.accept()
    manager.websockets.append(websocket)

    try:
        await manager.stream_instrument_data(instrument_id, websocket)
    finally:
        manager.websockets.remove(websocket)


@router.websocket("/ws/workflows")
async def workflow_updates_stream(websocket: WebSocket):
    """WebSocket endpoint for workflow progress updates."""
    manager = get_dashboard_manager()
    await websocket.accept()
    manager.websockets.append(websocket)

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.websockets.remove(websocket)


async def initialize_dashboard():
    """Initialize dashboard: load the active instrument-set config (or seed
    one)."""
    manager = get_dashboard_manager()
    await manager.initialize_instruments()


__all__ = ["get_dashboard_manager", "initialize_dashboard", "router"]
