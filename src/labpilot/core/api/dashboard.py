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
from labpilot.core.lab import (
    InstrumentHandle,
    InstrumentSpec,
    Lab,
    UnknownInstrumentError,
)
from labpilot.core.session import Session
from labpilot.instruments import available_catalog
from labpilot.instruments.factory import UnknownAdapterError


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
    """The HTTP/WebSocket face of the `Lab`.

    Everything about *which instruments exist and what they are doing* now
    lives in `core/lab/` — this class turns that model into the wire format
    the Devices UI and the console client already speak, and owns the
    WebSocket fan-out, which is genuinely presentation.

    It used to be the model as well: `self.instruments` was a dict of
    untyped dicts holding the adapter, its address, its saved settings, its
    status and its last error together, and `_save_active_config()` wrote
    the whole thing to disk from the `finally` of nearly every operation.
    That is what let a runtime write land in the saved configuration. With
    the spec/handle split the save calls that remain are the ones that
    follow a change to the configuration itself.
    """

    def __init__(self):
        self.lab = Lab()
        self.websockets: list[WebSocket] = []
        self.instrument_data_streams: dict[str, asyncio.Task] = {}

    # --- The lab, as the routes and the rest of the server see it ---------

    @property
    def instruments(self) -> dict[str, InstrumentHandle]:
        """Every configured instrument, by id."""
        return {handle.id: handle for handle in self.lab}

    @property
    def config_store(self) -> InstrumentSetPersistence:
        return self.lab.store

    @property
    def active_config_name(self) -> str | None:
        return self.lab.active_config

    @property
    def session(self) -> Session | None:
        return self.lab.session

    def set_session(self, session: Session) -> None:
        """Attach the shared Session, so a connected instrument is also
        resolvable by name from a workflow script."""
        self.lab.set_session(session)

    # --- Instrument sets --------------------------------------------------

    async def initialize_instruments(self):
        """Load the active instrument-set config, or seed a fresh one."""
        await self.lab.initialize()

    async def load_instrument_set(self, name: str) -> None:
        """Tear down the current instrument set and load a named config."""
        await self.lab.load(name)

    def save_instrument_set_as(self, name: str) -> None:
        """Snapshot the current instrument set under a name and activate it."""
        self.lab.save_as(name)

    async def create_blank_instrument_set(self, name: str) -> None:
        """Start a new, empty named config; instruments added later save into it."""
        await self.lab.new(name)

    async def import_instrument_set(self, name: str, device_dicts: list[dict[str, Any]]) -> None:
        """Load an uploaded config's device list, save it, and make it active."""
        await self.lab.import_specs(name, device_dicts)

    # --- One instrument ---------------------------------------------------

    def get_instrument_status(self, instrument_id: str) -> InstrumentStatus:
        """One instrument's spec and runtime state, in the wire format."""
        handle = self.lab.get(instrument_id)
        return InstrumentStatus(
            id=handle.id,
            name=handle.name,
            adapter_type=handle.adapter_key,
            kind=handle.schema.kind,
            dimensionality=handle.dimensionality,
            tags=handle.schema.tags,
            connected=handle.connected,
            status=handle.status,
            error=handle.error,
            data=None,  # populated by the real-time stream
            connection_params=dict(handle.spec.connection),
            custom_settings=dict(handle.spec.defaults),
        )

    def create_instrument(
        self,
        adapter_key: str,
        instrument_id: str | None,
        name: str | None,
        connection_params: dict[str, Any],
    ) -> InstrumentStatus:
        """Instantiate (but don't connect) a new instrument from the catalog."""
        instrument_id = instrument_id or f"{adapter_key}_{len(self.lab) + 1}"
        if instrument_id in self.lab:
            raise ValueError(f"Instrument id {instrument_id!r} already exists")

        spec = InstrumentSpec(
            id=instrument_id,
            adapter_key=adapter_key,
            name=name or adapter_key,
            connection=connection_params,
        )
        try:
            self.lab.add(spec)
        except UnknownAdapterError as e:
            raise ValueError(str(e)) from e

        self.lab.save()
        return self.get_instrument_status(instrument_id)

    async def connect_instrument(self, instrument_id: str) -> InstrumentStatus:
        """Connect an instrument's adapter to real hardware.

        The spec's startup settings are applied right after — the earliest
        point a real adapter can accept a write, since most only build
        their underlying handle in `connect()`. Nothing is saved: connecting
        does not change the configuration.
        """
        try:
            await self.lab.connect(instrument_id)
        finally:
            await self._broadcast_status(instrument_id)
        return self.get_instrument_status(instrument_id)

    async def disconnect_instrument(self, instrument_id: str) -> InstrumentStatus:
        """Disconnect an instrument's adapter from hardware."""
        try:
            await self.lab.disconnect(instrument_id)
        finally:
            await self._broadcast_status(instrument_id)
        return self.get_instrument_status(instrument_id)

    async def write_instrument_settings(
        self, instrument_id: str, values: dict[str, Any], *, persist: bool = True
    ) -> InstrumentStatus:
        """Set one or more of an instrument's settable parameters.

        With `persist` (the Settings UI) the values also become part of the
        instrument's spec, so they are re-applied the next time it
        connects. `persist=False` is an ordinary runtime write — a console
        loop stepping a stage, a jog control. Those used to take the same
        path, so every point of a scan rewrote the config file and the
        position the scan stopped at became the stage's startup setting.
        """
        handle = self.lab.get(instrument_id)

        # Validate first, and validate even while disconnected: this
        # endpoint saves settings for later application, so otherwise an
        # out-of-range value would be stored, reported as saved, and then
        # fail on the next connect — far from where it was typed. Needs no
        # hardware, only the schema.
        checked = handle.validate_write(values)

        if handle.connected:
            await handle.write(values)

        if persist:
            # The coerced values, not the raw ones, so what is replayed on
            # the next connect is what the device actually accepted.
            self.lab.update_spec(instrument_id, handle.spec.with_defaults(checked))
            self.lab.save()
        return self.get_instrument_status(instrument_id)

    async def set_instrument_staged(self, instrument_id: str, staged: bool) -> InstrumentStatus:
        """Stage or unstage an instrument for acquisition.

        `stage()`/`unstage()` are part of every adapter's contract and are
        what a real acquisition loop brackets its reads with (arm the
        camera, allocate the counter's buffer), but they had no route, so
        a scan driven from a notebook silently ran every point unstaged.
        """
        await self.lab.get(instrument_id).set_staged(staged)
        return self.get_instrument_status(instrument_id)

    async def stop_instrument(self, instrument_id: str) -> InstrumentStatus:
        """Stop a moving instrument where it is (`Motor.stop()`).

        The half of "abort" that reaches hardware: ending the loop that
        commands a stage does not stop the stage, which keeps travelling to
        the position last commanded. Routed rather than reimplemented for
        the console, so a remote handle and an in-process wrapper stop a
        device the same way.
        """
        await self.lab.get(instrument_id).stop()
        return self.get_instrument_status(instrument_id)

    async def call_instrument_action(self, instrument_id: str, action_name: str) -> InstrumentStatus:
        """Invoke one of an instrument's declared `DeviceSchema.actions` —
        a zero-argument adapter method that isn't a settable-parameter
        write (a microwave source's `cw_on`, a pulse sequencer's `start`).
        Requires the instrument to be connected: unlike a setting, an
        action is a state transition, so it cannot be staged for later."""
        await self.lab.get(instrument_id).call(action_name)
        await self._broadcast_status(instrument_id)
        return self.get_instrument_status(instrument_id)

    async def update_instrument_connection(
        self, instrument_id: str, connection_params: dict[str, Any]
    ) -> InstrumentStatus:
        """Point an instrument at different hardware (a new VISA address),
        rebuilding its adapter under the same id.

        Disconnects first — repointing a live adapter mid-connection isn't
        safe. If the new parameters are rejected the previous instrument is
        left in place, disconnected, because `Lab.add` only stores the
        handle once the adapter has been constructed successfully.
        """
        handle = self.lab.get(instrument_id)
        if handle.connected:
            try:
                await self.lab.disconnect(instrument_id)
            except Exception:
                pass  # Best-effort — the adapter is about to be replaced.

        self.lab.add(handle.spec.with_connection(connection_params))
        self.lab.save()
        await self._broadcast_status(instrument_id)
        return self.get_instrument_status(instrument_id)

    async def remove_instrument(self, instrument_id: str) -> None:
        """Disconnect (if needed) and remove an instrument from the lab."""
        await self.lab.remove(instrument_id)
        self.lab.save()

    def get_dashboard_state(self) -> DashboardState:
        """Get complete dashboard state.

        Workflows are a separate, real system (core/workflow/ + the
        /api/workflows* routes in server.py) — not part of dashboard state.
        """
        return DashboardState(
            instruments=[self.get_instrument_status(i) for i in self.lab.ids]
        )

    # --- WebSockets -------------------------------------------------------

    async def stream_instrument_data(self, instrument_id: str, websocket: WebSocket):
        """Stream real-time data from an instrument to a WebSocket."""
        handle = self.lab.get(instrument_id)
        try:
            while True:
                data = await handle.adapter.read()
                await websocket.send_json({
                    "type": "instrument_data",
                    "instrument_id": instrument_id,
                    "data": _jsonable_read(data),
                    "timestamp": time.time(),
                })
                await asyncio.sleep(0.1)  # 10 Hz
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"Error streaming {instrument_id}: {e}")

    async def _broadcast_status(self, instrument_id: str) -> None:
        """Push one instrument's current status to every listening client."""
        if instrument_id not in self.lab:
            return
        await self.broadcast_to_websockets({
            "type": "instrument_status",
            "instrument_id": instrument_id,
            "data": self.get_instrument_status(instrument_id).model_dump(),
        })

    async def broadcast_to_websockets(self, message: dict[str, Any]):
        """Broadcast message to all connected WebSockets."""
        disconnected = []
        for ws in self.websockets:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

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
        for inst_id in manager.lab.ids
    ]
    return {"success": True, "data": instruments}


@router.get("/instruments/{instrument_id}/schema")
async def get_instrument_schema(instrument_id: str):
    """Get an instrument's real DeviceSchema (readable/settable/units/limits),
    for rendering an instrument-specific settings form."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.lab:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    schema = manager.lab[instrument_id].schema
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
    if instrument_id not in manager.lab:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    handle = manager.lab[instrument_id]
    if not handle.connected:
        raise HTTPException(status_code=409, detail="Instrument is not connected")
    try:
        data = await handle.read()
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
    if instrument_id not in manager.lab:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    was_connected = manager.lab[instrument_id].connected
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
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        verb = "Stage" if staged else "Unstage"
        raise HTTPException(status_code=502, detail=f"{verb} failed: {e}") from e


@router.post("/instruments/{instrument_id}/stop")
async def stop_instrument(instrument_id: str):
    """Stop a moving instrument where it is (see `Motor.stop()`)."""
    manager = get_dashboard_manager()
    try:
        status = await manager.stop_instrument(instrument_id)
        return {"success": True, "data": status.model_dump()}
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except UnsupportedOperationError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stop failed: {e}") from e


@router.post("/instruments/{instrument_id}/actions/{action_name}")
async def call_instrument_action(instrument_id: str, action_name: str):
    """Invoke one of an instrument's declared non-settable actions (see
    DeviceSchema.actions) — e.g. a microwave source's `cw_on`, a pulse
    sequencer's `start`. Requires the instrument to be connected."""
    manager = get_dashboard_manager()
    try:
        status = await manager.call_instrument_action(instrument_id, action_name)
        return {"success": True, "data": status.model_dump()}
    except (UnknownInstrumentError, KeyError) as e:
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
    if instrument_id not in manager.lab:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    return {"success": True, "data": get_instrument_ui_prefs(instrument_id)}


@router.get("/instruments/{instrument_id}/ui_prefs_schema")
async def read_instrument_ui_prefs_schema(instrument_id: str):
    """Which display preferences this instrument's native-UI kind
    declares (e.g. "use_slider" for a motor/source), so the Settings modal
    can render its "Native UI" section generically instead of one-off JSX
    per preference. See core/config/instrument_ui_prefs.py."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.lab:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id} not found")
    schema = manager.lab[instrument_id].schema
    return {"success": True, "data": get_display_pref_schema(schema.kind)}


@router.put("/instruments/{instrument_id}/ui_prefs")
async def write_instrument_ui_prefs(instrument_id: str, request: UIPrefsRequest):
    """Save this instrument's native-UI display preferences."""
    manager = get_dashboard_manager()
    if instrument_id not in manager.lab:
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
    except UnknownInstrumentError as e:
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
    except UnknownInstrumentError as e:
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
    except UnknownInstrumentError as e:
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
    except UnknownInstrumentError as e:
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
            manager.get_instrument_status(i).model_dump() for i in manager.lab.ids
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
            manager.get_instrument_status(i).model_dump() for i in manager.lab.ids
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
