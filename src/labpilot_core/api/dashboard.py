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

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from labpilot_core.adapters import adapter_registry
from labpilot_core.workflows.confocal_scan import ConfocalScan, ConfocalScanConfig
from labpilot_core.workflows.transient_absorption import (
    TransientAbsorption,
    TransientAbsorptionConfig,
)


class InstrumentStatus(BaseModel):
    """Status of a connected instrument."""

    id: str
    name: str
    adapter_type: str
    kind: str  # detector or actuator
    dimensionality: str  # 0D, 1D, 2D, 3D
    tags: list[str]
    connected: bool
    data: dict[str, Any] | None = None


class WorkflowStatus(BaseModel):
    """Status of a workflow."""

    id: str
    name: str
    workflow_type: str
    connected_instruments: list[str]
    running: bool
    progress: float = 0.0  # 0-100
    has_data: bool = False


class DashboardState(BaseModel):
    """Overall dashboard state."""

    instruments: list[InstrumentStatus]
    workflows: list[WorkflowStatus]
    connections: list[dict[str, str]]  # Instrument-workflow connections


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow."""

    workflow_id: str
    config: dict[str, Any] | None = None


class DashboardManager:
    """Manages dashboard state, instruments, and workflows."""

    def __init__(self):
        self.instruments: dict[str, Any] = {}  # id -> adapter instance
        self.workflows: dict[str, Any] = {}  # id -> workflow instance
        self.websockets: list[WebSocket] = []
        self.instrument_data_streams: dict[str, asyncio.Task] = {}

    async def initialize_fake_instruments(self):
        """Initialize (but don't auto-connect) fake instruments on startup."""

        # Define instrument configurations organized by dimensionality
        instrument_configs = [
            # 0D Detectors
            {"id": "apd1", "name": "APD Detector", "adapter": "fake_apd", "dim": "0D"},
            # 1D Detectors
            {
                "id": "spec1",
                "name": "Spectrometer",
                "adapter": "fake_spectrometer",
                "dim": "1D",
            },
            # 2D Detectors
            {
                "id": "cam1",
                "name": "CCD Camera",
                "adapter": "fake_spectrum_camera",
                "dim": "2D",
            },
            # 0D Actuators
            {
                "id": "switch1",
                "name": "Laser Shutter",
                "adapter": "fake_switch",
                "dim": "0D",
            },
            # 1D Actuators
            {
                "id": "stage1",
                "name": "Delay Stage",
                "adapter": "fake_stage",
                "dim": "1D",
            },
            {
                "id": "scanner1d1",
                "name": "Line Scanner",
                "adapter": "fake_scanner_1d",
                "dim": "1D",
            },
            # 2D Actuators
            {
                "id": "scanner2d1",
                "name": "XY Scanner",
                "adapter": "fake_scanner_2d",
                "dim": "2D",
            },
            # 3D Actuators
            {
                "id": "scanner3d1",
                "name": "Confocal Scanner",
                "adapter": "fake_scanner_3d",
                "dim": "3D",
            },
        ]

        # Instantiate instruments (but don't connect them)
        for config in instrument_configs:
            try:
                # Get adapter class
                AdapterClass = adapter_registry.get(config["adapter"])

                # Instantiate (disconnected state)
                adapter = AdapterClass(name=config["name"])

                # DON'T auto-connect - let user connect manually
                # (adapter._connected is False by default)

                # Store
                self.instruments[config["id"]] = {
                    "adapter": adapter,
                    "name": config["name"],
                    "adapter_type": config["adapter"],
                    "dimensionality": config["dim"],
                    "schema": adapter.schema,
                }

                print(f"✅ Registered {config['name']} ({config['id']}) - disconnected")

            except Exception as e:
                print(f"❌ Failed to register {config['name']}: {e}")

    async def initialize_fake_workflows(self):
        """Pre-create fake workflows connected to instruments."""

        # Confocal Scan: APD + 3D Scanner
        confocal = ConfocalScan(
            apd_adapter="fake_apd", scanner_adapter="fake_scanner_3d"
        )
        await confocal.initialize()

        self.workflows["confocal1"] = {
            "instance": confocal,
            "name": "Confocal Microscopy",
            "type": "confocal_scan",
            "instruments": ["apd1", "scanner3d1"],
        }

        # Transient Absorption: Spectrometer + Stage
        transient = TransientAbsorption(
            spectrometer_adapter="fake_spectrometer", stage_adapter="fake_stage"
        )
        await transient.initialize()

        self.workflows["transient1"] = {
            "instance": transient,
            "name": "Transient Absorption",
            "type": "transient_absorption",
            "instruments": ["spec1", "stage1"],
        }

        print(f"✅ Initialized {len(self.workflows)} workflows")

    def get_instrument_status(self, instrument_id: str) -> InstrumentStatus:
        """Get current status of an instrument."""
        if instrument_id not in self.instruments:
            raise ValueError(f"Instrument {instrument_id} not found")

        inst = self.instruments[instrument_id]
        schema = inst["schema"]

        return InstrumentStatus(
            id=instrument_id,
            name=inst["name"],
            adapter_type=inst["adapter_type"],
            kind=schema.kind,
            dimensionality=inst["dimensionality"],
            tags=schema.tags,
            connected=True,
            data=None,  # Will be populated by real-time stream
        )

    def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        """Get current status of a workflow."""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")

        wf = self.workflows[workflow_id]
        instance = wf["instance"]
        status = instance.get_status()

        return WorkflowStatus(
            id=workflow_id,
            name=wf["name"],
            workflow_type=wf["type"],
            connected_instruments=wf["instruments"],
            running=status["running"],
            has_data=status["has_data"],
        )

    def get_dashboard_state(self) -> DashboardState:
        """Get complete dashboard state."""
        instruments = [
            self.get_instrument_status(inst_id) for inst_id in self.instruments.keys()
        ]

        workflows = [
            self.get_workflow_status(wf_id) for wf_id in self.workflows.keys()
        ]

        # Build connections list
        connections = []
        for wf_id, wf in self.workflows.items():
            for inst_id in wf["instruments"]:
                connections.append(
                    {"instrument_id": inst_id, "workflow_id": wf_id, "type": "uses"}
                )

        return DashboardState(
            instruments=instruments, workflows=workflows, connections=connections
        )

    async def execute_workflow(
        self, workflow_id: str, config: dict[str, Any] | None = None
    ):
        """Execute a workflow with optional configuration."""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")

        wf = self.workflows[workflow_id]
        instance = wf["instance"]

        # Progress callback for real-time updates
        async def progress_callback(progress_data: dict[str, Any]):
            # Broadcast progress to all connected WebSocket clients
            message = {
                "type": "workflow_progress",
                "workflow_id": workflow_id,
                "data": progress_data,
            }
            await self.broadcast_to_websockets(message)

        # Parse config based on workflow type
        if wf["type"] == "confocal_scan":
            workflow_config = ConfocalScanConfig(**config) if config else None
        elif wf["type"] == "transient_absorption":
            workflow_config = (
                TransientAbsorptionConfig(**config) if config else None
            )
        else:
            workflow_config = None

        # Execute workflow
        data = await instance.run(workflow_config, progress_callback)

        # Broadcast completion
        message = {
            "type": "workflow_complete",
            "workflow_id": workflow_id,
            "data": data.__dict__ if hasattr(data, "__dict__") else str(data),
        }
        await self.broadcast_to_websockets(message)

        return data

    async def stop_workflow(self, workflow_id: str):
        """Stop a running workflow."""
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")

        wf = self.workflows[workflow_id]
        instance = wf["instance"]
        await instance.stop()

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
                    "data": data,
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


@router.get("/workflows")
async def list_workflows():
    """List all workflows."""
    manager = get_dashboard_manager()
    workflows = [
        manager.get_workflow_status(wf_id).model_dump()
        for wf_id in manager.workflows.keys()
    ]
    return {"success": True, "data": workflows}


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, request: WorkflowExecuteRequest):
    """Execute a workflow."""
    manager = get_dashboard_manager()
    try:
        data = await manager.execute_workflow(workflow_id, request.config)
        return {"success": True, "data": {"message": "Workflow completed", "data": str(data)}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workflows/{workflow_id}/stop")
async def stop_workflow(workflow_id: str):
    """Stop a running workflow."""
    manager = get_dashboard_manager()
    try:
        await manager.stop_workflow(workflow_id)
        return {"success": True, "data": {"message": "Workflow stopped"}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    """Initialize dashboard with fake instruments and workflows."""
    manager = get_dashboard_manager()
    await manager.initialize_fake_instruments()
    await manager.initialize_fake_workflows()


__all__ = ["get_dashboard_manager", "initialize_dashboard", "router"]
