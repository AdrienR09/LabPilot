"""FastAPI server for LabPilot browser interface.

Provides RESTful API endpoints for:
- Session management and device control
- Workflow creation and execution
- AI chat and streaming responses
- Real-time data streaming via WebSockets
- Configuration management

The server runs alongside the core LabPilot session and provides
web access to all laboratory automation capabilities.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from labpilot.core.api.dashboard import get_dashboard_manager, initialize_dashboard
from labpilot.core.api.dashboard import router as dashboard_router
from labpilot.core.config import (
    ConfigPersistence,
)
from labpilot.core.config.paths import user_workflow_dir
from labpilot.core.config.template_params import TemplateParamPersistence
from labpilot.core.config.workflow_sets import WorkflowSetPersistence
from labpilot.core.lab import UnknownInstrumentError
from labpilot.core.run import OptimizePlan, RunAbortedError, prepare
from labpilot.core.run.manager import RunManager, WorkflowExecutionError
from labpilot.core.session import Session
from labpilot.core.workflow import WorkflowGraph, WorkflowStore
from labpilot.core.workflow.instrument_roles import (
    read_capabilities,
    read_required_instruments,
    read_required_instruments_from_file,
    read_result_ui,
    read_template_description,
    read_workflow_params,
)
from labpilot.core.workflow.migrate import migrate_library_workflows
from labpilot.core.workflow.presets import load_presets
from labpilot.core.workflow.scan_params import resolve_scan_axes

__all__ = ["LabPilotServer", "create_app"]


def _workflow_templates_dir() -> Path:
    """Where the shipped templates live, inside the installed package."""
    import labpilot.core.workflow_templates as templates

    return Path(templates.__path__[0])

# API Models
class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    data: Any = None
    error: str | None = None
    timestamp: float = Field(default_factory=time.time)


class DeviceStatus(BaseModel):
    """Device status information."""
    name: str
    adapter_type: str
    connected: bool
    last_reading: dict[str, Any] | None = None
    error: str | None = None


class DeviceConnectionRequest(BaseModel):
    """Request to connect a device."""
    name: str
    adapter_type: str
    connection_params: dict[str, Any]


class WorkflowCreateRequest(BaseModel):
    """Request to create a new workflow."""
    name: str
    description: str = ""


class WorkflowScriptUpdateRequest(BaseModel):
    """Request to save edited script text (file-only, not re-parsed)."""
    content: str


class WorkflowParamUpdateRequest(BaseModel):
    """Request to change one of a workflow's own tunable parameters (see
    core/workflow/instrument_roles.py's read_workflow_params) — distinct
    from an instrument's settings."""
    value: Any


class WorkflowOptimizeRequest(BaseModel):
    """Request to re-center a workflow's optimizer-capability-bound
    actuator on the detector's local maximum — a small ad-hoc sequence of
    sub-scans around its current position (`core/run/plans.py`'s
    `OptimizePlan`), not a full run of the workflow's own script.

    `axes`, if given, is the EXACT set of actuator axes to optimize over
    (validated against what's actually available — see
    `core/workflow/scan_params.py`) — "select if you want to optimize along one
    dimension or multiple dimensions"; omit to use every available axis
    (today's default behavior, unchanged). `ranges`/`points_per_axis`, if
    given, override the per-axis search span/resolution (an axis not
    present in either falls back to a fraction of its own declared
    AXIS_RANGES span, and to `points`, respectively). See
    POST /api/workflows/{id}/optimize/start."""
    axes: list[str] | None = None
    ranges: dict[str, float] | None = None
    points: int = 5
    points_per_axis: dict[str, int] | None = None


class WorkflowLoadRequest(BaseModel):
    """Request to load a workflow script from a path into the active
    workflow-set."""
    path: str


class WorkflowBindingRequest(BaseModel):
    """Request to bind (or, with instrument_id=None, unbind) one
    instrument role to a real connected instrument."""
    instrument_id: str | None


class ScanAxisRequest(BaseModel):
    """One swept dimension of an ad-hoc scan — see `run.plans.ScanAxis`."""
    name: str
    device: str
    start: float
    stop: float
    points: int
    unit: str = ""


class ScanRequest(BaseModel):
    """Start a scan that belongs to no workflow.

    What `lp.scan(...)` posts. The console cannot reach the in-process
    `ScanPlan` — instruments live in the server — so it describes the plan
    it wants and the server builds it. Everything past that point is the
    ordinary run machinery: the worker loop, live patches, pause, abort and
    the automatic HDF5 save.
    """
    axes: list[ScanAxisRequest]
    detector: str
    name: str = "scan"
    hold: dict[str, float] = {}
    hold_device: str | None = None


class RunRequest(BaseModel):
    """Start any plan that declares how it crosses the process boundary.

    `POST /api/runs/scan` could rebuild a `ScanPlan` and nothing else,
    so a console could start a scan and no other kind of run. Rather than
    a third bespoke route for pulsed measurements, a plan type declares
    its own transport (`core/run/requests.py`) and this route reads that
    declaration. `/api/runs/scan` stays, as the same thing under its
    original name.
    """
    plan: str
    params: dict[str, Any] = {}
    name: str = ""


class QtLaunchRequest(BaseModel):
    """Request to launch Qt instrument window."""
    instrument_id: str
    instrument_type: str
    dimensionality: str

# WebSocket Manager
class WebSocketManager:
    """Manages WebSocket connections for real-time communication."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except:
                # Connection is dead, remove it
                self.disconnect(connection)


class LabPilotServer:
    """Main LabPilot FastAPI server."""

    def __init__(self, config_dir: Path | None = None):
        """Initialize LabPilot server.

        Args:
            config_dir: Configuration directory path.
        """
        self.session = Session()
        self.config_persistence = ConfigPersistence(config_dir)
        self.workflow_store: WorkflowStore | None = None
        self.workflow_engine: RunManager | None = None
        self.workflow_set_store = WorkflowSetPersistence(self.config_persistence.config_dir)
        self.template_param_store = TemplateParamPersistence(self.config_persistence.config_dir)
        self.websocket_manager = WebSocketManager()
        self._event_task: asyncio.Task | None = None
        # One in-flight optimize run per workflow — a small ad-hoc grid
        # scan around the crosshair-bound actuator's current position,
        # separate from a full run of the workflow's own script (see
        # /api/workflows/{id}/optimize/start below). Tracked here rather
        # than through RunManager's own execution-state machinery
        # since it isn't a run of the workflow's script at all.
        self.optimize_states: dict[str, dict] = {}
        self._optimize_tasks: dict[str, asyncio.Task] = {}
        # The Run each in-flight optimize is executing, so stopping one
        # stops the hardware and keeps its points, not just the task.
        self._optimize_runs: dict[str, Any] = {}

    async def initialize(self):
        """Initialize server components."""
        # Load session configuration
        config = self.config_persistence.load_session_config()
        if config:
            self.config_persistence.to_session(config, self.session)

        # Initialize workflow components
        db_path = self.config_persistence.config_dir / "workflows" / "workflows.db"
        self.workflow_store = WorkflowStore(db_path)
        self.workflow_engine = RunManager(self.session, self.workflow_store)

        # Workflows saved before an instance became a row still point at a
        # timestamped copy of a template's source inside the installed
        # package. Repoint them at the template itself — see
        # core/workflow/migrate.py. Idempotent: a row already pointing at a
        # template is not a copy and is skipped.
        migrate_library_workflows(self.workflow_store, _workflow_templates_dir())

        # First run: nothing loaded yet — seed the active workflow-set from
        # whatever's already in the store with a real script_path, so
        # existing genuine workflows keep showing up. Anything without one
        # (e.g. leftover empty test graphs) is naturally excluded rather
        # than needing explicit cleanup.
        if self.workflow_set_store.get_active_name() is None:
            seeded = []
            for summary in self.workflow_store.list_all():
                try:
                    graph = self.workflow_store.load(summary.id)
                except Exception:
                    continue
                if graph.metadata.get("script_path"):
                    seeded.append(summary.id)
            self.workflow_set_store.save(WorkflowSetPersistence.DEFAULT_NAME, seeded)
            self.workflow_set_store.set_active_name(WorkflowSetPersistence.DEFAULT_NAME)

        # Start event broadcasting
        self._event_task = asyncio.create_task(self._event_broadcaster())

        # A dashboard-connected instrument must also be resolvable by name
        # from a workflow node (RunManager reads through self.session,
        # the dashboard's own instrument registry is separate) — attach the
        # session before any instrument can connect.
        get_dashboard_manager().set_session(self.session)

        # Initialize dashboard: load/seed the active instrument-set config.
        await initialize_dashboard()

    async def shutdown(self):
        """Shutdown server components."""
        if self._event_task:
            self._event_task.cancel()

    async def _event_broadcaster(self):
        """Broadcast LabPilot events to WebSocket clients."""
        try:
            async for event in self.session.bus.subscribe():
                # Skip the serialize+broadcast entirely when nobody is
                # listening: json.dumps on every reported point competes
                # for the same event loop the workflow runs on, and with
                # zero WebSocket clients connected (the common case) it is
                # pure waste.
                if not self.websocket_manager.active_connections:
                    continue
                event_dict = event.to_dict()
                # No thinning here any more. Producers publish a summary
                # plus per-point `DatasetPatch`es (see
                # Session.report_progress/report_reading and
                # core/data/dataset.py::summarise_arrays), so the bus
                # carries no bulk arrays to strip. This used to be
                # `_strip_oversized_fields`, which walked every outgoing
                # event and dropped any list past 4096 flattened
                # elements — necessary at the time, because one un-thinned
                # completion frame for a 30x30 scan produced a ~70 MB
                # frame and killed the connection outright, but it was
                # guessing at the socket, by size, about payloads whose
                # meaning it did not know. Its own history records the
                # cost: a first version that looked only at top-level
                # fields missed WORKFLOW_COMPLETED entirely, and a `<=`
                # where a `<` belonged let every 64x64 camera frame —
                # exactly 4096 elements — through un-thinned.
                event_data = {
                    "type": "event",
                    "event": event_dict,
                }
                await self.websocket_manager.broadcast(json.dumps(event_data))
        except asyncio.CancelledError:
            pass


# Create FastAPI app with lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server startup and shutdown."""
    server: LabPilotServer = app.state.server
    await server.initialize()
    print("🚀 LabPilot server initialized")
    yield
    await server.shutdown()
    print("🔌 LabPilot server shutdown")


def create_app(config_dir: Path | None = None) -> FastAPI:
    """Create FastAPI application.

    Args:
        config_dir: Configuration directory path.

    Returns:
        Configured FastAPI app.
    """
    app = FastAPI(
        title="LabPilot API",
        description="AI-native laboratory experiment operating system",
        version="1.0.0",
        lifespan=lifespan
    )

    # Store server instance in app state
    app.state.server = LabPilotServer(config_dir)

    # CORS middleware for browser access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # React dev server
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Dependency to get server instance
    def get_server() -> LabPilotServer:
        return app.state.server

    # Include dashboard router
    app.include_router(dashboard_router)

    # API Routes
    @app.get("/api/health", response_model=ApiResponse)
    async def health_check():
        """Health check endpoint."""
        return ApiResponse(success=True, data={"status": "healthy"})

    @app.get("/api/runs", response_model=ApiResponse)
    async def list_runs(limit: int = 50, server: LabPilotServer = Depends(get_server)):
        """Every saved run, newest first.

        Runs are now written to HDF5 and indexed automatically as they
        finish (see core/storage/runs.py). Without a route to read the
        index back, the provenance catalogue would be as unreachable as it
        was when nothing constructed it at all.
        """
        try:
            runs = await server.workflow_engine.runs.list_runs(limit=limit)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Run catalogue unavailable: {e}") from e
        return ApiResponse(success=True, data=runs)

    # --- Ad-hoc runs ------------------------------------------------------
    #
    # A scan that belongs to no workflow. These share `RunManager`'s run
    # table with workflow runs, so the id one returns is accepted by
    # /stop, /pause and /resume below rather than needing its own set.

    @app.post("/api/runs/scan", response_model=ApiResponse)
    async def start_scan(request: ScanRequest, server: LabPilotServer = Depends(get_server)):
        """Start a scan described in the request, and return its run id.

        The console's `lp.scan(...)`. Instruments are named by their
        registered ids, which is what the console already has; the
        instruments must be connected, and saying so here is better than
        accepting the run and failing on the worker loop after the caller
        has been told it started.
        """
        if not request.axes:
            raise HTTPException(status_code=422, detail="A scan needs at least one axis")
        return await _start(
            server, "scan",
            {
                "axes": [axis.model_dump() for axis in request.axes],
                "detector": request.detector,
                "name": request.name,
                "hold": request.hold,
                "hold_device": request.hold_device,
            },
            request.name,
        )

    @app.post("/api/runs", response_model=ApiResponse)
    async def start_run(request: RunRequest, server: LabPilotServer = Depends(get_server)):
        """Start any plan a console can describe — see `RunRequest`."""
        return await _start(server, request.plan, request.params, request.name)

    async def _start(
        server: LabPilotServer, plan_name: str, params: dict, name: str
    ) -> ApiResponse:
        """Build a plan from a request and hand it to the run manager.

        The connection check happens here, before the run is accepted:
        discovering a disconnected counter on the worker loop means the
        caller was already told the run started.
        """
        from labpilot.core.run import build_plan, plan_devices

        try:
            missing = sorted(
                role for role in plan_devices(plan_name, params)
                if not server.session.has(role)
            )
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        if missing:
            raise HTTPException(
                status_code=409,
                detail=f"Not connected: {', '.join(missing)}. "
                       f"Connect them before starting the run.",
            )

        try:
            plan = build_plan(plan_name, params)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        try:
            run_id = await server.workflow_engine.start_plan(plan)
        except WorkflowExecutionError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return ApiResponse(
            success=True,
            data={"run_id": run_id, "name": name or getattr(plan, "name", plan_name)},
        )

    @app.get("/api/runs/{run_id}/state", response_model=ApiResponse)
    async def get_run_state(run_id: str, server: LabPilotServer = Depends(get_server)):
        """How far through a run is, and whether it is still going."""
        engine = server.workflow_engine
        state = engine.run_state(run_id)
        running = engine.is_running(run_id)
        if state is None and not running and engine.result(run_id) is None:
            raise HTTPException(status_code=404, detail=f"No run {run_id!r}")
        return ApiResponse(
            success=True,
            data={"run_id": run_id, "running": running, **(state or {})},
        )

    @app.get("/api/runs/{run_id}/result", response_model=ApiResponse)
    async def get_run_result(run_id: str, server: LabPilotServer = Depends(get_server)):
        """What the run measured — the last live frame while it is going,
        its full result once it has finished."""
        result = server.workflow_engine.result(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No run {run_id!r}")
        return ApiResponse(success=True, data=result)

    @app.post("/api/runs/{run_id}/stop", response_model=ApiResponse)
    async def stop_run(run_id: str, server: LabPilotServer = Depends(get_server)):
        """Stop at the next point boundary, keeping what was measured."""
        if not server.workflow_engine.is_running(run_id):
            raise HTTPException(status_code=409, detail=f"Run {run_id!r} is not running")
        await server.workflow_engine.stop_workflow(run_id)
        return ApiResponse(success=True, data={"run_id": run_id, "stopped": True})

    @app.post("/api/runs/{run_id}/pause", response_model=ApiResponse)
    async def pause_run(run_id: str, server: LabPilotServer = Depends(get_server)):
        if not await server.workflow_engine.pause_workflow(run_id):
            raise HTTPException(status_code=409, detail=f"Run {run_id!r} is not running a plan")
        return ApiResponse(success=True, data={"run_id": run_id, "paused": True})

    @app.post("/api/runs/{run_id}/resume", response_model=ApiResponse)
    async def resume_run(run_id: str, server: LabPilotServer = Depends(get_server)):
        if not await server.workflow_engine.resume_workflow(run_id):
            raise HTTPException(status_code=409, detail=f"Run {run_id!r} is not running a plan")
        return ApiResponse(success=True, data={"run_id": run_id, "paused": False})

    @app.get("/api/session/status", response_model=ApiResponse)
    async def get_session_status(server: LabPilotServer = Depends(get_server)):
        """Get current session status."""
        return ApiResponse(
            success=True,
            data={
                "session_id": getattr(server.session, "_config", {}).get("session_id", "default"),
                "devices_connected": len(server.session.devices),
                "workflow_engine_running": len(server.workflow_engine.get_running_workflows()) if server.workflow_engine else 0
            }
        )

    @app.get("/api/devices", response_model=ApiResponse)
    async def list_devices(server: LabPilotServer = Depends(get_server)):
        """List all connected devices."""
        devices = []
        for name, device in server.session.devices.items():
            # Get device status
            try:
                last_reading = await device.read() if hasattr(device, 'read') else None
                connected = True
                error = None
            except Exception as e:
                last_reading = None
                connected = False
                error = str(e)

            device_status = DeviceStatus(
                name=name,
                adapter_type=getattr(device, '_adapter_type', 'unknown'),
                connected=connected,
                last_reading=last_reading,
                error=error
            )
            devices.append(device_status.model_dump())

        return ApiResponse(success=True, data=devices)

    @app.post("/api/devices/connect", response_model=ApiResponse)
    async def connect_device(
        request: DeviceConnectionRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Create and connect a device by adapter key.

        Delegates to the DashboardManager rather than touching
        `session.devices` directly: the manager owns instrument instances and
        their connection parameters, and mirrors connected ones into the
        Session. Writing to the mirror here instead would leave the two
        registries disagreeing.

        (This previously returned success unconditionally without creating or
        connecting anything.)
        """
        manager = get_dashboard_manager()
        try:
            manager.create_instrument(
                request.adapter_type, request.name, request.name, request.connection_params
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except TypeError as e:
            raise HTTPException(
                status_code=422, detail=f"Invalid connection parameters: {e}"
            ) from e

        try:
            status = await manager.connect_instrument(request.name)
        except UnknownInstrumentError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Connection failed: {e}") from e

        return ApiResponse(success=True, data=status.model_dump())

    @app.delete("/api/devices/{device_name}", response_model=ApiResponse)
    async def disconnect_device(
        device_name: str,
        server: LabPilotServer = Depends(get_server)
    ):
        """Disconnect a device.

        Goes through the DashboardManager for the same reason as connect
        above — deleting straight out of `session.devices` disconnected the
        instrument as far as workflows were concerned while leaving the
        manager (and so the Devices tab) still showing it connected.
        """
        manager = get_dashboard_manager()
        try:
            status = await manager.disconnect_instrument(device_name)
        except UnknownInstrumentError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Disconnect failed: {e}") from e

        return ApiResponse(success=True, data=status.model_dump())

    def _loaded_workflow_ids(server: LabPilotServer) -> set[str]:
        """Which workflows the Workflows tab shows (see
        WorkflowSetPersistence).

        Entries are workflow ids. A config written before that was true
        lists script paths instead, so those are mapped to the workflows
        that use them — which also means several instances of one template
        no longer have to be several copies of its source in order to be
        told apart.
        """
        active = server.workflow_set_store.get_active_name()
        if active is None:
            return set()
        entries = set(server.workflow_set_store.load(active))
        loaded = set()
        for summary in server.workflow_store.list_all():
            if summary.id in entries:
                loaded.add(summary.id)
                continue
            try:
                graph = server.workflow_store.load(summary.id)
            except Exception:
                continue
            if graph.metadata.get("script_path") in entries:
                loaded.add(summary.id)
        return loaded

    def _find_by_script_path(server: LabPilotServer, script_path: str) -> str | None:
        """Workflow id already registered under this script_path, if any."""
        for summary in server.workflow_store.list_all():
            try:
                graph = server.workflow_store.load(summary.id)
            except Exception:
                continue
            if graph.metadata.get("script_path") == script_path:
                return summary.id
        return None

    @app.get("/api/workflows", response_model=ApiResponse)
    async def list_workflows(server: LabPilotServer = Depends(get_server)):
        """List loaded workflows only — see WorkflowSetPersistence."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")

        try:
            loaded = _loaded_workflow_ids(server)
            workflow_data = []
            for wf in server.workflow_store.list_all():
                if wf.id not in loaded:
                    continue
                graph = server.workflow_store.load(wf.id)
                running = bool(server.workflow_engine and server.workflow_engine.is_running(wf.id))
                latest = server.workflow_store.get_latest_execution(wf.id, include_results=False)
                bindings = graph.metadata.get("instrument_bindings") or {}
                workflow_data.append({
                    "id": wf.id,
                    "name": wf.name,
                    "version": wf.current_version,
                    "created_at": wf.created_at,
                    "updated_at": wf.updated_at,
                    "description": graph.metadata.get("description"),
                    "script_path": graph.metadata.get("script_path"),
                    "running": running,
                    "last_status": latest["status"] if latest else None,
                    "last_completed_at": latest["completed_at"] if latest else None,
                    "connected_instruments": [v for v in bindings.values() if v],
                })
            return ApiResponse(success=True, data=workflow_data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/workflows", response_model=ApiResponse)
    async def create_workflow(
        request: WorkflowCreateRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Create a new workflow and load it (its generated script becomes
        the active workflow-set's newest entry)."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")

        try:
            workflow = WorkflowGraph(name=request.name)
            if request.description:
                workflow.metadata["description"] = request.description
            version = server.workflow_store.save(workflow, "Initial creation")
            server.workflow_set_store.add_to_active(workflow.id)

            return ApiResponse(
                success=True,
                data={
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "version": version,
                    "script_path": workflow.metadata["script_path"],
                }
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # NOTE: must be registered before GET /api/workflows/{workflow_id}
    # below — FastAPI matches routes in registration order, and that
    # wildcard would otherwise swallow "/api/workflows/templates" as if
    # "templates" were a workflow id.
    @app.get("/api/workflows/templates", response_model=ApiResponse)
    async def list_workflow_templates():
        """Library of ready-made, general-purpose workflows (confocal
        scanner, pump-probe, ...) — each references the instruments it
        needs by *role* rather than a literal id (see
        core/workflow/instrument_roles.py), so loading one creates a
        workflow with empty, bindable instrument slots rather than one
        already wired to a specific physical setup."""
        templates = []
        sources: dict[str, str] = {}
        for path in sorted(_workflow_templates_dir().glob("*.py")):
            if path.stem.startswith("_"):
                continue
            text = path.read_text()
            sources[path.stem] = text
            templates.append({
                "name": path.stem,
                "description": read_template_description(text),
                "required_instruments": read_required_instruments(text),
                "preset_of": None,
            })

        # Presets sit in the same list: from here a preset *is* a template
        # you can load — it differs only in that its parameters come from a
        # declaration rather than from its own module's defaults. Its roles
        # are its base template's, since that is the script that will run.
        for preset in load_presets().values():
            text = sources.get(preset.template)
            if text is None:
                print(f"⚠️  Preset {preset.name!r} names unknown template "
                      f"{preset.template!r} — not listed")
                continue
            templates.append({
                "name": preset.name,
                "description": preset.description,
                "required_instruments": read_required_instruments(text),
                "preset_of": preset.template,
            })
        return ApiResponse(success=True, data=sorted(templates, key=lambda t: t["name"]))

    @app.post("/api/workflows/templates/{template_name}/load", response_model=ApiResponse)
    async def load_workflow_template(template_name: str, server: LabPilotServer = Depends(get_server)):
        """Instantiate a template as a new, loaded workflow, with every
        declared instrument role starting unbound.

        The instance is a store row, not a copy of the template's source.
        Loading used to write a timestamped copy of the `.py` into the
        installed package directory (`core/workflow_library/`) — which
        works only on an editable install, mixes user data into the
        framework's own files, and had accumulated 27 committed scripts,
        22 of them the same template across three generations. What
        distinguishes two instances of one template is their parameters and
        their bindings, and both are rows.

        Parameters start from this template's last-saved values (see
        core/config/template_params.py) where it still declares them, so
        reloading a template comes back to how it was last configured
        rather than to its hardcoded defaults.
        """
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")

        # A preset runs its base template's script with different starting
        # parameters — see core/workflow/presets.py. Everything downstream
        # is identical, because a workflow instance was already a row
        # (script path + params + bindings) rather than a copy of a file.
        preset = load_presets().get(template_name)
        script_name = preset.template if preset else template_name
        template_path = _workflow_templates_dir() / f"{script_name}.py"
        if not template_path.exists():
            raise HTTPException(status_code=404, detail=f"No template named {template_name!r}")

        text = template_path.read_text()
        required = read_required_instruments(text)
        declared = read_workflow_params(text)
        # Saved values are keyed by the name that was loaded, so
        # reconfiguring one preset does not move another built on the same
        # template. A preset's own defaults fill in what has not been saved.
        saved_params = server.template_param_store.load(template_name) or {}
        if preset:
            saved_params = {**preset.params, **saved_params}

        graph = WorkflowGraph(name=template_name.replace("_", " ").title())
        graph.metadata["script_path"] = str(template_path)
        graph.metadata["template_name"] = template_name
        graph.metadata["externally_authored"] = True
        graph.metadata["description"] = read_template_description(text)
        graph.metadata["instrument_bindings"] = {role: None for role in required}
        # Only parameters this template still declares — a saved value for
        # one it has since dropped is stale, not a setting.
        graph.metadata["params"] = {
            name: value for name, value in saved_params.items() if name in declared
        }
        server.workflow_store.save(graph, f"Loaded from template {template_name!r}")
        server.workflow_set_store.add_to_active(graph.id)

        return ApiResponse(
            success=True,
            data={"workflow_id": graph.id, "script_path": str(template_path)},
        )

    @app.get("/api/workflows/{workflow_id}", response_model=ApiResponse)
    async def get_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Full graph (nodes/edges/metadata) for one workflow."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        return ApiResponse(success=True, data=json.loads(graph.to_json()))

    @app.get("/api/workflows/{workflow_id}/script", response_model=ApiResponse)
    async def get_workflow_script(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Raw text of the workflow's generated (or externally-authored) script."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        script_path = graph.metadata.get("script_path")
        if not script_path or not Path(script_path).exists():
            raise HTTPException(status_code=404, detail="No script file for this workflow")
        return ApiResponse(success=True, data={"path": script_path, "content": Path(script_path).read_text()})

    @app.put("/api/workflows/{workflow_id}/script", response_model=ApiResponse)
    async def update_workflow_script(
        workflow_id: str, request: WorkflowScriptUpdateRequest, server: LabPilotServer = Depends(get_server)
    ):
        """Save edited script text to its file only — not re-parsed into
        the graph (see core/workflow/script.py's module docstring)."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        script_path = graph.metadata.get("script_path")
        if not script_path:
            raise HTTPException(status_code=404, detail="No script file for this workflow")

        # A template-derived workflow shares the shipped template file, so
        # editing it takes a copy first — into the user's own workflow
        # directory, never into the installed package. Otherwise one
        # instance's edit would rewrite the template every other instance
        # (and every future load) runs.
        if _is_shared_template(script_path):
            target = user_workflow_dir() / f"{_slugify(graph.name)}_{graph.id[:8]}.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            script_path = str(target)
            graph.metadata["script_path"] = script_path
            # `params` stays: it is this workflow's configuration, and it
            # still applies to the copy the same way it applied to the
            # template. Only the file becomes private.
            server.workflow_store.save(graph, "Edited script (copied from template)")
        Path(script_path).write_text(request.content)
        return ApiResponse(success=True, data={"path": script_path})

    def _is_shared_template(script_path: str) -> bool:
        try:
            return Path(script_path).resolve().parent == _workflow_templates_dir().resolve()
        except OSError:
            return False

    def _slugify(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "workflow"

    @app.get("/api/workflows/{workflow_id}/params", response_model=ApiResponse)
    async def get_workflow_params(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """This workflow's own tunable parameters — top-level UPPERCASE
        constants declared in its script (e.g. omniscan.py's
        X_POSITIONS/Y_POSITIONS/SETTLE_TOLERANCE_MM), read by the native
        desktop window (workflow_window.py) as a settings panel specific
        to *this* workflow, distinct from any bound instrument's own
        settings. See core/workflow/instrument_roles.py's
        read_workflow_params.

        The script declares the parameters and their defaults; this
        workflow's own row (`graph.metadata["params"]`) says where it
        differs. Reading them merged, in the order the template author
        wrote them, is what a settings form needs.
        """
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        return ApiResponse(success=True, data=_workflow_params(graph))

    def _workflow_params(graph: WorkflowGraph) -> dict[str, Any]:
        """A workflow's parameters: the script's declared defaults, with
        this instance's saved overrides applied."""
        script_path = graph.metadata.get("script_path")
        if not script_path or not Path(script_path).exists():
            return {}
        declared = read_workflow_params(Path(script_path).read_text())
        for name, value in (graph.metadata.get("params") or {}).items():
            if name in declared:
                declared[name] = value
        return declared

    @app.put("/api/workflows/{workflow_id}/params/{param_name}", response_model=ApiResponse)
    async def set_workflow_param(
        workflow_id: str, param_name: str, request: WorkflowParamUpdateRequest,
        server: LabPilotServer = Depends(get_server),
    ):
        """Change one of this workflow's own tunable parameters.

        Stored on the workflow (`graph.metadata["params"]`), applied to the
        template module when the run starts (see
        `RunManager._execute_script`). It used to be written into the
        script: the instance's private copy of the template had that
        constant's assignment rewritten in place, through an AST span edit.
        Which meant configuring a workflow rewrote source code, the values
        could not be read without parsing Python, and a non-editable
        install could not be configured at all.

        The declared value in the script is still what says a parameter
        exists and what type it is — a form needs both, and the template
        author writes them where they are read.

        If this instance came from a template, the resulting set is also
        persisted to that template's status file
        (core/config/template_params.py), so the next fresh load of the
        same template starts from these values rather than the defaults.
        """
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        current = _workflow_params(graph)
        if not current:
            raise HTTPException(status_code=404, detail="No script file for this workflow")
        if param_name not in current:
            raise HTTPException(status_code=404, detail=f"{param_name!r} is not a tunable parameter of this workflow")

        current_value = current[param_name]
        new_value = request.value
        # A JSON int for a Python constant that's really a float (e.g.
        # SETTLE_TOLERANCE_MM = 0.02, submitted as a bare 50) is a common,
        # harmless case worth coercing rather than rejecting.
        if isinstance(current_value, float) and isinstance(new_value, int) and not isinstance(new_value, bool):
            new_value = float(new_value)
        expected_type = type(current_value)
        if type(new_value) is not expected_type:
            raise HTTPException(
                status_code=422,
                detail=f"{param_name!r} expects a {expected_type.__name__}, got {type(new_value).__name__}",
            )

        params = dict(graph.metadata.get("params") or {})
        params[param_name] = new_value
        graph.metadata["params"] = params
        server.workflow_store.save(graph, f"Set {param_name}")

        template_name = graph.metadata.get("template_name")
        if template_name:
            server.template_param_store.save(template_name, _workflow_params(graph))

        return ApiResponse(success=True, data={"name": param_name, "value": new_value})

    def _resolve_optimize_targets(workflow_id: str, server: LabPilotServer, requested_axes: list[str] | None = None):
        """Shared validation for both start/stop/state — resolves the
        optimizer capability's target actuator/detector roles (falling
        back to inferring them from RESULT_UI's crosshair when a workflow
        declares no explicit CAPABILITIES, see `read_capabilities`), their
        bound+connected instrument adapters, which axes to optimize, and
        the detector's value key. Raises HTTPException on any failure;
        returns (actuator_id, detector_id, axes, axis_ranges)."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        script_path = graph.metadata.get("script_path")
        if not script_path or not Path(script_path).exists():
            raise HTTPException(status_code=404, detail="No script file for this workflow")
        script_text = Path(script_path).read_text()

        capabilities = read_capabilities(script_text)
        optimizer_spec = capabilities.get("optimizer")
        if not optimizer_spec:
            raise HTTPException(status_code=400, detail="This workflow declares no optimizer capability")
        actuator_role = optimizer_spec.get("around")
        if not actuator_role:
            raise HTTPException(status_code=400, detail="This workflow's optimizer capability names no actuator role")

        result_ui = read_result_ui(script_text)
        crosshair = result_ui.get("crosshair") or {}
        x_axis = crosshair.get("x_axis")
        y_axis = crosshair.get("y_axis")

        required = read_required_instruments(script_text)
        detector_role = next((role for role, spec in required.items() if spec.get("kind") == "detector"), None)
        if detector_role is None:
            raise HTTPException(status_code=400, detail="This workflow declares no detector role to optimize against")

        bindings = graph.metadata.get("instrument_bindings", {})
        actuator_id = bindings.get(actuator_role)
        detector_id = bindings.get(detector_role)
        if not actuator_id or not detector_id:
            raise HTTPException(
                status_code=400,
                detail=f"Bind both {actuator_role!r} and {detector_role!r} before optimizing",
            )

        lab = get_dashboard_manager().lab
        if actuator_id not in lab or detector_id not in lab:
            raise HTTPException(status_code=404, detail="Bound instrument not found")
        actuator, detector = lab[actuator_id], lab[detector_id]
        if not actuator.connected or not detector.connected:
            raise HTTPException(status_code=409, detail="Both instruments must be connected to optimize")

        actuator_schema = actuator.schema
        if not detector.schema.readable:
            raise HTTPException(status_code=400, detail="Bound detector declares no readable value")
        if not (server.session.has(actuator_id) and server.session.has(detector_id)):
            raise HTTPException(
                status_code=409,
                detail="Both instruments must be connected to optimize",
            )

        # This workflow's own parameters, not the template's defaults: a
        # scan reconfigured to a different AXIS_RANGES must be optimized
        # over the range it actually scans.
        axes, axis_ranges = resolve_scan_axes(
            _workflow_params(graph), actuator_schema, x_axis, y_axis, requested_axes
        )
        if not axes:
            raise HTTPException(status_code=400, detail="Could not determine which axes to optimize")

        # Ids, not adapters: the plan resolves devices through the session,
        # the same way a workflow's roles are resolved, so an optimize and a
        # scan drive hardware through one path.
        return actuator_id, detector_id, axes, axis_ranges

    async def _run_optimize(
        server: LabPilotServer, workflow_id: str, actuator_id: str, detector_id: str,
        axes: list[str], axis_ranges: dict[str, tuple[float, float, int]],
        search_range: dict[str, float] | None, points: int,
        points_per_axis_override: dict[str, int] | None = None,
    ) -> None:
        """Background task running the whole optimize sequence — the
        OptimizerDockWidget (see workflow_window.py) polls
        `server.optimize_states[workflow_id]["progress"]` as this fills
        in, one pane per step (qudi's own `OptimizerDockWidget`,
        `UI_FRAMEWORK_DESIGN.md` §2.6), the same live-progress feel a full
        workflow run gets from report_progress(), scoped to this small
        re-scan-and-recenter sequence instead of the workflow's own script.

        `progress`/`last_result` are shaped `{"sequence": [...], "steps":
        {step_index: {...}}}` — a dict KEYED BY STEP, not overwritten
        wholesale on every callback, so a completed earlier step's final
        fit stays visible once a later step starts (a poller only ever
        sees one `progress` snapshot at a time; overwriting the whole
        thing with just the newest step's data would lose every prior
        step's result the instant the sequence moved on, well before a
        poll could ever have seen it).

        The sequence itself is an `OptimizePlan`, so aborting it stops at
        a point boundary and keeps what it measured, exactly as stopping a
        scan does — where cancelling the task left the sub-scan's
        detector staged and the stage still travelling.
        """
        state = server.optimize_states[workflow_id]
        points_per_axis_override = points_per_axis_override or {}
        points_per_axis = {ax: max(2, points_per_axis_override.get(ax, points)) for ax in axes}

        async def on_step(progress: dict) -> None:
            current = state.get("progress") or {"sequence": progress.get("sequence"), "steps": {}}
            current["sequence"] = progress.get("sequence", current.get("sequence"))
            current["steps"][progress["step_index"]] = progress
            current["current_step_index"] = progress["step_index"]
            state["progress"] = current

        plan = OptimizePlan(
            axes=axes, axis_ranges=axis_ranges,
            actuator=actuator_id, detector=detector_id,
            search_range=search_range, points_per_axis=points_per_axis,
            on_step=on_step,
        )
        try:
            run = await prepare(server.session, plan)
            server._optimize_runs[workflow_id] = run
            await run.execute(plan.points(server.session, run.descriptor))
        except (asyncio.CancelledError, RunAbortedError):
            pass
        except Exception as e:
            state["error"] = str(e)
        finally:
            state["last_result"] = {
                "sequence": plan.sequence,
                "steps": {step["step_index"]: step for step in plan.steps},
                "best_position": plan.best_position,
            }
            state["running"] = False
            server._optimize_runs.pop(workflow_id, None)

    @app.post("/api/workflows/{workflow_id}/optimize/start", response_model=ApiResponse)
    async def start_optimize(
        workflow_id: str, request: WorkflowOptimizeRequest, server: LabPilotServer = Depends(get_server)
    ):
        """Starts (as a background task) re-centering a workflow's
        crosshair-bound actuator on its detector's local maximum — a
        small ad-hoc grid scan around the actuator's *current* position
        (not a run of the workflow's own script), generalizing qudi's
        `scanning_optimize_logic.py`/`OptimizerDockWidget` (a quick,
        *live-watchable* re-scan-and-recenter routine) beyond a single
        blocking call. Poll GET .../optimize/state for progress; only one
        optimize can run at a time per workflow."""
        if server.optimize_states.get(workflow_id, {}).get("running"):
            raise HTTPException(status_code=409, detail="Optimize already running for this workflow")
        # Reserve the slot immediately, with no `await` between the check
        # above and this set — two /optimize/start calls arriving close
        # together would otherwise both pass the check before either sets
        # "running", since everything below this line awaits (hardware
        # I/O) and yields the event loop to exactly that second call.
        server.optimize_states[workflow_id] = {
            "running": True, "progress": None, "last_result": None, "error": None,
        }
        try:
            actuator_id, detector_id, axes, axis_ranges = _resolve_optimize_targets(
                workflow_id, server, request.axes,
            )
        except HTTPException:
            server.optimize_states[workflow_id]["running"] = False
            raise
        except Exception as e:
            server.optimize_states[workflow_id]["running"] = False
            raise HTTPException(status_code=502, detail=f"Failed to resolve optimize targets: {e}")

        task = asyncio.create_task(
            _run_optimize(server, workflow_id, actuator_id, detector_id, axes, axis_ranges,
                          request.ranges, request.points, request.points_per_axis)
        )
        server._optimize_tasks[workflow_id] = task
        return ApiResponse(success=True, data={"started": True})

    @app.post("/api/workflows/{workflow_id}/optimize/stop", response_model=ApiResponse)
    async def stop_optimize(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Stops an in-flight optimize, if any (a no-op otherwise).

        The actuator stays where the scan had reached — it is not moved
        back, nor on to the best point found so far — but it is told to
        stop: cancelling the task ends the loop that commands the stage
        while leaving the stage travelling to the position it was last
        sent to. Same reasoning, and the same `Motor.stop()`, as
        RunManager.stop_workflow.
        """
        run = server._optimize_runs.get(workflow_id)
        if run is not None:
            # Stops at the next point boundary, unstages the detector and
            # stops the actuator — the same abort a scan gets.
            run.abort()
        else:
            task = server._optimize_tasks.get(workflow_id)
            if task is not None and not task.done():
                task.cancel()
        state = server.optimize_states.get(workflow_id)
        if state is not None:
            state["running"] = False
        return ApiResponse(success=True, data={"stopped": True})

    @app.get("/api/workflows/{workflow_id}/optimize/state", response_model=ApiResponse)
    async def get_optimize_state(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Polled by the OptimizerDockWidget — {running, progress
        (the grid so far, live), last_result (the final grid once
        finished), error}."""
        state = server.optimize_states.get(
            workflow_id, {"running": False, "progress": None, "last_result": None, "error": None}
        )
        return ApiResponse(success=True, data=state)

    @app.post("/api/workflows/{workflow_id}/execute", response_model=ApiResponse)
    async def execute_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Execute a workflow — either its node graph, or (if it has no
        nodes, e.g. a hand/AI-written script loaded directly) its script's
        `run(session)` function, per RunManager._execute_script."""
        if not server.workflow_engine or not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        if not graph.nodes and not graph.metadata.get("script_path"):
            raise HTTPException(
                status_code=400,
                detail="This workflow has no nodes and no script — nothing to run.",
            )
        try:
            execution_id = await server.workflow_engine.start_workflow(workflow_id)
            return ApiResponse(success=True, data={"execution_id": execution_id})
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/workflows/{workflow_id}/stop", response_model=ApiResponse)
    async def stop_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Stop a running workflow.

        A workflow running a plan stops at its next point boundary, keeping
        what it measured and telling its actuators to stop; anything else is
        cancelled where it stands. See RunManager.stop_workflow.
        """
        if not server.workflow_engine:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        try:
            await server.workflow_engine.stop_workflow(workflow_id)
            return ApiResponse(success=True, data={"message": f"Stopped workflow {workflow_id}"})
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/workflows/{workflow_id}/pause", response_model=ApiResponse)
    async def pause_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Hold a running scan at its next point boundary, resumable.

        409 when this workflow is not running a plan: a script running its
        own loop has no boundary to hold at, and reporting a pause that did
        not happen is what the old FSM-only pause did.
        """
        if not server.workflow_engine:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        if not await server.workflow_engine.pause_workflow(workflow_id):
            raise HTTPException(
                status_code=409,
                detail=f"Workflow {workflow_id} is not running a pausable plan",
            )
        return ApiResponse(success=True, data=server.workflow_engine.run_state(workflow_id))

    @app.post("/api/workflows/{workflow_id}/resume", response_model=ApiResponse)
    async def resume_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Continue a paused scan from the point where it stopped."""
        if not server.workflow_engine:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        if not await server.workflow_engine.resume_workflow(workflow_id):
            raise HTTPException(
                status_code=409,
                detail=f"Workflow {workflow_id} is not running a pausable plan",
            )
        return ApiResponse(success=True, data=server.workflow_engine.run_state(workflow_id))

    @app.delete("/api/workflows/{workflow_id}", response_model=ApiResponse)
    async def unload_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Unload from the Workflows tab — removes it from the active
        workflow-set only. The script file and the WorkflowStore row
        (history/versions) are untouched."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        # Both forms: a workflow loaded before the set stored ids is listed
        # by its script path.
        server.workflow_set_store.remove_from_active(
            workflow_id, graph.metadata.get("script_path") or ""
        )
        return ApiResponse(success=True, data={"message": f"Unloaded {workflow_id}"})

    @app.post("/api/workflows/load", response_model=ApiResponse)
    async def load_workflow(request: WorkflowLoadRequest, server: LabPilotServer = Depends(get_server)):
        """Add a script path to the active workflow-set. If it isn't
        already backed by a WorkflowStore graph, register a minimal
        placeholder so it has an id to list/view — it's still immediately
        Execute-able (see RunManager._execute_script): a script's
        `run(session)` runs directly, no node graph required."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"No file at {request.path}")
        script_path = str(path)

        workflow_id = _find_by_script_path(server, script_path)
        if workflow_id is None:
            graph = WorkflowGraph(name=path.stem)
            graph.metadata["script_path"] = script_path
            graph.metadata["externally_authored"] = True
            server.workflow_store.save(graph, "Loaded from external script")
            workflow_id = graph.id

        server.workflow_set_store.add_to_active(workflow_id)
        return ApiResponse(success=True, data={"workflow_id": workflow_id, "script_path": script_path})

    @app.get("/api/workflows/{workflow_id}/bindings", response_model=ApiResponse)
    async def get_workflow_bindings(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Each instrument role this workflow declares, merged with
        whichever real instrument (if any) is currently bound to it."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        script_path = graph.metadata.get("script_path")
        required = read_required_instruments_from_file(script_path) if script_path else {}
        bindings = graph.metadata.get("instrument_bindings", {})
        roles = [
            {
                "role": role,
                "kind": requirement.get("kind"),
                "dimensionality": requirement.get("dimensionality"),
                "instrument_id": bindings.get(role),
                # e.g. omniscan.py's "scanner" role — an alternative to
                # its "actuator"/"detector" pair, not required alongside
                # them (see engine.py's _check_instrument_bindings, which
                # already skips this same flag). Surfaced so a client can
                # visually de-emphasize/hide an optional, unbound role
                # instead of showing it identically to a required one.
                "optional": bool(requirement.get("optional")),
            }
            for role, requirement in required.items()
        ]
        return ApiResponse(success=True, data={"roles": roles})

    @app.put("/api/workflows/{workflow_id}/bindings/{role}", response_model=ApiResponse)
    async def set_workflow_binding(
        workflow_id: str, role: str, request: WorkflowBindingRequest, server: LabPilotServer = Depends(get_server)
    ):
        """Bind (or, with instrument_id=None, unbind) one instrument role
        to a real connected instrument — see
        core/workflow/instrument_roles.py. Validates the instrument's
        kind/dimensionality matches what the role requires before
        accepting the binding."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        script_path = graph.metadata.get("script_path")
        required = read_required_instruments_from_file(script_path) if script_path else {}
        if role not in required:
            raise HTTPException(status_code=404, detail=f"This workflow declares no role {role!r}")

        if request.instrument_id is not None:
            lab = get_dashboard_manager().lab
            if request.instrument_id not in lab:
                raise HTTPException(status_code=404, detail=f"Instrument {request.instrument_id!r} not found")
            handle = lab[request.instrument_id]
            requirement = required[role]
            actual_kind = handle.schema.kind
            actual_dim = handle.dimensionality
            if requirement.get("kind") and actual_kind != requirement["kind"]:
                raise HTTPException(
                    status_code=422,
                    detail=f"Role {role!r} needs kind={requirement['kind']!r}, "
                           f"but {request.instrument_id!r} is {actual_kind!r}",
                )
            if requirement.get("dimensionality") and actual_dim != requirement["dimensionality"]:
                raise HTTPException(
                    status_code=422,
                    detail=f"Role {role!r} needs dimensionality={requirement['dimensionality']!r}, "
                           f"but {request.instrument_id!r} is {actual_dim!r}",
                )

        bindings = dict(graph.metadata.get("instrument_bindings", {}))
        bindings[role] = request.instrument_id
        graph.metadata["instrument_bindings"] = bindings
        server.workflow_store.save(graph, f"{'Bound' if request.instrument_id else 'Unbound'} role {role!r}")

        return ApiResponse(success=True, data={"role": role, "instrument_id": request.instrument_id})

    @app.get("/api/workflows/{workflow_id}/execution_state", response_model=ApiResponse)
    async def get_workflow_execution_state(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Merges live (in-progress) and last-completed execution state into
        one response — polled by the native desktop window
        (workflow_window.py) to drive a live result view, and usable by any
        client that just wants "what happened last time"."""
        if not server.workflow_store or not server.workflow_engine:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        running = server.workflow_engine.is_running(workflow_id)
        progress = server.workflow_engine.get_live_progress(workflow_id) if running else None
        latest = server.workflow_store.get_latest_execution(workflow_id)
        return ApiResponse(success=True, data={
            "running": running,
            # Present only while a plan is executing: whether it is paused,
            # and how far through it is, without inferring either from the
            # size of the last progress frame.
            "run": server.workflow_engine.run_state(workflow_id),
            "execution_id": latest["execution_id"] if latest else None,
            "progress": progress,
            "last_status": latest["status"] if latest else None,
            "last_started_at": latest["started_at"] if latest else None,
            "last_completed_at": latest["completed_at"] if latest else None,
            "last_results": latest["results"] if latest else None,
        })

    @app.post("/api/instruments/{instrument_id}/launch-qt", response_model=ApiResponse)
    async def launch_qt_window(
        instrument_id: str,
        request: QtLaunchRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Launch Qt window for specific instrument."""
        try:
            import sys

            # Find Qt desktop shell path (src/labpilot/ui/desktop/)
            qt_frontend_path = Path(__file__).parent.parent / "ui" / "desktop"
            if not qt_frontend_path.exists():
                # Try alternative paths
                for search_path in [
                    Path.cwd() / "src" / "labpilot" / "ui" / "desktop",
                    Path.cwd() / "labpilot" / "ui" / "desktop",
                ]:
                    if search_path.exists():
                        qt_frontend_path = search_path
                        break
                else:
                    raise HTTPException(
                        status_code=404,
                        detail="Qt frontend directory not found"
                    )

            launch_script = qt_frontend_path / "launch_instrument.py"
            if not launch_script.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Qt launch script not found"
                )

            # Launch Qt window
            cmd = [
                sys.executable,
                str(launch_script),
                "--instrument", request.instrument_id,
                "--type", request.instrument_type,
                "--dimensionality", request.dimensionality
            ]

            process = subprocess.Popen(
                cmd,
                cwd=qt_frontend_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait briefly to check if launch was successful
            time.sleep(0.5)

            if process.poll() is None:
                # Process is still running, launch successful
                return ApiResponse(
                    success=True,
                    data={
                        "message": f"Qt window launched for {request.instrument_id}",
                        "pid": process.pid,
                        "instrument_id": request.instrument_id
                    }
                )
            else:
                # Process exited, check for errors
                stdout, stderr = process.communicate()
                if process.returncode == 0:
                    return ApiResponse(
                        success=True,
                        data={
                            "message": f"Qt window launched for {request.instrument_id}",
                            "output": stdout
                        }
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Qt launch failed: {stderr}"
                    )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to launch Qt window: {e!s}")

    @app.get("/api/config", response_model=ApiResponse)
    async def get_config_summary(server: LabPilotServer = Depends(get_server)):
        """Get configuration summary."""
        summary = server.config_persistence.get_config_summary()
        return ApiResponse(success=True, data=summary)

    @app.post("/api/config/save", response_model=ApiResponse)
    async def save_config(server: LabPilotServer = Depends(get_server)):
        """Save current session configuration."""
        try:
            config = server.config_persistence.from_session(server.session)
            config_path = server.config_persistence.save_session_config(config)

            return ApiResponse(
                success=True,
                data={"message": f"Configuration saved to {config_path}"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/session/config", response_model=ApiResponse)
    async def get_session_config(server: LabPilotServer = Depends(get_server)):
        """Get current session configuration."""
        try:
            # Convert session to config format
            config = server.config_persistence.from_session(server.session)

            # Return comprehensive session state
            session_data = {
                "session_id": config.session_id,
                "created_at": config.created_at,
                "updated_at": config.updated_at,
                "preferences": asdict(config.preferences),
                "devices": [asdict(device) for device in config.devices],
                "active_workflow_id": config.active_workflow_id,
                "recent_scans": config.recent_scans,
            }

            return ApiResponse(success=True, data=session_data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # WebSocket endpoint for real-time communication
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, server: LabPilotServer = Depends(get_server)):
        await server.websocket_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive and handle client messages
                data = await websocket.receive_text()
                message = json.loads(data)

                if message.get("type") == "ping":
                    await server.websocket_manager.send_personal_message(
                        json.dumps({"type": "pong"}), websocket
                    )

        except WebSocketDisconnect:
            server.websocket_manager.disconnect(websocket)

    # Serve React frontend (in production)
    if Path("frontend/build").exists():
        # Vite outputs to 'assets', not 'static'
        assets_dir = Path("frontend/build/assets")
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory="frontend/build/assets"), name="assets")

        @app.get("/", response_class=HTMLResponse)
        async def serve_frontend():
            with open("frontend/build/index.html") as f:
                return HTMLResponse(f.read())

    return app


# CLI entry point
if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True  # For development
    )
