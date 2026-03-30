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
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from labpilot_core.ai import AISession
from labpilot_core.ai.structured_prompt import (
    clean_response_text,
    extract_structured_prompt,
)
from labpilot_core.api.dashboard import initialize_dashboard
from labpilot_core.api.dashboard import router as dashboard_router
from labpilot_core.config import (
    ConfigPersistence,
)
from labpilot_core.core.session import Session
from labpilot_core.workflow import WorkflowEngine, WorkflowGraph, WorkflowStore

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


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow."""
    workflow_id: str
    version: int | None = None


class QtLaunchRequest(BaseModel):
    """Request to launch Qt instrument window."""
    instrument_id: str
    instrument_type: str
    dimensionality: str


class QtSpawnRequest(BaseModel):
    """Request to spawn Qt window from DSL."""
    window_id: str = Field(default_factory=lambda: f"qt_{uuid.uuid4().hex[:8]}")
    spec: dict[str, Any]


class ChatRequest(BaseModel):
    """AI chat request."""
    message: str
    conversation_id: str = "default"
    use_tools: bool = True


class ChatResponse(BaseModel):
    """AI chat response."""
    response: str
    conversation_id: str
    tool_calls: int = 0
    structured_prompt: dict[str, Any] | None = None


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
        self.websocket_manager = WebSocketManager()
        self._event_task: asyncio.Task | None = None

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

        # Initialize AI session if configured
        try:
            self.ai_session = AISession(self.session)
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

        # Initialize dashboard with fake instruments and workflows
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
                event_data = {
                    "type": "event",
                    "event": event.to_dict()
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

    @app.get("/api/workflows", response_model=ApiResponse)
    async def list_workflows(server: LabPilotServer = Depends(get_server)):
        """List all workflows."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")

        try:
            workflows = server.workflow_store.list_all()
            workflow_data = [
                {
                    "id": wf.id,
                    "name": wf.name,
                    "version": wf.current_version,
                    "created_at": wf.created_at,
                    "updated_at": wf.updated_at,
                }
                for wf in workflows
            ]
            return ApiResponse(success=True, data=workflow_data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/workflows", response_model=ApiResponse)
    async def create_workflow(
        request: WorkflowCreateRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Create a new workflow."""
        if not server.workflow_store:
            raise HTTPException(status_code=503, detail="Workflow store not available")

        try:
            # Create empty workflow graph
            workflow = WorkflowGraph(name=request.name)
            if request.description:
                workflow.metadata["description"] = request.description
            version = server.workflow_store.save(workflow, "Initial creation")

            return ApiResponse(
                success=True,
                data={
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "version": version
                }
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/workflows/execute", response_model=ApiResponse)
    async def execute_workflow(
        request: WorkflowExecuteRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Execute a workflow."""
        if not server.workflow_engine:
            raise HTTPException(status_code=503, detail="Workflow engine not available")

        try:
            execution_id = await server.workflow_engine.start_workflow(
                request.workflow_id,
                request.version
            )
            return ApiResponse(
                success=True,
                data={"execution_id": execution_id}
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/instruments/{instrument_id}/launch-qt", response_model=ApiResponse)
    async def launch_qt_window(
        instrument_id: str,
        request: QtLaunchRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Launch Qt window for specific instrument."""
        try:
            import subprocess
            import sys
            from pathlib import Path

            # Find Qt frontend path
            qt_frontend_path = Path(__file__).parent.parent.parent / "qt_frontend"
            if not qt_frontend_path.exists():
                # Try alternative paths
                for search_path in [
                    Path.cwd() / "qt_frontend",
                    Path.cwd() / "labpilot" / "qt_frontend",
                    Path("/Users/adrien/Documents/Qudi/labpilot/qt_frontend")
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
            import time
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
                request.use_tools
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
                "preferences": config.preferences.model_dump(),
                "devices": [device.model_dump() for device in config.devices],
                "workflows": [workflow.model_dump() for workflow in config.workflows],
                "open_panels": [panel.model_dump() for panel in config.open_panels],
                "ai_config": config.ai_config.model_dump() if config.ai_config else None,
                "metadata": config.metadata
            }

            return ApiResponse(success=True, data=session_data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/qt/spawn", response_model=ApiResponse)
    async def spawn_qt_window(
        request: QtSpawnRequest,
        server: LabPilotServer = Depends(get_server)
    ):
        """Spawn Qt window from DSL specification."""
        try:
            # Import Qt bridge here to avoid import errors if Qt not available
            from labpilot_core.qt.bridge import get_bridge

            bridge = get_bridge()
            if bridge is None:
                raise HTTPException(status_code=503, detail="Qt bridge not available")

            # Validate spec structure
            if not isinstance(request.spec, dict):
                raise HTTPException(status_code=400, detail="Spec must be a dictionary")

            required_fields = ["type", "title"]
            for field in required_fields:
                if field not in request.spec:
                    raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

            # Spawn the Qt window
            bridge.open_window(request.window_id, request.spec)

            return ApiResponse(
                success=True,
                data={
                    "window_id": request.window_id,
                    "message": f"Qt window '{request.spec['title']}' spawned successfully"
                }
            )

        except ImportError:
            raise HTTPException(status_code=503, detail="Qt components not available - install PyQt6 and pyqtgraph")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to spawn Qt window: {e!s}")

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
        server: LabPilotServer = Depends(get_server)
    ):
        """Stream AI chat response."""
        if not server.ai_session:
            raise HTTPException(status_code=503, detail="AI session not available")

        async def generate():
            try:
                async for chunk in server.ai_session.chat_stream(message, conversation_id):
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
