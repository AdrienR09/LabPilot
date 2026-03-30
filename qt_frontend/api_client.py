#!/usr/bin/env python3
"""
API Client - Backend Communication Layer
Provides Qt-compatible API integration for the Material Manager
"""

import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QThread
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtCore import QUrl
import requests

# Import data structures
from main import DashboardInstrument
from workflows_page import Workflow

@dataclass
class ApiResponse:
    """Standard API response structure"""
    success: bool
    data: Any = None
    error: str = ""
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class LabPilotApiClient(QObject):
    """Qt-compatible API client for LabPilot backend"""

    # Signals for async communication
    session_status_updated = pyqtSignal(dict)
    devices_updated = pyqtSignal(list)
    workflows_updated = pyqtSignal(list)
    ai_response_received = pyqtSignal(str)
    connection_status_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.connected = False

        # Setup periodic status checking
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_connection_status)
        self.status_timer.start(5000)  # Check every 5 seconds

    def set_base_url(self, url: str):
        """Update base URL"""
        self.base_url = url.rstrip('/')

    def check_connection_status(self):
        """Check backend connection status"""
        try:
            response = self.session.get(f"{self.base_url}/api/session/status", timeout=2)
            if response.status_code == 200:
                if not self.connected:
                    self.connected = True
                    self.connection_status_changed.emit(True)

                # Emit session data
                data = response.json()
                self.session_status_updated.emit(data)
            else:
                self._handle_connection_loss()
        except Exception as e:
            self._handle_connection_loss()

    def _handle_connection_loss(self):
        """Handle connection loss"""
        if self.connected:
            self.connected = False
            self.connection_status_changed.emit(False)
            self.error_occurred.emit("Lost connection to backend server")

    # Session API
    def get_session_status(self) -> ApiResponse:
        """Get current session status"""
        try:
            response = self.session.get(f"{self.base_url}/api/session/status")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    # Device API
    def get_devices(self) -> ApiResponse:
        """Get all devices"""
        try:
            response = self.session.get(f"{self.base_url}/api/devices")
            if response.status_code == 200:
                devices_data = response.json()
                devices = [DashboardInstrument(**device) for device in devices_data]
                return ApiResponse(success=True, data=devices)
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def connect_device(self, device_id: str) -> ApiResponse:
        """Connect a device"""
        try:
            response = self.session.post(f"{self.base_url}/api/devices/{device_id}/connect")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def disconnect_device(self, device_id: str) -> ApiResponse:
        """Disconnect a device"""
        try:
            response = self.session.post(f"{self.base_url}/api/devices/{device_id}/disconnect")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def add_device(self, device_data: dict) -> ApiResponse:
        """Add a new device"""
        try:
            response = self.session.post(f"{self.base_url}/api/devices", json=device_data)
            if response.status_code == 201:
                device = DashboardInstrument(**response.json())
                return ApiResponse(success=True, data=device)
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def remove_device(self, device_id: str) -> ApiResponse:
        """Remove a device"""
        try:
            response = self.session.delete(f"{self.base_url}/api/devices/{device_id}")
            if response.status_code == 200:
                return ApiResponse(success=True)
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    # Workflow API
    def get_workflows(self) -> ApiResponse:
        """Get all workflows"""
        try:
            response = self.session.get(f"{self.base_url}/api/workflows")
            if response.status_code == 200:
                workflows_data = response.json()
                workflows = [Workflow(**workflow) for workflow in workflows_data]
                return ApiResponse(success=True, data=workflows)
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def create_workflow(self, workflow_data: dict) -> ApiResponse:
        """Create a new workflow"""
        try:
            response = self.session.post(f"{self.base_url}/api/workflows", json=workflow_data)
            if response.status_code == 201:
                workflow = Workflow(**response.json())
                return ApiResponse(success=True, data=workflow)
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def start_workflow(self, workflow_id: str) -> ApiResponse:
        """Start workflow execution"""
        try:
            response = self.session.post(f"{self.base_url}/api/workflows/{workflow_id}/start")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def stop_workflow(self, workflow_id: str) -> ApiResponse:
        """Stop workflow execution"""
        try:
            response = self.session.post(f"{self.base_url}/api/workflows/{workflow_id}/stop")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    # AI API
    def send_ai_message(self, message: str, conversation_id: Optional[str] = None) -> ApiResponse:
        """Send message to AI assistant"""
        try:
            payload = {"message": message}
            if conversation_id:
                payload["conversation_id"] = conversation_id

            response = self.session.post(f"{self.base_url}/api/ai/chat", json=payload)
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def get_ai_status(self) -> ApiResponse:
        """Get AI assistant status"""
        try:
            response = self.session.get(f"{self.base_url}/api/ai/status")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    # Data API
    def get_data_files(self) -> ApiResponse:
        """Get list of data files"""
        try:
            response = self.session.get(f"{self.base_url}/api/data/files")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def get_data_file(self, file_id: str) -> ApiResponse:
        """Get specific data file"""
        try:
            response = self.session.get(f"{self.base_url}/api/data/files/{file_id}")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    def export_data(self, data_id: str, format_type: str = "json") -> ApiResponse:
        """Export data in specified format"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/data/{data_id}/export",
                params={"format": format_type}
            )
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.content)
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

    # Qt Interface API
    def launch_qt_interface(self, device_id: str) -> ApiResponse:
        """Launch Qt interface for device"""
        try:
            response = self.session.post(f"{self.base_url}/api/qt-interface/launch/{device_id}")
            if response.status_code == 200:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(success=False, error=f"HTTP {response.status_code}")
        except Exception as e:
            return ApiResponse(success=False, error=str(e))

class AsyncApiWorker(QThread):
    """Worker thread for async API operations"""

    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_client: LabPilotApiClient, operation: str, **kwargs):
        super().__init__()
        self.api_client = api_client
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        """Execute API operation in background thread"""
        try:
            if hasattr(self.api_client, self.operation):
                method = getattr(self.api_client, self.operation)
                result = method(**self.kwargs)
                self.result_ready.emit(result)
            else:
                self.error_occurred.emit(f"Unknown operation: {self.operation}")
        except Exception as e:
            self.error_occurred.emit(str(e))

def create_api_client(base_url: str = "http://localhost:8000") -> LabPilotApiClient:
    """Factory function to create API client"""
    return LabPilotApiClient(base_url)