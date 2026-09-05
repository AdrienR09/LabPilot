"""
Comprehensive tests for LabPilot server API endpoints.

Tests all REST API endpoints, WebSocket functionality, error handling,
and integration with core components.
"""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI

# Import FastAPI testing components
from fastapi.testclient import TestClient

from labpilot.core.config import DeviceConfig, SessionConfig

# Import server components
from labpilot.core.server import LabPilotServer, WebSocketManager, create_app
from labpilot.core.session import Session


@pytest.fixture
def mock_server():
    """Create mock LabPilotServer for testing."""
    server = Mock(spec=LabPilotServer)
    server.session = Mock(spec=Session)
    server.session.devices = {}
    server.workflow_store = Mock()
    server.workflow_engine = Mock()
    # Real handler code does len(get_running_workflows()) — a bare Mock()
    # isn't lenable, so give it a sane default; tests that care override it.
    server.workflow_engine.get_running_workflows.return_value = []
    server.workflow_set_store = Mock()
    server.config_persistence = Mock()
    # spec=WebSocketManager auto-detects its async methods (connect,
    # send_personal_message, broadcast) and mocks those as AsyncMock —
    # a bare Mock() makes every attribute a plain Mock, so `await
    # server.websocket_manager.connect(...)` in the real route would fail.
    server.websocket_manager = Mock(spec=WebSocketManager)
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
        mock_server.workflow_engine.get_running_workflows.return_value = ["wf1", "wf2"]

        response = client.get("/api/session/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["devices_connected"] == 2
        assert data["data"]["workflow_engine_running"] == 2


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

    def test_connect_device_rejects_unknown_adapter(self, client, mock_server):
        """An adapter key that isn't registered must fail, not report success.

        This route used to return `{"success": true}` unconditionally without
        creating or connecting anything, so a typo'd adapter type looked like
        a working connection.
        """
        response = client.post("/api/devices/connect", json={
            "name": "new_device",
            "adapter_type": "NoSuchAdapter",
            "connection_params": {"port": "COM1"},
        })

        assert response.status_code == 400

    def test_connect_and_disconnect_device_roundtrip(self, client, mock_server):
        """A real registered adapter connects, and disconnecting it again
        goes through the same registry rather than the Session mirror."""
        response = client.post("/api/devices/connect", json={
            "name": "roundtrip_detector",
            "adapter_type": "mock_basic_detector_0d",
            "connection_params": {},
        })
        assert response.status_code == 200, response.text
        assert response.json()["data"]["connected"] is True

        response = client.delete("/api/devices/roundtrip_detector")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["connected"] is False

    def test_disconnect_device_not_found(self, client, mock_server):
        """Test disconnecting nonexistent device."""
        response = client.delete("/api/devices/nonexistent")

        assert response.status_code == 404


class TestWorkflowEndpoints:
    """Test workflow management endpoints."""

    def test_list_workflows(self, client, mock_server):
        """Test listing workflows — only ones "loaded" (script_path present
        in the active workflow-set) are returned, see WorkflowSetPersistence."""
        # NOTE: Mock(name=...) sets the mock's own debug repr, not a real
        # `.name` attribute (a classic unittest.mock gotcha) — must be
        # assigned after construction instead, or `wf.name` returns an
        # auto-generated child Mock that Pydantic can't serialize.
        mock_workflows = [
            Mock(
                id="wf1",
                current_version=1,
                created_at="2024-01-01T10:00:00Z",
                updated_at="2024-01-01T11:00:00Z"
            ),
            Mock(
                id="wf2",
                current_version=2,
                created_at="2024-01-01T12:00:00Z",
                updated_at="2024-01-01T13:00:00Z"
            )
        ]
        mock_workflows[0].name = "Test Workflow 1"
        mock_workflows[1].name = "Test Workflow 2"
        mock_server.workflow_store.list_all.return_value = mock_workflows
        graphs_by_id = {
            "wf1": Mock(metadata={"script_path": "/loaded/wf1.py"}),
            "wf2": Mock(metadata={"script_path": "/loaded/wf2.py"}),
        }
        mock_server.workflow_store.load.side_effect = lambda wf_id: graphs_by_id[wf_id]
        mock_server.workflow_set_store.get_active_name.return_value = "default"
        mock_server.workflow_set_store.load.return_value = ["/loaded/wf1.py", "/loaded/wf2.py"]
        # list_workflows also enriches each entry with running/last-run
        # status (see GET /api/workflows/{id}/execution_state) — a bare
        # Mock() for get_latest_execution would return a non-subscriptable
        # Mock instead of a real dict-or-None, so it's configured here too.
        mock_server.workflow_store.get_latest_execution.return_value = None
        mock_server.workflow_engine.is_running.return_value = False

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
        def fake_save(graph, comment=""):
            # Mirrors the real WorkflowStore.save()'s side effect of
            # assigning a script_path into graph.metadata (see
            # WorkflowStore._ensure_script) — the route depends on this.
            graph.metadata["script_path"] = "/fake/workflow_library/new_workflow.py"
            return 1
        mock_server.workflow_store.save.side_effect = fake_save
        mock_server.workflow_set_store.exists.return_value = False

        request_data = {
            "name": "New Workflow",
            "description": "Test workflow"
        }

        with patch('labpilot.core.server.WorkflowGraph') as mock_wf:
            mock_workflow = Mock()
            mock_workflow.id = "new_wf_id"
            mock_workflow.name = "New Workflow"
            mock_workflow.metadata = {}
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
        mock_graph = Mock(metadata={}, nodes={"n1": {"kind": "acquire"}})
        mock_server.workflow_store.load.return_value = mock_graph

        response = client.post("/api/workflows/wf_123/execute")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["execution_id"] == "exec_123"

    def test_execute_workflow_no_nodes(self, client, mock_server):
        """Executing a workflow with no real graph (e.g. an externally-loaded,
        not-yet-parsed script) is rejected with a clear error rather than
        silently "succeeding" at doing nothing."""
        mock_graph = Mock(metadata={"externally_authored": True}, nodes={})
        mock_server.workflow_store.load.return_value = mock_graph

        response = client.post("/api/workflows/wf_123/execute")

        assert response.status_code == 400


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
        with patch('labpilot.core.server.subprocess.Popen') as mock_popen, \
             patch('labpilot.core.server.Path') as mock_path:

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
        mock_config = SessionConfig(session_id="test_session")
        mock_server.config_persistence.from_session.return_value = mock_config

        response = client.get("/api/session/config")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["data"]["session_id"] == "test_session"
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
        # This test exercises the real connect/accept/receive protocol
        # handshake end-to-end, so it needs the real WebSocketManager here
        # (not the mocked one from the shared fixture) — a mocked
        # `connect()` would never actually call `websocket.accept()`.
        mock_server.websocket_manager = WebSocketManager()
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
        from labpilot.core.server import WebSocketManager

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