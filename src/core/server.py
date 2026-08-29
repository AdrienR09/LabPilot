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
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.ai import AISession
from core.ai.structured_prompt import (
    clean_response_text,
    extract_structured_prompt,
)
from core.api.dashboard import initialize_dashboard, get_dashboard_manager
from core.api.dashboard import router as dashboard_router
from core.config import (
    ConfigPersistence,
)
from core.config.template_params import TemplateParamPersistence
from core.config.workflow_sets import WorkflowSetPersistence
from core.events import EventKind
from core.session import Session
from core.workflow import WorkflowEngine, WorkflowGraph, WorkflowStore
from core.workflow.capabilities import OptimizerCapability
from core.workflow.instrument_roles import (
    read_required_instruments,
    read_required_instruments_from_file,
    read_template_description,
    read_result_ui,
    read_capabilities,
    read_workflow_params,
    write_workflow_param,
)

__all__ = ["LabPilotServer", "create_app"]

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
    sub-scans around its current position (`core/workflow/capabilities.py`'s
    `OptimizerCapability`), not a full run of the workflow's own script.

    `axes`, if given, is the EXACT set of actuator axes to optimize over
    (validated against what's actually available — see
    `_resolve_optimize_axes`) — "select if you want to optimize along one
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


class QtLaunchRequest(BaseModel):
    """Request to launch Qt instrument window."""
    instrument_id: str
    instrument_type: str
    dimensionality: str


class ChatRequest(BaseModel):
    """AI chat request."""
    message: str
    conversation_id: str = "default"
    use_tools: bool = True
    # Scopes the AI's system context to one workflow (its graph + script
    # text) so it can see/modify real code instead of generating blind —
    # set when the chat is opened from a specific workflow (see frontend's
    # openAIChat()). None for a general chat or a brand-new workflow.
    workflow_id: str | None = None


class ChatResponse(BaseModel):
    """AI chat response."""
    response: str
    conversation_id: str
    tool_calls: int = 0
    structured_prompt: dict[str, Any] | None = None


# Any single WORKFLOW_PROGRESS field with more elements than this is
# dropped from the WebSocket broadcast (see LabPilotServer._event_broadcaster)
# — large enough that a live 1D scan/spectrum curve still broadcasts in
# full, small enough that a 2D image or ND scan's flat data array (which
# can reach millions of elements) doesn't get re-serialized every point.
_PROGRESS_BROADCAST_LIMIT = 4096


def _flat_len(value: Any, _depth: int = 0) -> int:
    """Element count of `value`, flattening one level of list-of-lists
    (image-style 2D payloads) so e.g. a 100x100 image reports 10000, not
    100. Non-list values (scalars, dicts, None) count as 0 — only list
    payloads are ever large enough to matter here."""
    if not isinstance(value, list):
        return 0
    if _depth == 0 and value and isinstance(value[0], list):
        return sum(_flat_len(row, _depth + 1) for row in value)
    return len(value)


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
        self.ai_session: AISession | None = None
        self.workflow_store: WorkflowStore | None = None
        self.workflow_engine: WorkflowEngine | None = None
        self.workflow_set_store = WorkflowSetPersistence(self.config_persistence.config_dir)
        self.template_param_store = TemplateParamPersistence(self.config_persistence.config_dir)
        self.websocket_manager = WebSocketManager()
        self._event_task: asyncio.Task | None = None
        # One in-flight optimize run per workflow — a small ad-hoc grid
        # scan around the crosshair-bound actuator's current position,
        # separate from a full run of the workflow's own script (see
        # /api/workflows/{id}/optimize/start below). Tracked here rather
        # than through WorkflowEngine's own execution-state machinery
        # since it isn't a run of the workflow's script at all.
        self.optimize_states: dict[str, dict] = {}
        self._optimize_tasks: dict[str, asyncio.Task] = {}

    async def initialize(self):
        """Initialize server components."""
        # Load session configuration
        config = self.config_persistence.load_session_config()
        if config:
            self.config_persistence.to_session(config, self.session)

        # Initialize workflow components
        db_path = self.config_persistence.config_dir / "workflows" / "workflows.db"
        self.workflow_store = WorkflowStore(db_path)
        self.workflow_engine = WorkflowEngine(self.session, self.workflow_store)

        # First run: nothing loaded yet — seed the active workflow-set from
        # whatever's already in the store with a real script_path, so
        # existing genuine workflows keep showing up. Anything without one
        # (e.g. leftover empty test graphs) is naturally excluded rather
        # than needing explicit cleanup.
        if self.workflow_set_store.get_active_name() is None:
            seeded_paths = []
            for summary in self.workflow_store.list_all():
                try:
                    graph = self.workflow_store.load(summary.id)
                except Exception:
                    continue
                script_path = graph.metadata.get("script_path")
                if script_path:
                    seeded_paths.append(script_path)
            self.workflow_set_store.save(WorkflowSetPersistence.DEFAULT_NAME, seeded_paths)
            self.workflow_set_store.set_active_name(WorkflowSetPersistence.DEFAULT_NAME)

        # Initialize AI session if configured
        try:
            self.ai_session = AISession(
                self.session, self.workflow_store, self.workflow_engine, self.workflow_set_store,
                config_persistence=self.config_persistence,
            )
            # Try to initialize with default Ollama config
            # Using mistral (better at function calling than llama3.1)
            await self.ai_session.initialize({
                "type": "ollama",
                "model": "mistral",
                "base_url": "http://localhost:11434",
                "timeout": 120.0  # Increased timeout for initial tool-heavy requests
            })
        except Exception as e:
            print(f"AI initialization failed (will retry later): {e}")
            self.ai_session = None

        # Start event broadcasting
        self._event_task = asyncio.create_task(self._event_broadcaster())

        # A dashboard-connected instrument must also be resolvable by name
        # from a workflow node (WorkflowEngine reads through self.session,
        # the dashboard's own instrument registry is separate) — attach the
        # session before any instrument can connect.
        get_dashboard_manager().set_session(self.session)

        # Initialize dashboard: load/seed the active instrument-set config.
        await initialize_dashboard()

    async def shutdown(self):
        """Shutdown server components."""
        if self._event_task:
            self._event_task.cancel()

        if self.ai_session:
            await self.ai_session.shutdown()

    async def _event_broadcaster(self):
        """Broadcast LabPilot events to WebSocket clients."""
        try:
            async for event in self.session.bus.subscribe():
                # A WORKFLOW_PROGRESS event's data includes the scan's full
                # accumulated flat array (session.report_progress() sends
                # the whole thing, not a delta) — for an ND scan that's up
                # to millions of floats, growing every point. json.dumps-ing
                # that on EVERY reported point, unconditionally, is pure
                # waste with zero WebSocket clients connected (the common
                # case today) and was competing for the same asyncio event
                # loop the workflow script itself runs on — a real
                # contributor to "scan acquisition takes a long time".
                # Skip the serialize+broadcast entirely when nobody's
                # listening.
                if not self.websocket_manager.active_connections:
                    continue
                event_dict = event.to_dict()
                if event.kind == EventKind.WORKFLOW_PROGRESS:
                    # Even WITH a listener connected, broadcasting the full
                    # array on every single point reintroduces the same
                    # O(size) cost per tick, now permanently (a workflow
                    # window is always listening while open) instead of
                    # only every poll interval. Measured: the same scan
                    # went from finishing in <6s with no listener to still
                    # running after 9s (and climbing per-point) with one
                    # connected, purely from this serialization. The WS
                    # push only needs to tell the client "something changed
                    # and here's the shape of it" — the client re-fetches
                    # the actual (still full, but throttled) snapshot via
                    # GET execution_state when it wants to render (see
                    # WorkflowStatePoller._on_message in the desktop app).
                    # Every RESULT_UI-producing template names its bulky
                    # array differently (omniscan's "data", generic_2d_scan/
                    # confocal_scanner/hyperspectral_imaging's "image"/
                    # "live_image", ...), so this drops by estimated size,
                    # not by name — any field whose total element count
                    # (flattening one level of nesting for image-style
                    # list-of-lists) is past the threshold.
                    event_dict = dict(event_dict)
                    event_dict["data"] = {
                        k: v for k, v in event_dict["data"].items()
                        if _flat_len(v) <= _PROGRESS_BROADCAST_LIMIT
                    }
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

    @app.get("/api/session/status", response_model=ApiResponse)
    async def get_session_status(server: LabPilotServer = Depends(get_server)):
        """Get current session status."""
        return ApiResponse(
            success=True,
            data={
                "session_id": getattr(server.session, "_config", {}).get("session_id", "default"),
                "devices_connected": len(server.session.devices),
                "ai_available": server.ai_session is not None,
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
        """Connect a new device."""
        try:
            # This would use the adapter registry to create and connect device
            # For now, return mock success
            return ApiResponse(
                success=True,
                data={"message": f"Device '{request.name}' connected successfully"}
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/devices/{device_name}", response_model=ApiResponse)
    async def disconnect_device(
        device_name: str,
        server: LabPilotServer = Depends(get_server)
    ):
        """Disconnect a device."""
        if device_name not in server.session.devices:
            raise HTTPException(status_code=404, detail=f"Device '{device_name}' not found")

        try:
            # Remove device from session
            del server.session.devices[device_name]
            return ApiResponse(
                success=True,
                data={"message": f"Device '{device_name}' disconnected"}
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    def _loaded_script_paths(server: LabPilotServer) -> list[str]:
        """Script paths in the currently active workflow-set — the
        Workflows tab only ever shows workflows whose script_path is in
        this list (see WorkflowSetPersistence)."""
        active = server.workflow_set_store.get_active_name()
        if active is None:
            return []
        return server.workflow_set_store.load(active)

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
            loaded_paths = set(_loaded_script_paths(server))
            workflow_data = []
            for wf in server.workflow_store.list_all():
                graph = server.workflow_store.load(wf.id)
                if graph.metadata.get("script_path") not in loaded_paths:
                    continue
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
            server.workflow_set_store.add_to_active(workflow.metadata["script_path"])

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

    def _workflow_templates_dir() -> Path:
        import core.workflow_templates as _workflow_templates
        return Path(_workflow_templates.__path__[0])

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
        for path in sorted(_workflow_templates_dir().glob("*.py")):
            if path.stem.startswith("_"):
                continue
            text = path.read_text()
            templates.append({
                "name": path.stem,
                "description": read_template_description(text),
                "required_instruments": read_required_instruments(text),
            })
        return ApiResponse(success=True, data=templates)

    @app.post("/api/workflows/templates/{template_name}/load", response_model=ApiResponse)
    async def load_workflow_template(template_name: str, server: LabPilotServer = Depends(get_server)):
        """Instantiate a template as a new, loaded workflow — copies its
        script into workflow_library/ (mirrors WriteWorkflowScriptTool's
        copy-and-register pattern exactly) with every declared instrument
        role starting unbound.

        Pre-filled from this template's last-saved parameter values (see
        core/config/template_params.py), if any exist — carrying forward
        AXIS_RANGES/SCAN_AXES/HOLD_POSITIONS/etc. from the last time this
        same template was configured, rather than always resetting to its
        hardcoded defaults, "so I can come back to those parameters when
        reloading the workflow"."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        template_path = _workflow_templates_dir() / f"{template_name}.py"
        if not template_path.exists():
            raise HTTPException(status_code=404, detail=f"No template named {template_name!r}")

        import re
        import time as time_module
        import core.workflow_library as _workflow_library

        text = template_path.read_text()
        required = read_required_instruments(text)

        saved_params = server.template_param_store.load(template_name)
        if saved_params:
            current_names = set(read_workflow_params(text).keys())
            for name, value in saved_params.items():
                if name not in current_names:
                    continue  # a param this template no longer declares — drop it rather than inject a stale one
                try:
                    text = write_workflow_param(text, name, value)
                except ValueError:
                    continue

        slug = re.sub(r"[^a-z0-9]+", "_", template_name.lower()).strip("_") or "workflow"
        script_dir = Path(_workflow_library.__path__[0])
        script_path = script_dir / f"{slug}_{int(time_module.time())}.py"
        script_path.write_text(text)

        graph = WorkflowGraph(name=template_name.replace("_", " ").title())
        graph.metadata["script_path"] = str(script_path)
        graph.metadata["template_name"] = template_name
        graph.metadata["externally_authored"] = True
        graph.metadata["description"] = read_template_description(text)
        graph.metadata["instrument_bindings"] = {role: None for role in required}
        server.workflow_store.save(graph, f"Loaded from template {template_name!r}")
        server.workflow_set_store.add_to_active(str(script_path))

        return ApiResponse(success=True, data={"workflow_id": graph.id, "script_path": str(script_path)})

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
        Path(script_path).write_text(request.content)
        return ApiResponse(success=True, data={"path": script_path})

    @app.get("/api/workflows/{workflow_id}/params", response_model=ApiResponse)
    async def get_workflow_params(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """This workflow's own tunable parameters — top-level UPPERCASE
        constants declared in its script (e.g. confocal_scanner.py's
        X_POSITIONS/Y_POSITIONS/SETTLE_TOLERANCE_MM), read by the native
        desktop window (workflow_window.py) as a settings panel specific
        to *this* workflow, distinct from any bound instrument's own
        settings. See core/workflow/instrument_roles.py's
        read_workflow_params."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        script_path = graph.metadata.get("script_path")
        if not script_path or not Path(script_path).exists():
            return ApiResponse(success=True, data={})
        return ApiResponse(success=True, data=read_workflow_params(Path(script_path).read_text()))

    @app.put("/api/workflows/{workflow_id}/params/{param_name}", response_model=ApiResponse)
    async def set_workflow_param(
        workflow_id: str, param_name: str, request: WorkflowParamUpdateRequest,
        server: LabPilotServer = Depends(get_server),
    ):
        """Changes one of this workflow's own tunable parameters in place
        — a precise, targeted edit of just that constant's value in the
        script text (see write_workflow_param), not a full script
        rewrite.

        If this instance came from a template (`graph.metadata
        ["template_name"]`, set by load_workflow_template), also persists
        the complete resulting parameter set to that template's status
        file (core/config/template_params.py) — so the NEXT time this
        template is loaded fresh, it starts from these values instead of
        the template's original hardcoded defaults."""
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
        current = read_workflow_params(script_text)
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

        try:
            new_script = write_workflow_param(script_text, param_name, new_value)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        Path(script_path).write_text(new_script)

        template_name = graph.metadata.get("template_name")
        if template_name:
            server.template_param_store.save(template_name, read_workflow_params(new_script))

        return ApiResponse(success=True, data={"name": param_name, "value": new_value})

    def _resolve_optimize_axes(
        script_text: str, actuator_schema, x_axis: str | None, y_axis: str | None,
        requested_axes: list[str] | None = None,
    ) -> tuple[list[str], dict[str, tuple[float, float, int]]]:
        """Which actuator axes to run the optimize sequence over, and each
        one's own declared span (used only to derive a default search
        range — see `WorkflowOptimizeRequest.ranges`). Prefers an
        omniscan-style `AXIS_RANGES`/`SCAN_AXES` declaration (any number of
        axes, intersected with what the bound actuator's schema actually
        has); falls back to the crosshair's own fixed `x_axis`/`y_axis`
        pair (e.g. confocal_scanner.py, which declares neither) using
        whatever `X_POSITIONS`/`Y_POSITIONS`-style explicit lists it has
        for a span, or a harmless placeholder span if it has none at all —
        that workflow's optimize behavior is otherwise unchanged from
        before this phase.

        `requested_axes` (`WorkflowOptimizeRequest.axes` — "select if you
        want to optimize along one dimension or multiple dimensions"), if
        given, narrows the result to just that subset (still validated
        against what's actually available — a requested axis this
        workflow doesn't have is silently dropped rather than erroring,
        matching how an unavailable SCAN_AXES entry is already handled
        elsewhere)."""
        params = read_workflow_params(script_text)
        axis_ranges = params.get("AXIS_RANGES")
        scan_axes = params.get("SCAN_AXES")
        if isinstance(axis_ranges, dict) and isinstance(scan_axes, list):
            settable = actuator_schema.settable
            axes = [a for a in scan_axes if a in axis_ranges and a in settable]
            if axes:
                if requested_axes is not None:
                    axes = [a for a in requested_axes if a in axes]
                return axes, {a: tuple(axis_ranges[a]) for a in axes}

        axes = [a for a in (x_axis, y_axis) if a]
        if requested_axes is not None:
            axes = [a for a in requested_axes if a in axes]
        ranges: dict[str, tuple[float, float, int]] = {}
        for axis, list_key in ((x_axis, "X_POSITIONS"), (y_axis, "Y_POSITIONS")):
            if not axis:
                continue
            positions = params.get(list_key)
            if isinstance(positions, list) and len(positions) >= 2:
                ranges[axis] = (float(min(positions)), float(max(positions)), len(positions))
            else:
                ranges[axis] = (-0.5, 0.5, 5)
        return axes, ranges

    def _resolve_optimize_targets(workflow_id: str, server: LabPilotServer, requested_axes: list[str] | None = None):
        """Shared validation for both start/stop/state — resolves the
        optimizer capability's target actuator/detector roles (falling
        back to inferring them from RESULT_UI's crosshair when a workflow
        declares no explicit CAPABILITIES, see `read_capabilities`), their
        bound+connected instrument adapters, which axes to optimize, and
        the detector's value key. Raises HTTPException on any failure;
        returns (actuator, detector, axes, axis_ranges, value_key)."""
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

        manager = get_dashboard_manager()
        if actuator_id not in manager.instruments or detector_id not in manager.instruments:
            raise HTTPException(status_code=404, detail="Bound instrument not found")
        actuator = manager.instruments[actuator_id]["adapter"]
        detector = manager.instruments[detector_id]["adapter"]
        if not actuator.connected or not detector.connected:
            raise HTTPException(status_code=409, detail="Both instruments must be connected to optimize")

        actuator_schema = manager.instruments[actuator_id]["schema"]
        detector_schema = manager.instruments[detector_id]["schema"]
        value_key = next(iter(detector_schema.readable.keys()), None)
        if value_key is None:
            raise HTTPException(status_code=400, detail="Bound detector declares no readable value")

        axes, axis_ranges = _resolve_optimize_axes(script_text, actuator_schema, x_axis, y_axis, requested_axes)
        if not axes:
            raise HTTPException(status_code=400, detail="Could not determine which axes to optimize")

        return actuator, detector, axes, axis_ranges, value_key

    async def _run_optimize(
        server: LabPilotServer, workflow_id: str, actuator, detector,
        axes: list[str], axis_ranges: dict[str, tuple[float, float, int]],
        search_range: dict[str, float] | None, points: int,
        points_per_axis_override: dict[str, int] | None = None,
    ) -> None:
        """Background task running the whole optimize sequence — the
        OptimizerDockWidget (see workflow_window.py) polls
        `server.optimize_states[workflow_id]["progress"]` as this fills
        in, one pane per `OptimizerSequence` step (qudi's own
        `OptimizerDockWidget`, `UI_FRAMEWORK_DESIGN.md` §2.6), the same
        live-progress feel a full workflow run gets from
        report_progress(), scoped to this small re-scan-and-recenter
        sequence instead of the workflow's own script.

        `progress`/`last_result` are shaped `{"sequence": [...], "steps":
        {step_index: {...}}}` — a dict KEYED BY STEP, not overwritten
        wholesale on every callback, so a completed earlier step's final
        fit stays visible once a later step starts (a poller only ever
        sees one `progress` snapshot at a time; overwriting the whole
        thing with just the newest step's data would lose every prior
        step's result the instant the sequence moved on, well before a
        poll could ever have seen it)."""
        state = server.optimize_states[workflow_id]
        points_per_axis_override = points_per_axis_override or {}
        points_per_axis = {ax: max(2, points_per_axis_override.get(ax, points)) for ax in axes}
        optimizer = OptimizerCapability(actuator, detector)

        async def on_progress(progress: dict) -> None:
            current = state.get("progress") or {"sequence": progress.get("sequence"), "steps": {}}
            current["sequence"] = progress.get("sequence", current.get("sequence"))
            current["steps"][progress["step_index"]] = progress
            current["current_step_index"] = progress["step_index"]
            state["progress"] = current

        try:
            result = await optimizer.run(
                axes, axis_ranges, search_range=search_range, points=points_per_axis,
                on_progress=on_progress,
            )
            state["last_result"] = {
                "sequence": result["sequence"],
                "steps": {step["step_index"]: step for step in result["steps"]},
                "best_position": result["best_position"],
            }
        except asyncio.CancelledError:
            pass
        except Exception as e:
            state["error"] = str(e)
        finally:
            state["running"] = False

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
            actuator, detector, axes, axis_ranges, _value_key = _resolve_optimize_targets(
                workflow_id, server, request.axes,
            )
        except HTTPException:
            server.optimize_states[workflow_id]["running"] = False
            raise
        except Exception as e:
            server.optimize_states[workflow_id]["running"] = False
            raise HTTPException(status_code=502, detail=f"Failed to resolve optimize targets: {e}")

        task = asyncio.create_task(
            _run_optimize(server, workflow_id, actuator, detector, axes, axis_ranges,
                          request.ranges, request.points, request.points_per_axis)
        )
        server._optimize_tasks[workflow_id] = task
        return ApiResponse(success=True, data={"started": True})

    @app.post("/api/workflows/{workflow_id}/optimize/stop", response_model=ApiResponse)
    async def stop_optimize(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Cancels an in-flight optimize task, if any (a no-op
        otherwise) — the actuator is left wherever the scan had reached,
        not moved back or on to the best point found so far."""
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
        `run(session)` function, per WorkflowEngine._execute_script."""
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
        """Stop a running workflow."""
        if not server.workflow_engine:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        try:
            await server.workflow_engine.stop_workflow(workflow_id)
            return ApiResponse(success=True, data={"message": f"Stopped workflow {workflow_id}"})
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/workflows/{workflow_id}", response_model=ApiResponse)
    async def unload_workflow(workflow_id: str, server: LabPilotServer = Depends(get_server)):
        """Unload from the Workflows tab — removes its script_path from the
        active workflow-set only. The script file and the WorkflowStore row
        (history/versions) are untouched."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")
        try:
            graph = server.workflow_store.load(workflow_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        script_path = graph.metadata.get("script_path")
        if script_path:
            server.workflow_set_store.remove_from_active(script_path)
        return ApiResponse(success=True, data={"message": f"Unloaded {workflow_id}"})

    @app.post("/api/workflows/load", response_model=ApiResponse)
    async def load_workflow(request: WorkflowLoadRequest, server: LabPilotServer = Depends(get_server)):
        """Add a script path to the active workflow-set. If it isn't
        already backed by a WorkflowStore graph, register a minimal
        placeholder so it has an id to list/view — it's still immediately
        Execute-able (see WorkflowEngine._execute_script): a script's
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

        server.workflow_set_store.add_to_active(script_path)
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
            manager = get_dashboard_manager()
            inst = manager.instruments.get(request.instrument_id)
            if inst is None:
                raise HTTPException(status_code=404, detail=f"Instrument {request.instrument_id!r} not found")
            requirement = required[role]
            actual_kind = inst["schema"].kind
            actual_dim = inst["dimensionality"]
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

            # Find Qt desktop shell path (src/ui/desktop/)
            qt_frontend_path = Path(__file__).parent.parent / "ui" / "desktop"
            if not qt_frontend_path.exists():
                # Try alternative paths
                for search_path in [
                    Path.cwd() / "src" / "ui" / "desktop",
                    Path.cwd() / "ui" / "desktop",
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

    @app.post("/api/ai/chat", response_model=ApiResponse)
    async def chat(
        request: ChatRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Send message to AI assistant."""
        if not server.ai_session:
            raise HTTPException(status_code=503, detail="AI session not available")

        try:
            response, tool_calls_made = await server.ai_session.chat(
                request.message,
                request.conversation_id,
                request.use_tools,
                workflow_id=request.workflow_id,
            )

            # Extract structured prompt if present
            structured_prompt = extract_structured_prompt(response)
            # Always try to clean response text to remove form JSON blocks
            clean_response = clean_response_text(response)

            return ApiResponse(
                success=True,
                data=ChatResponse(
                    response=clean_response.strip(),
                    conversation_id=request.conversation_id,
                    tool_calls=tool_calls_made,  # Now uses actual count!
                    structured_prompt=structured_prompt.to_dict() if structured_prompt else None
                ).model_dump()
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/ai/conversations", response_model=ApiResponse)
    async def list_conversations(server: LabPilotServer = Depends(get_server)):
        """List all AI conversations."""
        conversation_ids = server.config_persistence.list_conversations()
        return ApiResponse(success=True, data=conversation_ids)

    @app.get("/api/ai/conversations/{conversation_id}", response_model=ApiResponse)
    async def get_conversation(conversation_id: str, server: LabPilotServer = Depends(get_server)):
        """This conversation's message history — e.g. a workflow-scoped
        chat's `f"workflow-{workflow_id}"` conversation, so reopening the
        AI chat for a workflow shows its prior messages (see
        AISession.get_conversation_messages, which hydrates from disk via
        ConfigPersistence if this conversation isn't already in memory)."""
        if not server.ai_session:
            raise HTTPException(status_code=503, detail="AI session not available")
        messages = server.ai_session.get_conversation_messages(conversation_id)
        return ApiResponse(success=True, data=[
            {
                "id": f"{conversation_id}-{i}",
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
            for i, msg in enumerate(messages)
        ])

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

    # Streaming endpoints
    @app.get("/api/ai/chat/stream")
    async def chat_stream(
        message: str,
        conversation_id: str = "default",
        workflow_id: str | None = None,
        server: LabPilotServer = Depends(get_server)
    ):
        """Stream AI chat response."""
        if not server.ai_session:
            raise HTTPException(status_code=503, detail="AI session not available")

        async def generate():
            try:
                async for chunk in server.ai_session.chat_stream(message, conversation_id, workflow_id=workflow_id):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/plain")

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
