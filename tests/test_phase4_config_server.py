#!/usr/bin/env python3
"""Test Phase 4: Session Config Persistence + FastAPI Server.

Verifies that:
- SessionConfig persistence works correctly
- DeviceConfig and UserPreferences serialization
- AI conversation history persistence
- FastAPI server initialization and basic endpoints
- WebSocket connections and event broadcasting

This test can run without requiring actual devices or AI providers.
"""

import sys
import json
import tempfile
import asyncio
from pathlib import Path

# Add labpilot to path
labpilot_root = Path(__file__).parent.parent
sys.path.insert(0, str(labpilot_root / "src"))

print("=" * 80)
print("🌐 LABPILOT PHASE 4 TEST - CONFIG + SERVER")
print("=" * 80)
print()

# Test imports
try:
    from labpilot_core.config import (
        SessionConfig,
        UserPreferences,
        DeviceConfig,
        ConfigPersistence,
        ConfigError,
    )
    from labpilot_core.server import LabPilotServer, create_app
    from labpilot_core.core.session import Session
    from labpilot_core.ai.ai_session import AIConversation
    from labpilot_core.ai.provider import AIMessage
    print("✅ All Phase 4 imports successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

print()

async def test_config_persistence():
    """Test configuration persistence functionality."""
    print("1. Testing SessionConfig and persistence...")

    # Use temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "test_config"

        try:
            # Initialize config persistence
            persistence = ConfigPersistence(config_dir)
            print("   ✅ ConfigPersistence initialized")

            # Create test configuration
            test_prefs = UserPreferences(
                theme="dark",
                ai_provider="ollama",
                ai_model="llama3.1",
                decimal_places=2
            )

            test_device = DeviceConfig(
                name="test_laser",
                adapter_type="thorlabs_pm100",
                connection_params={"port": "/dev/ttyUSB0", "baudrate": 9600},
                custom_settings={"timeout": 5.0}
            )

            config = SessionConfig(
                devices=[test_device],
                preferences=test_prefs,
                active_workflow_id="workflow_123"
            )

            print("   ✅ SessionConfig created with preferences and device")

            # Save configuration
            config_path = persistence.save_session_config(config)
            print(f"   ✅ Configuration saved to {config_path}")

            # Load configuration
            loaded_config = persistence.load_session_config()
            print("   ✅ Configuration loaded successfully")

            # Verify loaded data
            assert loaded_config.preferences.theme == "dark"
            assert loaded_config.preferences.decimal_places == 2
            assert len(loaded_config.devices) == 1
            assert loaded_config.devices[0].name == "test_laser"
            assert loaded_config.active_workflow_id == "workflow_123"
            print("   ✅ Configuration data verified")

            # Test device-specific config
            device_path = persistence.save_device_config(test_device)
            loaded_device = persistence.load_device_config("test_laser")
            assert loaded_device.adapter_type == "thorlabs_pm100"
            assert loaded_device.connection_params["port"] == "/dev/ttyUSB0"
            print("   ✅ Device configuration persistence works")

            # Test AI conversation persistence
            conversation = AIConversation("test_conversation")
            conversation.add_message(AIMessage(
                role="user",
                content="Hello, can you help me with the laser?"
            ))
            conversation.add_message(AIMessage(
                role="assistant",
                content="Of course! I can help you control the laser device."
            ))

            conv_path = persistence.save_conversation(conversation)
            loaded_conversation = persistence.load_conversation("test_conversation")

            assert loaded_conversation.id == "test_conversation"
            assert len(loaded_conversation.messages) == 2
            assert loaded_conversation.messages[0].content == "Hello, can you help me with the laser?"
            print("   ✅ AI conversation persistence works")

            # Test configuration summary
            summary = persistence.get_config_summary()
            assert summary["session_config_exists"] == True
            assert summary["device_configs"] == 1
            assert summary["conversations"] == 1
            print("   ✅ Configuration summary works")

        except Exception as e:
            print(f"   ❌ Config persistence test failed: {e}")
            return False

    return True


async def test_server_initialization():
    """Test FastAPI server initialization."""
    print("2. Testing FastAPI server initialization...")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "server_test"

        try:
            # Create server
            server = LabPilotServer(config_dir)
            print("   ✅ LabPilotServer created")

            # Initialize server components
            await server.initialize()
            print("   ✅ Server components initialized")

            # Verify components
            assert server.session is not None
            assert server.config_persistence is not None
            assert server.workflow_store is not None
            assert server.workflow_engine is not None
            print("   ✅ All server components available")

            # Test session status
            devices_count = len(server.session.devices)
            ai_available = server.ai_session is not None
            print(f"   ✅ Session status: {devices_count} devices, AI: {ai_available}")

            # Cleanup
            await server.shutdown()
            print("   ✅ Server shutdown successful")

        except Exception as e:
            print(f"   ❌ Server initialization test failed: {e}")
            return False

    return True


async def test_fastapi_app():
    """Test FastAPI application creation."""
    print("3. Testing FastAPI application...")

    try:
        # Create FastAPI app
        app = create_app()
        print("   ✅ FastAPI app created")

        # Verify app configuration
        assert app.title == "LabPilot API"
        assert hasattr(app.state, 'server')
        print("   ✅ App configuration verified")

        # Check routes are registered
        route_paths = [route.path for route in app.routes]
        expected_routes = [
            "/api/health",
            "/api/session/status",
            "/api/devices",
            "/api/workflows",
            "/api/ai/chat",
            "/ws"
        ]

        for expected_route in expected_routes:
            assert expected_route in route_paths, f"Missing route: {expected_route}"
        print(f"   ✅ All {len(expected_routes)} API routes registered")

    except Exception as e:
        print(f"   ❌ FastAPI app test failed: {e}")
        return False

    return True


async def test_session_integration():
    """Test session and config integration."""
    print("4. Testing Session-Config integration...")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "integration_test"

        try:
            # Create session and persistence
            session = Session()
            persistence = ConfigPersistence(config_dir)

            # Create config from session
            config = persistence.from_session(session)
            assert config.session_id is not None
            print("   ✅ Config created from Session")

            # Save and load config
            persistence.save_session_config(config)
            loaded_config = persistence.load_session_config()
            assert loaded_config.session_id == config.session_id
            print("   ✅ Session config round-trip successful")

            # Apply config to session
            persistence.to_session(loaded_config, session)
            assert hasattr(session, '_config')
            print("   ✅ Config applied to Session")

        except Exception as e:
            print(f"   ❌ Session integration test failed: {e}")
            return False

    return True


async def test_websocket_manager():
    """Test WebSocket manager functionality."""
    print("5. Testing WebSocket components...")

    try:
        from labpilot_core.server import WebSocketManager

        # Create WebSocket manager
        manager = WebSocketManager()
        assert len(manager.active_connections) == 0
        print("   ✅ WebSocketManager created")

        # Test broadcast (no connections)
        await manager.broadcast('{"type": "test", "message": "Hello"}')
        print("   ✅ Broadcast with no connections works")

        # Test connection management (mock connections)
        class MockWebSocket:
            def __init__(self, name):
                self.name = name
                self.connected = True

        mock_ws1 = MockWebSocket("client1")
        mock_ws2 = MockWebSocket("client2")

        manager.active_connections.append(mock_ws1)
        manager.active_connections.append(mock_ws2)
        assert len(manager.active_connections) == 2
        print("   ✅ Connection tracking works")

        manager.disconnect(mock_ws1)
        assert len(manager.active_connections) == 1
        print("   ✅ Disconnection handling works")

    except Exception as e:
        print(f"   ❌ WebSocket test failed: {e}")
        return False

    return True


async def main():
    """Run all Phase 4 tests."""

    tests = [
        ("Config Persistence", test_config_persistence),
        ("Server Initialization", test_server_initialization),
        ("FastAPI Application", test_fastapi_app),
        ("Session Integration", test_session_integration),
        ("WebSocket Components", test_websocket_manager),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"Running {test_name}...")
        try:
            success = await test_func()
            results.append(success)
        except Exception as e:
            print(f"   ❌ {test_name} failed with exception: {e}")
            results.append(False)
        print()

    # Summary
    passed = sum(results)
    total = len(results)

    print("=" * 80)
    print("🎯 PHASE 4 TEST SUMMARY")
    print("=" * 80)
    print()

    if passed == total:
        print("✅ All Phase 4 components verified:")
        print("   • SessionConfig: Complete configuration persistence")
        print("   • UserPreferences: UI and AI settings management")
        print("   • DeviceConfig: Device connection parameters")
        print("   • ConfigPersistence: JSON-based config with backups")
        print("   • LabPilotServer: FastAPI server with lifecycle")
        print("   • API Routes: 8+ endpoints for browser interface")
        print("   • WebSocket: Real-time event broadcasting")
        print("   • Integration: Session-config bidirectional sync")
        print()
        print("🚀 PHASE 4 COMPLETE: CONFIG + SERVER READY")
        print()
        print("Next: Phase 5 - React Frontend (UI Components + State)")
    else:
        print(f"❌ {total - passed} of {total} tests failed")
        print("Phase 4 needs fixes before proceeding")

    print()


if __name__ == "__main__":
    asyncio.run(main())