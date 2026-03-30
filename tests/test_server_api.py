"""
Comprehensive tests for LabPilot server API endpoints.

Tests all REST API endpoints, WebSocket functionality, error handling,
and integration with core components.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

# Import FastAPI testing components
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Import server components
from labpilot_core.server import create_app, LabPilotServer
from labpilot_core.session_config import SessionConfig, DeviceConfig
from labpilot_core.core.session import Session


@pytest.fixture
def mock_server():
    """Create mock LabPilotServer for testing."""
    server = Mock(spec=LabPilotServer)
    server.session = Mock(spec=Session)
    server.session.devices = {}
    server.ai_session = Mock()
    server.workflow_store = Mock()
    server.workflow_engine = Mock()
    server.config_persistence = Mock()
    server.websocket_manager = Mock()
    return server


@pytest.fixture
def test_app(mock_server):
    """Create test FastAPI app with mocked components."""
    app = create_app()
    app.state.server = mock_server
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestHealthEndpoints:
    """Test health check and status endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["status"] == "healthy"

    def test_session_status(self, client, mock_server):
        """Test session status endpoint."""
        # Setup mock data
        mock_server.session.devices = {"device1": Mock(), "device2": Mock()}
        mock_server.ai_session = Mock()
        mock_server.workflow_engine.get_running_workflows.return_value = ["wf1", "wf2"]

        response = client.get("/api/session/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["devices_connected"] == 2
        assert data["data"]["ai_available"] == True
        assert data["data"]["workflow_engine_running"] == 2

    def test_session_status_no_ai(self, client, mock_server):
        """Test session status when AI not available."""
        mock_server.ai_session = None

        response = client.get("/api/session/status")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["ai_available"] == False


class TestDeviceEndpoints:
    """Test device management endpoints."""

    def test_list_devices_empty(self, client, mock_server):
        """Test listing devices when none connected."""
        mock_server.session.devices = {}

        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert len(data["data"]) == 0

    def test_list_devices_with_devices(self, client, mock_server):
        """Test listing devices with connected devices."""
        # Mock devices
        device1 = Mock()
        device1.read = AsyncMock(return_value={"temperature": 25.0})
        device1._adapter_type = "TestAdapter"

        device2 = Mock()
        device2.read = AsyncMock(side_effect=Exception("Device error"))
        device2._adapter_type = "FailingAdapter"

        mock_server.session.devices = {
            "working_device": device1,
            "failing_device": device2
        }

        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert len(data["data"]) == 2

        # Check working device
        working = next(d for d in data["data"] if d["name"] == "working_device")
        assert working["connected"] == True
        assert working["adapter_type"] == "TestAdapter"
        assert working["last_reading"]["temperature"] == 25.0

        # Check failing device
        failing = next(d for d in data["data"] if d["name"] == "failing_device")
        assert failing["connected"] == False
        assert "Device error" in failing["error"]

    def test_connect_device(self, client, mock_server):
        """Test connecting a new device."""
        request_data = {
            "name": "new_device",
            "adapter_type": "TestAdapter",
            "connection_params": {"port": "COM1"}
        }

        response = client.post("/api/devices/connect", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "connected successfully" in data["data"]["message"]

    def test_disconnect_device_success(self, client, mock_server):
        """Test disconnecting existing device."""
        mock_server.session.devices = {"test_device": Mock()}

        response = client.delete("/api/devices/test_device")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "disconnected" in data["data"]["message"]

    def test_disconnect_device_not_found(self, client, mock_server):
        """Test disconnecting nonexistent device."""
        mock_server.session.devices = {}

        response = client.delete("/api/devices/nonexistent")

        assert response.status_code == 404


class TestWorkflowEndpoints:
    """Test workflow management endpoints."""

    def test_list_workflows(self, client, mock_server):
        """Test listing workflows."""
        # Mock workflow data
        mock_workflows = [
            Mock(
                id="wf1",
                name="Test Workflow 1",
                current_version=1,
                created_at="2024-01-01T10:00:00Z",
                updated_at="2024-01-01T11:00:00Z"
            ),
            Mock(
                id="wf2",
                name="Test Workflow 2",
                current_version=2,
                created_at="2024-01-01T12:00:00Z",
                updated_at="2024-01-01T13:00:00Z"
            )
        ]
        mock_server.workflow_store.list_all.return_value = mock_workflows

        response = client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert len(data["data"]) == 2
        assert data["data"][0]["name"] == "Test Workflow 1"
        assert data["data"][1]["version"] == 2

    def test_list_workflows_no_store(self, client, mock_server):
        """Test listing workflows when store unavailable."""
        mock_server.workflow_store = None

        response = client.get("/api/workflows")

        assert response.status_code == 503

    def test_create_workflow(self, client, mock_server):
        """Test creating a new workflow."""
        mock_server.workflow_store.save.return_value = 1

        request_data = {
            "name": "New Workflow",
            "description": "Test workflow"
        }

        with patch('labpilot_core.server.WorkflowGraph') as mock_wf:
            mock_workflow = Mock()
            mock_workflow.id = "new_wf_id"
            mock_workflow.name = "New Workflow"
            mock_wf.return_value = mock_workflow

            response = client.post("/api/workflows", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["workflow_id"] == "new_wf_id"
        assert data["data"]["version"] == 1

    def test_execute_workflow(self, client, mock_server):
        """Test executing a workflow."""
        mock_server.workflow_engine.start_workflow = AsyncMock(return_value="exec_123")

        request_data = {
            "workflow_id": "wf_123",
            "version": 2
        }

        response = client.post("/api/workflows/execute", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["execution_id"] == "exec_123"


class TestQtEndpoints:
    """Test Qt window management endpoints."""

    def test_launch_qt_window(self, client, mock_server):
        """Test launching Qt instrument window."""
        request_data = {
            "instrument_id": "camera1",
            "instrument_type": "camera",
            "dimensionality": "2D"
        }

        # Mock subprocess to simulate successful launch
        with patch('labpilot_core.server.subprocess.Popen') as mock_popen, \
             patch('labpilot_core.server.Path') as mock_path:

            # Setup path mocking
            mock_path.return_value.exists.return_value = True
            launch_script = mock_path.return_value / "launch_instrument.py"
            launch_script.exists.return_value = True

            # Setup process mocking
            mock_process = Mock()
            mock_process.poll.return_value = None  # Still running
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            response = client.post("/api/instruments/camera1/launch-qt", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "launched" in data["data"]["message"]
        assert data["data"]["pid"] == 12345

    def test_spawn_qt_window(self, client, mock_server):
        """Test spawning Qt window from DSL spec."""
        request_data = {
            "window_id": "custom_window",
            "spec": {
                "type": "window",
                "title": "Test Window",
                "layout": "vertical",
                "widgets": [
                    {
                        "type": "spectrum_plot",
                        "source": "device.data"
                    }
                ]
            }
        }

        with patch('labpilot_core.server.get_bridge') as mock_get_bridge:
            mock_bridge = Mock()
            mock_get_bridge.return_value = mock_bridge

            response = client.post("/api/qt/spawn", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["window_id"] == "custom_window"
        assert "spawned successfully" in data["data"]["message"]

        # Verify bridge was called with correct parameters
        mock_bridge.open_window.assert_called_once_with("custom_window", request_data["spec"])

    def test_spawn_qt_window_no_bridge(self, client, mock_server):
        """Test spawning Qt window when bridge unavailable."""
        request_data = {
            "spec": {
                "type": "window",
                "title": "Test"
            }
        }

        with patch('labpilot_core.server.get_bridge', return_value=None):
            response = client.post("/api/qt/spawn", json=request_data)

        assert response.status_code == 503
        assert "Qt bridge not available" in response.json()["detail"]

    def test_spawn_qt_window_invalid_spec(self, client, mock_server):
        """Test spawning Qt window with invalid spec."""
        request_data = {
            "spec": {
                "invalid": "spec"  # Missing required 'type' and 'title'
            }
        }

        response = client.post("/api/qt/spawn", json=request_data)

        assert response.status_code == 400
        assert "Missing required field" in response.json()["detail"]


class TestAIEndpoints:
    """Test AI chat and conversation endpoints."""

    def test_ai_chat(self, client, mock_server):
        """Test AI chat endpoint."""
        mock_server.ai_session.chat = AsyncMock(return_value=("Hello! I can help you.", 2))

        request_data = {
            "message": "Hello AI",
            "conversation_id": "test_conv",
            "use_tools": True
        }

        with patch('labpilot_core.server.extract_structured_prompt', return_value=None), \
             patch('labpilot_core.server.clean_response_text', return_value="Hello! I can help you."):

            response = client.post("/api/ai/chat", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["response"] == "Hello! I can help you."
        assert data["data"]["conversation_id"] == "test_conv"
        assert data["data"]["tool_calls"] == 2

    def test_ai_chat_no_session(self, client, mock_server):
        """Test AI chat when session unavailable."""
        mock_server.ai_session = None

        request_data = {"message": "Hello"}

        response = client.post("/api/ai/chat", json=request_data)

        assert response.status_code == 503

    def test_list_conversations(self, client, mock_server):
        """Test listing AI conversations."""
        mock_server.config_persistence.list_conversations.return_value = ["conv1", "conv2"]

        response = client.get("/api/ai/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"] == ["conv1", "conv2"]

    def test_chat_stream(self, client, mock_server):
        """Test streaming AI chat response."""
        async def mock_stream():
            yield "Hello"
            yield " world"
            yield "!"

        mock_server.ai_session.chat_stream = AsyncMock(return_value=mock_stream())

        response = client.get("/api/ai/chat/stream?message=test&conversation_id=test")

        assert response.status_code == 200
        # Note: Full streaming test would require async test client


class TestConfigEndpoints:
    """Test configuration management endpoints."""

    def test_get_config_summary(self, client, mock_server):
        """Test getting configuration summary."""
        mock_server.config_persistence.get_config_summary.return_value = {
            "session_id": "test_session",
            "devices_count": 3,
            "conversations_count": 5
        }

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["devices_count"] == 3

    def test_get_session_config(self, client, mock_server):
        """Test getting current session configuration."""
        # Mock session config
        mock_config = SessionConfig(
            session_id="test_session",
            metadata={"experiment": "spectroscopy"}
        )
        mock_server.config_persistence.from_session.return_value = mock_config

        response = client.get("/api/session/config")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["session_id"] == "test_session"
        assert data["data"]["metadata"]["experiment"] == "spectroscopy"
        assert "preferences" in data["data"]
        assert "devices" in data["data"]

    def test_save_config(self, client, mock_server):
        """Test saving current configuration."""
        mock_config = SessionConfig(session_id="save_test")
        mock_server.config_persistence.from_session.return_value = mock_config
        mock_server.config_persistence.save_session_config.return_value = "/path/to/config.json"

        response = client.post("/api/config/save")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "saved" in data["data"]["message"].lower()


class TestWebSocket:
    """Test WebSocket functionality."""

    def test_websocket_connection(self, test_app, mock_server):
        """Test WebSocket connection and communication."""
        with TestClient(test_app) as client:
            with client.websocket_connect("/ws") as websocket:
                # Send ping
                websocket.send_text(json.dumps({"type": "ping"}))

                # Should receive pong
                response = websocket.receive_text()
                data = json.loads(response)
                assert data["type"] == "pong"

    def test_websocket_broadcast(self, mock_server):
        """Test WebSocket broadcasting functionality."""
        from labpilot_core.server import WebSocketManager

        manager = WebSocketManager()

        # Mock WebSocket connections
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        # Simulate connections
        manager.active_connections = [mock_ws1, mock_ws2]

        # Test broadcast
        asyncio.run(manager.broadcast("test message"))

        # Both should have received message
        mock_ws1.send_text.assert_called_with("test message")
        mock_ws2.send_text.assert_called_with("test message")


class TestErrorHandling:
    """Test error handling across all endpoints."""

    def test_404_endpoints(self, client):
        """Test 404 responses for nonexistent endpoints."""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

        response = client.post("/api/invalid/endpoint")
        assert response.status_code == 404

    def test_invalid_json_requests(self, client, mock_server):
        """Test handling of invalid JSON in requests."""
        # Invalid JSON content
        response = client.post(
            "/api/devices/connect",
            content="{invalid json}",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_missing_required_fields(self, client, mock_server):
        """Test handling of missing required fields."""
        # Missing required fields in device connection
        response = client.post("/api/devices/connect", json={
            "name": "test"
            # Missing adapter_type and connection_params
        })
        assert response.status_code == 422

    def test_server_internal_errors(self, client, mock_server):
        """Test handling of internal server errors."""
        # Mock workflow store to raise exception
        mock_server.workflow_store.list_all.side_effect = Exception("Database error")

        response = client.get("/api/workflows")
        assert response.status_code == 500

    def test_method_not_allowed(self, client):
        """Test method not allowed responses."""
        # GET on POST-only endpoint
        response = client.get("/api/devices/connect")
        assert response.status_code == 405

        # DELETE on GET-only endpoint
        response = client.delete("/api/health")
        assert response.status_code == 405


class TestCORS:
    """Test CORS middleware functionality."""

    def test_cors_headers(self, client):
        """Test that CORS headers are properly set."""
        response = client.options("/api/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })

        # Should allow the request from localhost:3000
        assert "Access-Control-Allow-Origin" in response.headers

    def test_preflight_requests(self, client):
        """Test handling of preflight OPTIONS requests."""
        response = client.options("/api/ai/chat", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"
        })

        assert response.status_code == 200
        assert "Access-Control-Allow-Methods" in response.headers


if __name__ == "__main__":
    pytest.main([__file__])