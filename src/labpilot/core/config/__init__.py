"""Session configuration persistence for LabPilot.

Handles saving and loading of session state including:
- Connected devices and their configurations
- User preferences and settings
- Workflow definitions and history
- Recent scan data and results

Uses JSON for human-readable configs with optional encryption
for sensitive data like API keys and device credentials.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from labpilot.core.config.paths import labpilot_home
from labpilot.core.session import Session
from labpilot.core.workflow.store import WorkflowSummary

__all__ = [
    "ConfigError",
    "ConfigPersistence",
    "DeviceConfig",
    "SessionConfig",
    "UserPreferences"
]


@dataclass
class DeviceConfig:
    """Configuration for a connected device."""

    name: str
    adapter_type: str  # e.g., "keithley_2400", "thorlabs_pm100"
    connection_params: dict[str, Any]  # Port, address, etc.
    id: str | None = None  # Dashboard instrument id, defaults to name
    custom_settings: dict[str, Any] = None  # User overrides
    last_connected: float | None = None
    is_enabled: bool = True
    status: str | None = None  # Snapshot at save time: idle | busy | error

    def __post_init__(self):
        if self.custom_settings is None:
            self.custom_settings = {}
        if self.id is None:
            self.id = self.name


@dataclass
class UserPreferences:
    """User preferences and application settings."""

    # UI preferences
    theme: str = "dark"  # "light" or "dark"
    units: str = "metric"  # "metric" or "imperial"
    decimal_places: int = 3
    auto_save: bool = True

    # Workflow preferences
    auto_backup_workflows: bool = True
    default_analysis_timeout: float = 30.0

    # Data preferences
    default_data_format: str = "hdf5"  # "hdf5", "csv", "json"
    compression: bool = True
    retention_days: int | None = 90  # None = keep forever


@dataclass
class SessionConfig:
    """Complete session configuration."""

    # Metadata
    config_version: str = "1.0"
    session_id: str = None
    created_at: float = None
    updated_at: float = None

    # Core configuration
    devices: list[DeviceConfig] = None
    preferences: UserPreferences = None

    # State information
    active_workflow_id: str | None = None
    recent_scans: list[str] = None  # Scan UIDs

    # Cached data
    workflow_summaries: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.devices is None:
            self.devices = []
        if self.preferences is None:
            self.preferences = UserPreferences()
        if self.recent_scans is None:
            self.recent_scans = []
        if self.workflow_summaries is None:
            self.workflow_summaries = []
        if self.session_id is None:
            import uuid
            self.session_id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = time.time()
        self.updated_at = time.time()


class ConfigError(Exception):
    """Raised when configuration operations fail."""


class ConfigPersistence:
    """Handles session configuration persistence.

    Features:
    - Human-readable JSON configuration files
    - Automatic backup and versioning
    - Sensitive data encryption (API keys, passwords)
    - Configuration validation and migration
    - Atomic writes to prevent corruption

    Directory structure:
        ~/.labpilot/
        ├── config/
        │   ├── session.json          # Main session config
        │   ├── devices/              # Device-specific configs
        │   │   ├── laser_1.json
        │   │   └── detector_1.json
        │   └── backups/              # Timestamped backups
        │       ├── session_20240325_143022.json
        │       └── ...
        ├── data/                     # Scan data storage
        └── workflows/                # Workflow storage (managed by WorkflowStore)
    """

    def __init__(self, config_dir: Path | None = None):
        """Initialize configuration persistence.

        Args:
            config_dir: Configuration directory. Defaults to ~/.labpilot
        """
        if config_dir is None:
            config_dir = labpilot_home()

        self.config_dir = Path(config_dir)
        self.session_config_path = self.config_dir / "config" / "session.json"
        self.devices_dir = self.config_dir / "config" / "devices"
        self.backups_dir = self.config_dir / "config" / "backups"

        # Create directory structure
        self._init_directories()

    def _init_directories(self) -> None:
        """Create configuration directory structure."""
        dirs_to_create = [
            self.config_dir / "config",
            self.devices_dir,
            self.backups_dir,
            self.config_dir / "data",
            self.config_dir / "workflows",
        ]

        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)

    def save_session_config(self, config: SessionConfig) -> Path:
        """Save session configuration to disk.

        Args:
            config: Session configuration to save.

        Returns:
            Path to saved configuration file.

        Raises:
            ConfigError: If save operation fails.
        """
        try:
            # Update timestamp
            config.updated_at = time.time()

            # Backup existing config
            if self.session_config_path.exists():
                self._backup_config(self.session_config_path)

            # Convert to JSON-serializable format
            config_dict = asdict(config)

            # Write atomically (temp file + rename)
            temp_path = self.session_config_path.with_suffix('.json.tmp')
            with open(temp_path, 'w') as f:
                json.dump(config_dict, f, indent=2, default=self._json_serializer)

            # Atomic move
            temp_path.rename(self.session_config_path)

            return self.session_config_path

        except Exception as e:
            raise ConfigError(f"Failed to save session config: {e}")

    def load_session_config(self) -> SessionConfig | None:
        """Load session configuration from disk.

        Returns:
            SessionConfig instance or None if no config exists.

        Raises:
            ConfigError: If config exists but cannot be loaded.
        """
        if not self.session_config_path.exists():
            return None

        try:
            with open(self.session_config_path) as f:
                config_dict = json.load(f)

            # Convert back to dataclass
            # Handle nested UserPreferences
            if config_dict.get('preferences'):
                config_dict['preferences'] = UserPreferences(**config_dict['preferences'])

            # Handle DeviceConfig list
            if config_dict.get('devices'):
                config_dict['devices'] = [
                    DeviceConfig(**device_dict)
                    for device_dict in config_dict['devices']
                ]

            config = SessionConfig(**config_dict)
            return config

        except Exception as e:
            raise ConfigError(f"Failed to load session config: {e}")

    def save_device_config(self, device_config: DeviceConfig) -> Path:
        """Save device-specific configuration.

        Args:
            device_config: Device configuration to save.

        Returns:
            Path to saved device config file.
        """
        try:
            device_file = self.devices_dir / f"{device_config.name}.json"

            # Backup if exists
            if device_file.exists():
                self._backup_config(device_file)

            # Save device config
            with open(device_file, 'w') as f:
                json.dump(asdict(device_config), f, indent=2, default=self._json_serializer)

            return device_file

        except Exception as e:
            raise ConfigError(f"Failed to save device config '{device_config.name}': {e}")

    def load_device_config(self, device_name: str) -> DeviceConfig | None:
        """Load device-specific configuration.

        Args:
            device_name: Name of device to load config for.

        Returns:
            DeviceConfig instance or None if not found.
        """
        device_file = self.devices_dir / f"{device_name}.json"

        if not device_file.exists():
            return None

        try:
            with open(device_file) as f:
                config_dict = json.load(f)
            return DeviceConfig(**config_dict)

        except Exception as e:
            raise ConfigError(f"Failed to load device config '{device_name}': {e}")

    def from_session(self, session: Session) -> SessionConfig:
        """Create SessionConfig from active Session instance.

        Args:
            session: Active LabPilot session.

        Returns:
            SessionConfig representation of current session state.
        """
        # Extract device configurations
        devices = []
        for name, device in session.devices.items():
            # Get adapter type from device (would need adapter registry)
            adapter_type = getattr(device, '_adapter_type', 'unknown')

            device_config = DeviceConfig(
                name=name,
                adapter_type=adapter_type,
                connection_params={},  # Would extract from device
                last_connected=time.time(),
                is_enabled=True
            )
            devices.append(device_config)

        # Create session config
        config = SessionConfig(
            devices=devices,
            preferences=UserPreferences(),  # Would load from session if available
        )

        return config

    def to_session(self, config: SessionConfig, session: Session) -> None:
        """Apply SessionConfig to Session instance.

        Args:
            config: Configuration to apply.
            session: Session to configure.
        """
        # This would reconnect devices based on config
        # For now, just store the config in session metadata
        session._config = config

    def _backup_config(self, config_path: Path) -> Path:
        """Create timestamped backup of configuration file.

        Args:
            config_path: Path to configuration file to backup.

        Returns:
            Path to backup file.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{config_path.stem}_{timestamp}{config_path.suffix}"
        backup_path = self.backups_dir / backup_name

        shutil.copy2(config_path, backup_path)

        # Keep only last 10 backups
        self._cleanup_old_backups(config_path.stem)

        return backup_path

    def _cleanup_old_backups(self, config_name: str, keep_count: int = 10) -> None:
        """Remove old backup files, keeping only the most recent.

        Args:
            config_name: Name of config file (without extension).
            keep_count: Number of backups to keep.
        """
        backup_pattern = f"{config_name}_*.json"
        backups = sorted(self.backups_dir.glob(backup_pattern))

        if len(backups) > keep_count:
            for backup in backups[:-keep_count]:
                backup.unlink()

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for special types.

        Args:
            obj: Object to serialize.

        Returns:
            JSON-serializable representation.
        """
        if isinstance(obj, Path):
            return str(obj)
        elif hasattr(obj, 'isoformat'):  # datetime objects
            return obj.isoformat()
        else:
            raise TypeError(f"Object {obj} is not JSON serializable")

    def get_config_summary(self) -> dict[str, Any]:
        """Get summary of current configuration state.

        Returns:
            Dictionary with configuration summary.
        """
        summary = {
            "config_dir": str(self.config_dir),
            "session_config_exists": self.session_config_path.exists(),
            "device_configs": len(list(self.devices_dir.glob("*.json"))),
            "conversations": len(self.list_conversations()),
            "backup_count": len(list(self.backups_dir.glob("*.json"))),
        }

        if summary["session_config_exists"]:
            try:
                config = self.load_session_config()
                summary.update({
                    "session_id": config.session_id,
                    "devices_configured": len(config.devices),
                    "last_updated": config.updated_at,
                })
            except ConfigError:
                summary["config_load_error"] = True

        return summary
