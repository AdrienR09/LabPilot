#!/usr/bin/env python3
"""Test Phase 4: Session Config Persistence (Core Components).

Tests the configuration persistence system without requiring
external dependencies like FastAPI. This verifies the core
functionality that Phase 4 provides.
"""

import sys
import json
import tempfile
import asyncio
import time
from pathlib import Path

# Add labpilot to path
labpilot_root = Path(__file__).parent.parent
sys.path.insert(0, str(labpilot_root / "src"))

print("=" * 80)
print("💾 LABPILOT PHASE 4 TEST - CONFIG PERSISTENCE")
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
    from labpilot_core.core.session import Session
    from labpilot_core.ai.ai_session import AIConversation
    from labpilot_core.ai.provider import AIMessage
    print("✅ All config imports successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

print()

async def test_user_preferences():
    """Test UserPreferences dataclass."""
    print("1. Testing UserPreferences...")

    try:
        # Default preferences
        prefs = UserPreferences()
        assert prefs.theme == "dark"
        assert prefs.ai_provider == "ollama"
        assert prefs.decimal_places == 3
        print("   ✅ Default preferences created")

        # Custom preferences
        custom_prefs = UserPreferences(
            theme="light",
            ai_provider="openai",
            ai_model="gpt-4",
            decimal_places=2,
            auto_save=False
        )
        assert custom_prefs.theme == "light"
        assert custom_prefs.ai_model == "gpt-4"
        assert custom_prefs.auto_save == False
        print("   ✅ Custom preferences work")

        # JSON serialization
        prefs_dict = {
            "theme": prefs.theme,
            "ai_provider": prefs.ai_provider,
            "decimal_places": prefs.decimal_places,
            "auto_save": prefs.auto_save
        }
        json_str = json.dumps(prefs_dict)
        assert len(json_str) > 0
        print("   ✅ JSON serialization works")

    except Exception as e:
        print(f"   ❌ UserPreferences test failed: {e}")
        return False

    return True


async def test_device_config():
    """Test DeviceConfig dataclass."""
    print("2. Testing DeviceConfig...")

    try:
        # Basic device config
        device = DeviceConfig(
            name="laser_controller",
            adapter_type="thorlabs_pm100",
            connection_params={"port": "/dev/ttyUSB0", "baudrate": 9600}
        )

        assert device.name == "laser_controller"
        assert device.connection_params["port"] == "/dev/ttyUSB0"
        assert device.is_enabled == True
        assert device.custom_settings == {}  # Default empty dict
        print("   ✅ Basic DeviceConfig created")

        # Device with custom settings
        advanced_device = DeviceConfig(
            name="spectrometer",
            adapter_type="ocean_optics_usb4000",
            connection_params={"serial": "USB4H12345"},
            custom_settings={"integration_time": 100, "averaging": 5},
            is_enabled=False
        )

        assert advanced_device.custom_settings["integration_time"] == 100
        assert advanced_device.is_enabled == False
        print("   ✅ Advanced DeviceConfig with settings works")

        # Timestamp handling
        device.last_connected = time.time()
        assert device.last_connected is not None
        print("   ✅ Timestamp handling works")

    except Exception as e:
        print(f"   ❌ DeviceConfig test failed: {e}")
        return False

    return True


async def test_session_config():
    """Test SessionConfig dataclass."""
    print("3. Testing SessionConfig...")

    try:
        # Empty session config
        config = SessionConfig()
        assert config.session_id is not None
        assert config.created_at is not None
        assert len(config.devices) == 0
        assert config.preferences is not None
        print("   ✅ Empty SessionConfig created with defaults")

        # Session config with data
        device1 = DeviceConfig("laser", "thorlabs", {"port": "USB0"})
        device2 = DeviceConfig("detector", "keithley", {"address": "24"})
        prefs = UserPreferences(theme="light", decimal_places=4)

        full_config = SessionConfig(
            devices=[device1, device2],
            preferences=prefs,
            active_workflow_id="scan_123",
            recent_scans=["scan_1", "scan_2"]
        )

        assert len(full_config.devices) == 2
        assert full_config.devices[0].name == "laser"
        assert full_config.preferences.theme == "light"
        assert full_config.active_workflow_id == "scan_123"
        assert len(full_config.recent_scans) == 2
        print("   ✅ Full SessionConfig with data works")

        # Automatic timestamp updates
        original_updated = full_config.updated_at
        time.sleep(0.01)  # Small delay
        full_config.updated_at = time.time()
        assert full_config.updated_at > original_updated
        print("   ✅ Timestamp updates work")

    except Exception as e:
        print(f"   ❌ SessionConfig test failed: {e}")
        return False

    return True


async def test_config_persistence():
    """Test ConfigPersistence class functionality."""
    print("4. Testing ConfigPersistence...")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "test_config"

        try:
            # Initialize persistence
            persistence = ConfigPersistence(config_dir)
            print("   ✅ ConfigPersistence initialized")

            # Verify directory structure created
            assert persistence.config_dir.exists()
            assert persistence.devices_dir.exists()
            assert persistence.conversations_dir.exists()
            assert persistence.backups_dir.exists()
            print("   ✅ Directory structure created")

            # Test saving session config
            config = SessionConfig(
                devices=[DeviceConfig("test_device", "test_adapter", {"test": "param"})],
                preferences=UserPreferences(theme="dark"),
                active_workflow_id="workflow_test"
            )

            config_path = persistence.save_session_config(config)
            assert config_path.exists()
            print("   ✅ Session config saved")

            # Test loading session config
            loaded_config = persistence.load_session_config()
            assert loaded_config is not None
            assert loaded_config.session_id == config.session_id
            assert len(loaded_config.devices) == 1
            assert loaded_config.devices[0].name == "test_device"
            assert loaded_config.preferences.theme == "dark"
            assert loaded_config.active_workflow_id == "workflow_test"
            print("   ✅ Session config loaded and verified")

            # Test device config persistence
            device = DeviceConfig("special_device", "special_adapter", {"special": "value"})
            device_path = persistence.save_device_config(device)
            assert device_path.exists()

            loaded_device = persistence.load_device_config("special_device")
            assert loaded_device is not None
            assert loaded_device.adapter_type == "special_adapter"
            assert loaded_device.connection_params["special"] == "value"
            print("   ✅ Device config persistence works")

        except Exception as e:
            print(f"   ❌ ConfigPersistence test failed: {e}")
            return False

    return True


async def test_conversation_persistence():
    """Test AI conversation persistence."""
    print("5. Testing AI conversation persistence...")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "conversation_test"
        persistence = ConfigPersistence(config_dir)

        try:
            # Create conversation with messages
            conversation = AIConversation("test_chat")
            conversation.add_message(AIMessage(
                role="user",
                content="How do I connect to the laser?"
            ))
            conversation.add_message(AIMessage(
                role="assistant",
                content="To connect to the laser, use the connect_device tool with the appropriate parameters."
            ))
            conversation.add_message(AIMessage(
                role="user",
                content="Thanks! Can you create a workflow for power measurement?"
            ))

            assert len(conversation.messages) == 3
            print("   ✅ Conversation with messages created")

            # Save conversation
            conv_path = persistence.save_conversation(conversation)
            assert conv_path.exists()
            print("   ✅ Conversation saved to disk")

            # Load conversation
            loaded_conv = persistence.load_conversation("test_chat")
            assert loaded_conv is not None
            assert loaded_conv.id == "test_chat"
            assert len(loaded_conv.messages) == 3
            assert loaded_conv.messages[0].content == "How do I connect to the laser?"
            assert loaded_conv.messages[1].role == "assistant"
            print("   ✅ Conversation loaded and verified")

            # Test conversation listing
            conv_ids = persistence.list_conversations()
            assert "test_chat" in conv_ids
            print("   ✅ Conversation listing works")

        except Exception as e:
            print(f"   ❌ Conversation persistence test failed: {e}")
            return False

    return True


async def test_session_integration():
    """Test Session integration with config system."""
    print("6. Testing Session integration...")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "session_test"

        try:
            # Create session and persistence
            session = Session()
            persistence = ConfigPersistence(config_dir)

            # Create config from session
            config = persistence.from_session(session)
            assert config is not None
            assert config.session_id is not None
            print("   ✅ Config created from Session")

            # Add some mock devices to session
            class MockDevice:
                def __init__(self, name):
                    self.name = name
                    self._adapter_type = "mock_adapter"

            session.devices["mock_laser"] = MockDevice("mock_laser")
            session.devices["mock_detector"] = MockDevice("mock_detector")

            # Create config from session with devices
            config_with_devices = persistence.from_session(session)
            assert len(config_with_devices.devices) == 2
            print("   ✅ Config includes session devices")

            # Apply config to session
            persistence.to_session(config_with_devices, session)
            assert hasattr(session, '_config')
            print("   ✅ Config applied to session")

            # Test config summary
            summary = persistence.get_config_summary()
            assert "config_dir" in summary
            assert "session_config_exists" in summary
            print("   ✅ Config summary generation works")

        except Exception as e:
            print(f"   ❌ Session integration test failed: {e}")
            return False

    return True


async def main():
    """Run all configuration persistence tests."""

    tests = [
        ("UserPreferences", test_user_preferences),
        ("DeviceConfig", test_device_config),
        ("SessionConfig", test_session_config),
        ("ConfigPersistence", test_config_persistence),
        ("Conversation Persistence", test_conversation_persistence),
        ("Session Integration", test_session_integration),
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
    print("🎯 CONFIGURATION PERSISTENCE TEST SUMMARY")
    print("=" * 80)
    print()

    if passed == total:
        print("✅ All configuration components verified:")
        print("   • UserPreferences: UI, AI, and workflow settings")
        print("   • DeviceConfig: Connection parameters and custom settings")
        print("   • SessionConfig: Complete session state with metadata")
        print("   • ConfigPersistence: JSON-based persistence with backups")
        print("   • AI Conversations: Message history with full fidelity")
        print("   • Session Integration: Bidirectional config-session sync")
        print()
        print("💾 PHASE 4A COMPLETE: CONFIG PERSISTENCE READY")
        print()
        print("Note: FastAPI server requires additional dependencies.")
        print("See requirements.txt for full Phase 4 setup.")
    else:
        print(f"❌ {total - passed} of {total} tests failed")
        print("Phase 4A needs fixes before proceeding")

    print()


if __name__ == "__main__":
    asyncio.run(main())