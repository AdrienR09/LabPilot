"""
Device and Workflow Management API Routes
Handles device connections and workflow execution
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
from pathlib import Path

router = APIRouter(tags=["devices", "workflows"])

# In-memory stores (for now - would use database in production)
_connected_devices: Dict[str, Dict[str, Any]] = {}
_workflows: Dict[str, Dict[str, Any]] = {}

# Initialize with comprehensive mock devices organized by category
_connected_devices = {
    # Spectrometers
    "spec-ocean-001": {"adapter_type": "MockSpectrometer", "kind": "detector", "dimensionality": "1D", "category": "Spectrometer", "manufacturer": "Ocean Insights", "tags": ["Spectroscopy", "UV-Vis"], "status": "Ready", "connected": True},
    "spec-ocean-002": {"adapter_type": "MockSpectrometer", "kind": "detector", "dimensionality": "1D", "category": "Spectrometer", "manufacturer": "Ocean Insights", "tags": ["Spectroscopy"], "status": "Ready", "connected": True},
    "spec-princeton-001": {"adapter_type": "MockHighResSpectrometer", "kind": "detector", "dimensionality": "1D", "category": "Spectrometer", "manufacturer": "Princeton Instruments", "tags": ["High-Resolution"], "status": "Ready", "connected": False},
    "spec-agilent-001": {"adapter_type": "MockUVVISSpectrometer", "kind": "detector", "dimensionality": "1D", "category": "Spectrometer", "manufacturer": "Agilent", "tags": ["UV-VIS"], "status": "Ready", "connected": True},
    "spec-jasco-001": {"adapter_type": "MockIRSpectrometer", "kind": "detector", "dimensionality": "1D", "category": "Spectrometer", "manufacturer": "JASCO", "tags": ["IR"], "status": "Ready", "connected": False},
    "spec-raman-001": {"adapter_type": "MockRamanSpectrometer", "kind": "detector", "dimensionality": "1D", "category": "Spectrometer", "manufacturer": "Roper", "tags": ["Raman"], "status": "Ready", "connected": True},

    # Cameras
    "cam-andor-001": {"adapter_type": "MockCCDCamera", "kind": "detector", "dimensionality": "2D", "category": "Camera", "manufacturer": "Andor", "tags": ["CCD", "Imaging"], "status": "Ready", "connected": True},
    "cam-andor-002": {"adapter_type": "MockEMCCDCamera", "kind": "detector", "dimensionality": "2D", "category": "Camera", "manufacturer": "Andor", "tags": ["EM-CCD"], "status": "Ready", "connected": True},
    "cam-hamamatsu-001": {"adapter_type": "MockScientificCamera", "kind": "detector", "dimensionality": "2D", "category": "Camera", "manufacturer": "Hamamatsu", "tags": ["sCMOS"], "status": "Ready", "connected": False},
    "cam-highspeed-001": {"adapter_type": "MockHighSpeedCamera", "kind": "detector", "dimensionality": "2D", "category": "Camera", "manufacturer": "Vision Research", "tags": ["High-Speed"], "status": "Ready", "connected": True},
    "cam-thermal-001": {"adapter_type": "MockThermalCamera", "kind": "detector", "dimensionality": "2D", "category": "Camera", "manufacturer": "FLIR", "tags": ["Thermal"], "status": "Ready", "connected": False},

    # Motors/Stages
    "motor-xyz-001": {"adapter_type": "MockXYZStage", "kind": "motor", "dimensionality": "3D", "category": "Stage", "manufacturer": "Thorlabs", "tags": ["XYZ", "Positioning"], "status": "Ready", "connected": True},
    "motor-xy-001": {"adapter_type": "MockXYStage", "kind": "motor", "dimensionality": "2D", "category": "Stage", "manufacturer": "Newport", "tags": ["XY"], "status": "Ready", "connected": True},
    "motor-z-001": {"adapter_type": "MockFocusMotor", "kind": "motor", "dimensionality": "1D", "category": "Stage", "manufacturer": "Zaber", "tags": ["Focus", "Z-stage"], "status": "Ready", "connected": True},
    "motor-rotation-001": {"adapter_type": "MockRotationalStage", "kind": "motor", "dimensionality": "1D", "category": "Stage", "manufacturer": "Thorlabs", "tags": ["Rotation"], "status": "Ready", "connected": False},
    "motor-piezo-001": {"adapter_type": "MockPiezosStage", "kind": "motor", "dimensionality": "3D", "category": "Stage", "manufacturer": "PI", "tags": ["Piezo", "High-Precision"], "status": "Ready", "connected": True},

    # Power Meters
    "pm-thorlabs-001": {"adapter_type": "MockPowerMeter", "kind": "detector", "dimensionality": "0D", "category": "Power Meter", "manufacturer": "Thorlabs", "tags": ["Power"], "status": "Ready", "connected": True},
    "pm-uv-001": {"adapter_type": "MockUVPowerMeter", "kind": "detector", "dimensionality": "0D", "category": "Power Meter", "manufacturer": "Thorlabs", "tags": ["UV"], "status": "Ready", "connected": True},
    "pm-ir-001": {"adapter_type": "MockIRPowerMeter", "kind": "detector", "dimensionality": "0D", "category": "Power Meter", "manufacturer": "Thorlabs", "tags": ["IR"], "status": "Ready", "connected": False},
    "pm-array-001": {"adapter_type": "MockArrayPowerMeter", "kind": "detector", "dimensionality": "1D", "category": "Power Meter", "manufacturer": "Ophir", "tags": ["Array"], "status": "Ready", "connected": False},

    # Lock-in Amplifiers
    "lockin-srs-001": {"adapter_type": "MockLockInAmplifier", "kind": "detector", "dimensionality": "0D", "category": "Lock-in", "manufacturer": "SRS", "tags": ["Lock-in", "Measurement"], "status": "Ready", "connected": True},
    "lockin-srs-002": {"adapter_type": "MockDualChannelLockin", "kind": "detector", "dimensionality": "0D", "category": "Lock-in", "manufacturer": "SRS", "tags": ["Dual-Channel"], "status": "Ready", "connected": False},

    # Source Meters
    "smu-keithley-001": {"adapter_type": "MockSourceMeter", "kind": "detector", "dimensionality": "0D", "category": "Source Meter", "manufacturer": "Keithley", "tags": ["Source", "Meter"], "status": "Ready", "connected": True},
    "smu-hv-001": {"adapter_type": "MockHighVoltageSource", "kind": "detector", "dimensionality": "0D", "category": "Source Meter", "manufacturer": "Keithley", "tags": ["High-Voltage"], "status": "Ready", "connected": False},
    "smu-current-001": {"adapter_type": "MockCurrentSource", "kind": "detector", "dimensionality": "0D", "category": "Source Meter", "manufacturer": "Yoko", "tags": ["Current"], "status": "Ready", "connected": True},

    # Temperature Controllers
    "temp-lakeshore-001": {"adapter_type": "MockTemperatureController", "kind": "detector", "dimensionality": "0D", "category": "Temperature", "manufacturer": "Lakeshore", "tags": ["Temperature"], "status": "Ready", "connected": True},
    "temp-cryo-001": {"adapter_type": "MockCryostat", "kind": "detector", "dimensionality": "0D", "category": "Temperature", "manufacturer": "Janis", "tags": ["Cryogenic"], "status": "Ready", "connected": False},
    "temp-tec-001": {"adapter_type": "MockThermoElectricCooler", "kind": "detector", "dimensionality": "0D", "category": "Temperature", "manufacturer": "Thorlabs", "tags": ["TEC"], "status": "Ready", "connected": True},

    # Oscilloscopes
    "adc-keysight-001": {"adapter_type": "MockOscilloscope", "kind": "detector", "dimensionality": "1D", "category": "Oscilloscope", "manufacturer": "Keysight", "tags": ["Oscilloscope"], "status": "Ready", "connected": True},
    "adc-usb-001": {"adapter_type": "MockUSBOscilloscope", "kind": "detector", "dimensionality": "1D", "category": "Oscilloscope", "manufacturer": "Picoscope", "tags": ["USB"], "status": "Ready", "connected": True},
}

# Initialize with comprehensive mock workflows
_workflows = {
    "wf-spec-scan": {"name": "Spectroscopy Scan", "type": "Spectroscopy", "status": "ready", "tags": ["Spectroscopy"]},
    "wf-temp-sweep": {"name": "Temperature Sweep", "type": "Temperature Control", "status": "ready", "tags": ["Temperature"]},
    "wf-xy-mapping": {"name": "XY Mapping", "type": "Imaging", "status": "ready", "tags": ["Imaging"]},
    "wf-lockin-meas": {"name": "Lock-in Measurement", "type": "Signal Detection", "status": "ready", "tags": ["Measurement"]},
    "wf-iv-curve": {"name": "I-V Curve", "type": "Characterization", "status": "ready", "tags": ["Electronics"]},
    "wf-thermal-scan": {"name": "Thermal Imaging Scan", "type": "Thermal", "status": "ready", "tags": ["Thermal"]},
    "wf-fluorescence": {"name": "Fluorescence Lifetime", "type": "Spectroscopy", "status": "ready", "tags": ["Fluorescence"]},
    "wf-raman-map": {"name": "Raman Map", "type": "Spectroscopy", "status": "ready", "tags": ["Raman"]},
}

class DeviceConnectRequest(BaseModel):
    name: str
    adapter_type: str
    connection_params: Dict[str, Any] = {}

class WorkflowCreateRequest(BaseModel):
    name: str
    description: str = ""

# ============ DEVICE ENDPOINTS ============

@router.get("/devices")
async def get_devices():
    """Get list of connected and available devices."""
    try:
        devices = []

        # Get connected devices (from in-memory store)
        for device_name, device_info in _connected_devices.items():
            devices.append({
                "name": device_name,
                "adapter_type": device_info.get("adapter_type"),
                "connected": True,
                "status": "Connected",
                "last_reading": None,
                "error": None
            })

        # Return connected devices
        return {
            "success": True,
            "data": devices
        }
    except Exception as e:
        return {
            "success": False,
            "data": [],
            "error": str(e)
        }

# ============ DASHBOARD ENDPOINTS (for React frontend) ============

@router.get("/dashboard/instruments")
async def get_dashboard_instruments():
    """Get instruments in dashboard format."""
    try:
        instruments = []

        # Get connected devices
        for device_id, device_info in _connected_devices.items():
            instruments.append({
                "id": device_id,
                "name": device_info.get("adapter_type", device_id),
                "adapter_type": device_info.get("adapter_type"),
                "kind": device_info.get("kind", "generic"),
                "dimensionality": device_info.get("dimensionality", "0D"),
                "tags": device_info.get("tags", []),
                "connected": device_info.get("connected", True),
                "status": device_info.get("status", "Ready"),
                "data": None
            })

        return {
            "success": True,
            "data": instruments
        }
    except Exception as e:
        return {
            "success": False,
            "data": [],
            "error": str(e)
        }

@router.get("/dashboard/workflows")
async def get_dashboard_workflows():
    """Get workflows in dashboard format."""
    try:
        workflows = []

        # Convert workflows to dashboard format
        for wf_id, wf_info in _workflows.items():
            workflows.append({
                "id": wf_id,
                "name": wf_info.get("name", "Unknown"),
                "workflow_type": wf_info.get("type", "generic"),
                "connected_instruments": [],
                "running": wf_info.get("status") == "running",
                "progress": 0,
                "has_data": False
            })

        return {
            "success": True,
            "data": workflows
        }
    except Exception as e:
        return {
            "success": False,
            "data": [],
            "error": str(e)
        }

@router.get("/dashboard/state")
async def get_dashboard_state():
    """Get complete dashboard state."""
    try:
        instruments = []
        workflows = []
        connections = []

        # Get instruments
        for device_name, device_info in _connected_devices.items():
            instruments.append({
                "id": device_name,
                "name": device_name,
                "adapter_type": device_info.get("adapter_type"),
                "kind": device_info.get("kind", "generic"),
                "dimensionality": device_info.get("dimensionality", "0D"),
                "tags": device_info.get("tags", []),
                "connected": True,
                "data": None
            })

        # Get workflows
        for wf_id, wf_info in _workflows.items():
            workflows.append({
                "id": wf_id,
                "name": wf_info.get("name", "Unknown"),
                "workflow_type": wf_info.get("type", "generic"),
                "connected_instruments": [],
                "running": wf_info.get("status") == "running",
                "progress": 0,
                "has_data": False
            })

        return {
            "success": True,
            "data": {
                "instruments": instruments,
                "workflows": workflows,
                "connections": connections
            }
        }
    except Exception as e:
        return {
            "success": False,
            "data": {"instruments": [], "workflows": [], "connections": []},
            "error": str(e)
        }

@router.post("/dashboard/workflows/{workflow_id}/execute")
async def execute_dashboard_workflow(workflow_id: str):
    """Execute a workflow from dashboard."""
    try:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Update workflow status
        _workflows[workflow_id]["status"] = "running"

        return {
            "success": True,
            "data": {
                "message": "Workflow execution started",
                "data": workflow_id
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/dashboard/workflows/{workflow_id}/stop")
async def stop_dashboard_workflow(workflow_id: str):
    """Stop a running workflow from dashboard."""
    try:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Update workflow status
        _workflows[workflow_id]["status"] = "stopped"

        return {
            "success": True,
            "data": {
                "message": "Workflow stopped"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/devices/connect")
async def connect_device(request: DeviceConnectRequest):
    """Connect to a device."""
    try:
        # Store device connection info
        _connected_devices[request.name] = {
            "adapter_type": request.adapter_type,
            "connection_params": request.connection_params,
            "status": "Connected"
        }

        return {
            "success": True,
            "data": {
                "name": request.name,
                "adapter_type": request.adapter_type,
                "status": "Connected"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/devices/{device_name}")
async def disconnect_device(device_name: str):
    """Disconnect from a device."""
    try:
        if device_name in _connected_devices:
            del _connected_devices[device_name]
            return {
                "success": True,
                "data": {"message": f"Device {device_name} disconnected"}
            }
        else:
            raise HTTPException(status_code=404, detail=f"Device {device_name} not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============ WORKFLOW ENDPOINTS ============

@router.get("/workflows")
async def get_workflows():
    """Get list of available workflows."""
    try:
        workflows = []

        for workflow_id, workflow_info in _workflows.items():
            workflows.append({
                "id": workflow_id,
                "name": workflow_info.get("name", "Unknown"),
                "version": workflow_info.get("version", 1),
                "status": workflow_info.get("status", "ready"),
                "created_at": workflow_info.get("created_at", 0),
                "updated_at": workflow_info.get("updated_at", 0),
                "description": workflow_info.get("description", "")
            })

        return {
            "success": True,
            "data": workflows
        }
    except Exception as e:
        return {
            "success": False,
            "data": [],
            "error": str(e)
        }

@router.post("/workflows")
async def create_workflow(request: WorkflowCreateRequest):
    """Create a new workflow."""
    try:
        import time
        workflow_id = f"wf_{int(time.time())}"

        _workflows[workflow_id] = {
            "name": request.name,
            "description": request.description,
            "version": 1,
            "status": "ready",
            "created_at": int(time.time()),
            "updated_at": int(time.time())
        }

        return {
            "success": True,
            "data": {
                "id": workflow_id,
                "name": request.name,
                "version": 1,
                "created_at": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str):
    """Execute a workflow."""
    try:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Update workflow status
        _workflows[workflow_id]["status"] = "running"

        return {
            "success": True,
            "data": {
                "workflow_id": workflow_id,
                "status": "running",
                "message": "Workflow execution started"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow details."""
    try:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        return {
            "success": True,
            "data": _workflows[workflow_id]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a workflow."""
    try:
        if workflow_id not in _workflows:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        del _workflows[workflow_id]

        return {
            "success": True,
            "data": {"message": f"Workflow {workflow_id} deleted"}
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))