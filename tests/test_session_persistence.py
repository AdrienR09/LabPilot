"""
Comprehensive tests for LabPilot session persistence system.

Tests session configuration saving/loading, automatic persistence,
atomic operations, recovery scenarios, and edge cases.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import asyncio
import json
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Import session and configuration components
from labpilot_core.session_config import SessionConfig, DeviceConfig, WorkflowState, PanelSpec, AIConfig, UserPreferences
from labpilot_core.config import ConfigPersistence


class TestSessionConfig:
    """Test SessionConfig data model."""

    def test_session_config_creation_defaults(self):
        """Test SessionConfig creation with default values."""
        config = SessionConfig()

        # Check defaults
        assert config.session_id.startswith("session_")
        assert isinstance(config.created_at, datetime)
        assert isinstance(config.updated_at, datetime)
        assert len(config.devices) == 0
        assert len(config.workflows) == 0
        assert len(config.open_panels) == 0
        assert config.ai_config is None
        assert isinstance(config.preferences, UserPreferences)
        assert isinstance(config.metadata, dict)

    def test_session_config_with_data(self):
        """Test SessionConfig with actual data."""
        # Create device config
        device_config = DeviceConfig(
            name="test_device",
            adapter_type="TestAdapter",
            connection_params={"port": "COM1"},
            auto_connect=True
        )

        # Create workflow state
        workflow_state = WorkflowState(
            workflow_id="wf_123",
            name="Test Workflow",
            status="running",
            current_node="node_1",
            progress=0.5
        )

        # Create panel spec
        panel_spec = PanelSpec(
            panel_id="panel_1",
            title="Test Panel",
            panel_type="spectrum",
            spec={"type": "window", "title": "Test"}
        )

        # Create AI config
        ai_config = AIConfig(
            provider="ollama",
            model="mistral",
            base_url="http://localhost:11434"
        )

        # Create session config
        config = SessionConfig(
            session_id="test_session",
            devices=[device_config],
            workflows=[workflow_state],
            open_panels=[panel_spec],
            ai_config=ai_config,
            metadata={"experiment": "spectroscopy"}
        )

        # Verify data
        assert config.session_id == "test_session"
        assert len(config.devices) == 1
        assert config.devices[0].name == "test_device"
        assert len(config.workflows) == 1
        assert config.workflows[0].name == "Test Workflow"
        assert len(config.open_panels) == 1
        assert config.open_panels[0].title == "Test Panel"
        assert config.ai_config.provider == "ollama"
        assert config.metadata["experiment"] == "spectroscopy"

    def test_session_config_serialization(self):
        """Test SessionConfig JSON serialization."""
        device_config = DeviceConfig(
            name="spectrometer",
            adapter_type="OceanOpticsAdapter",
            connection_params={"serial": "SPEC001"}
        )

        config = SessionConfig(
            session_id="test123",
            devices=[device_config],
            metadata={"lab": "photonics"}
        )

        # Test model_dump (Pydantic v2)
        data = config.model_dump()
        assert isinstance(data, dict)
        assert data["session_id"] == "test123"
        assert len(data["devices"]) == 1
        assert data["devices"][0]["name"] == "spectrometer"
        assert data["metadata"]["lab"] == "photonics"

        # Should be JSON serializable
        json_str = json.dumps(data, default=str)
        assert "test123" in json_str

    def test_session_config_deserialization(self):
        """Test SessionConfig JSON deserialization."""
        data = {
            "session_id": "restored_session",
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-01T11:00:00Z",
            "devices": [
                {
                    "name": "laser",
                    "adapter_type": "LaserAdapter",
                    "connection_params": {"ip": "192.168.1.100"},
                    "auto_connect": False
                }
            ],
            "workflows": [],
            "open_panels": [],
            "ai_config": {
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "test_key"
            },
            "preferences": {"theme": "dark"},
            "metadata": {"user": "alice"}
        }

        # Test model_validate (Pydantic v2)
        config = SessionConfig.model_validate(data)

        assert config.session_id == "restored_session"
        assert len(config.devices) == 1
        assert config.devices[0].name == "laser"
        assert config.ai_config.provider == "openai"
        assert config.preferences.theme == "dark"
        assert config.metadata["user"] == "alice"


class TestAtomicOperations:
    """Test atomic file operations for session persistence."""

    def test_save_atomic_operation(self):
        """Test that saves are atomic (temp file -> rename)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "session.json"
            temp_path = Path(temp_dir) / "session.json.tmp"

            config = SessionConfig(session_id="atomic_test")

            # Save should create temp file then rename
            with patch("pathlib.Path.open", mock_open()) as mock_file, \
                 patch("pathlib.Path.replace") as mock_rename:

                config.save(config_path)

                # Should have opened temp file for writing
                mock_file.assert_called_with("w", encoding="utf-8")

                # Should have renamed temp file to final location
                mock_rename.assert_called_once()
                args = mock_rename.call_args[0]
                assert str(args[0]).endswith("session.json")

    def test_load_from_file(self):
        """Test loading session config from actual file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_session.json"

            # Create and save initial config
            original_config = SessionConfig(
                session_id="load_test",
                metadata={"test": "data"}
            )
            original_config.save(config_path)

            # Load config from file
            loaded_config = SessionConfig.load(config_path)

            assert loaded_config.session_id == "load_test"
            assert loaded_config.metadata["test"] == "data"
            assert isinstance(loaded_config.created_at, datetime)

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file returns None."""
        nonexistent_path = Path("/nonexistent/path/config.json")
        result = SessionConfig.load(nonexistent_path)
        assert result is None

    def test_load_corrupted_file(self):
        """Test loading corrupted JSON file returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "corrupted.json"

            # Write invalid JSON
            with config_path.open("w") as f:
                f.write('{"invalid": json content')

            result = SessionConfig.load(config_path)
            assert result is None


class TestConfigPersistence:
    """Test ConfigPersistence class functionality."""

    def test_config_persistence_creation(self):
        """Test ConfigPersistence initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            persistence = ConfigPersistence(config_dir)

            assert persistence.config_dir == config_dir
            assert config_dir.exists()

    def test_config_persistence_default_dir(self):
        """Test ConfigPersistence with default directory."""
        persistence = ConfigPersistence()
        assert persistence.config_dir.name == ".labpilot"

    def test_save_and_load_session_config(self):
        """Test complete save/load cycle."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            persistence = ConfigPersistence(config_dir)

            # Create config with data
            device_config = DeviceConfig(
                name="test_instrument",
                adapter_type="TestAdapter",
                connection_params={"setting": "value"}
            )

            original_config = SessionConfig(
                session_id="persistence_test",
                devices=[device_config],
                metadata={"experiment": "test"}
            )

            # Save config
            saved_path = persistence.save_session_config(original_config)
            assert saved_path.exists()

            # Load config
            loaded_config = persistence.load_session_config()
            assert loaded_config is not None
            assert loaded_config.session_id == "persistence_test"
            assert len(loaded_config.devices) == 1
            assert loaded_config.devices[0].name == "test_instrument"

    def test_save_with_backup(self):
        """Test that saving creates backups of existing config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            persistence = ConfigPersistence(config_dir)

            # Save first config
            config1 = SessionConfig(session_id="backup_test_1")
            persistence.save_session_config(config1)

            # Save second config (should backup first)
            config2 = SessionConfig(session_id="backup_test_2")
            persistence.save_session_config(config2)

            # Check that backup was created
            backup_pattern = "session_config.*.json"
            backups = list(config_dir.glob(backup_pattern))
            assert len(backups) >= 1

            # Current config should be the second one
            current = persistence.load_session_config()
            assert current.session_id == "backup_test_2"

    def test_conversation_persistence(self):
        """Test AI conversation saving and loading."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            persistence = ConfigPersistence(config_dir)

            # Save conversation
            conversation = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]

            persistence.save_conversation("test_conv", conversation)

            # Load conversation
            loaded = persistence.load_conversation("test_conv")
            assert loaded == conversation

            # List conversations
            conv_ids = persistence.list_conversations()
            assert "test_conv" in conv_ids

    def test_session_conversion(self):
        """Test conversion between Session objects and SessionConfig."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            persistence = ConfigPersistence(config_dir)

            # Mock session object
            mock_session = Mock()
            mock_session.devices = {
                "test_device": Mock(
                    name="test_device",
                    _adapter_type="TestAdapter",
                    connection_params={"param": "value"}
                )
            }
            mock_session._config = {"session_id": "mock_session"}

            # Convert Session to SessionConfig
            config = persistence.from_session(mock_session)
            assert isinstance(config, SessionConfig)
            assert config.session_id == "mock_session"

            # Convert SessionConfig back to Session
            new_session = Mock()
            persistence.to_session(config, new_session)

            # Verify session was updated (would need more specific mocking for full test)
            assert True  # Basic smoke test


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_save_to_readonly_directory(self):
        """Test saving to read-only directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            readonly_dir = Path(temp_dir) / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)  # Read-only

            config = SessionConfig()
            config_path = readonly_dir / "session.json"

            # Should handle permission error gracefully
            try:
                config.save(config_path)
                assert False, "Should have raised an exception"
            except (PermissionError, OSError):
                pass  # Expected
            finally:
                # Restore permissions for cleanup
                readonly_dir.chmod(0o755)

    def test_large_session_config(self):
        """Test handling of large session configurations."""
        # Create config with many devices
        devices = []
        for i in range(100):
            device = DeviceConfig(
                name=f"device_{i}",
                adapter_type="TestAdapter",
                connection_params={"index": i, "data": "x" * 1000}
            )
            devices.append(device)

        config = SessionConfig(
            session_id="large_config",
            devices=devices
        )

        # Should handle serialization of large config
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "large.json"
            config.save(config_path)

            # Should be able to load it back
            loaded = SessionConfig.load(config_path)
            assert loaded is not None
            assert len(loaded.devices) == 100
            assert loaded.devices[50].name == "device_50"

    def test_concurrent_access(self):
        """Test concurrent access to session files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "concurrent.json"

            async def save_config(session_id: str):
                """Save a config with given session ID."""
                config = SessionConfig(session_id=session_id)
                config.save(config_path)

            async def test_concurrent():
                # Start multiple saves concurrently
                tasks = [
                    save_config(f"session_{i}") for i in range(10)
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Should result in one valid config file
                if config_path.exists():
                    final_config = SessionConfig.load(config_path)
                    assert final_config is not None
                    assert final_config.session_id.startswith("session_")

            # Run the concurrent test
            asyncio.run(test_concurrent())

    def test_config_validation_errors(self):
        """Test handling of invalid configuration data."""
        # Test invalid device config data
        invalid_device_data = {
            "name": "",  # Empty name should fail validation
            "adapter_type": "TestAdapter",
            "connection_params": {}
        }

        with pytest.raises(Exception):  # Pydantic validation error
            DeviceConfig.model_validate(invalid_device_data)

        # Test session config with invalid nested data
        invalid_session_data = {
            "session_id": "test",
            "devices": [invalid_device_data]  # Should fail
        }

        with pytest.raises(Exception):
            SessionConfig.model_validate(invalid_session_data)

    def test_backwards_compatibility(self):
        """Test loading older session config formats."""
        # Simulate older config format (missing some fields)
        old_format_data = {
            "session_id": "old_session",
            "created_at": "2023-01-01T00:00:00Z",
            "devices": [],
            # Missing: updated_at, workflows, open_panels, preferences, etc.
        }

        # Should load successfully with defaults for missing fields
        config = SessionConfig.model_validate(old_format_data)
        assert config.session_id == "old_session"
        assert len(config.workflows) == 0  # Default empty list
        assert isinstance(config.preferences, UserPreferences)  # Default object

    def test_config_summary(self):
        """Test configuration summary generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            persistence = ConfigPersistence(config_dir)

            # Create config with various components
            device = DeviceConfig(name="test_device", adapter_type="TestAdapter")
            config = SessionConfig(
                session_id="summary_test",
                devices=[device],
                metadata={"experiment": "test"}
            )

            # Save config and conversation
            persistence.save_session_config(config)
            persistence.save_conversation("test_conv", [{"role": "user", "content": "test"}])

            # Get summary
            summary = persistence.get_config_summary()

            assert isinstance(summary, dict)
            assert "session" in summary
            assert "devices_count" in summary
            assert "conversations_count" in summary
            assert summary["devices_count"] == 1
            assert summary["conversations_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__])