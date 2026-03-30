"""Session configuration with automatic save/load and persistence.

Manages complete LabPilot session state including:
- Connected devices and their configurations
- Active workflows and their execution state
- Open Qt windows and their positions
- AI conversation history
- User preferences and settings

Features auto-save every 60s and manual save/load operations.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from labpilot_core.core.session import Session

__all__ = ["DeviceConfig", "PanelSpec", "SessionConfig", "WorkflowState"]


class DeviceConfig(BaseModel):
    """Configuration for a connected device."""

    name: str = Field(..., description="User-assigned device name")
    adapter: str = Field(..., description="Adapter key from registry")
    config: dict[str, Any] = Field(default_factory=dict, description="Device-specific configuration")
    last_status: str = Field(default="disconnected", description="Last known connection status")
    last_error: str | None = Field(default=None, description="Last error message if any")
    connected_at: float | None = Field(default=None, description="Connection timestamp")

    class Config:
        """Pydantic configuration."""
        extra = "forbid"


class PanelSpec(BaseModel):
    """Specification for an open Qt window/panel."""

    panel_id: str = Field(..., description="Unique panel identifier")
    kind: str = Field(default="qt_window", description="Panel type (qt_window, browser_panel)")
    title: str = Field(..., description="Window title")
    window_spec: dict[str, Any] = Field(..., description="Complete DSL window specification")
    position: dict[str, Any] = Field(default_factory=dict, description="Screen position and size")
    device_sources: list[str] = Field(default_factory=list, description="Data sources this panel subscribes to")
    created_at: float = Field(default_factory=time.time, description="Panel creation timestamp")

    class Config:
        """Pydantic configuration."""
        extra = "forbid"


class WorkflowState(BaseModel):
    """State of a workflow execution."""

    workflow_id: str = Field(..., description="Workflow unique identifier")
    graph_json: str = Field(..., description="Serialized WorkflowGraph")
    status: str = Field(default="stopped", description="Execution status (running, paused, stopped)")
    progress: float = Field(default=0.0, description="Execution progress (0-100%)")
    current_node: str | None = Field(default=None, description="Currently executing node ID")
    run_uid: str | None = Field(default=None, description="Current run identifier")
    started_at: float | None = Field(default=None, description="Execution start timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last update timestamp")

    class Config:
        """Pydantic configuration."""
        extra = "forbid"


class SessionConfig(BaseModel):
    """Complete LabPilot session configuration.

    Stores all session state that should persist across restarts:
    - Device connections and configurations
    - Active workflows and their state
    - Open Qt windows/panels
    - AI conversation history
    - User preferences and paths
    """

    # Metadata
    version: str = Field(default="1.0", description="Config format version")
    saved_at: float = Field(default_factory=time.time, description="Last save timestamp")
    session_name: str = Field(..., description="Human-readable session name")
    description: str = Field(default="", description="Optional session description")

    # Core state
    devices: list[DeviceConfig] = Field(default_factory=list, description="Connected devices")
    workflows: list[WorkflowState] = Field(default_factory=list, description="Active workflows")
    open_panels: list[PanelSpec] = Field(default_factory=list, description="Open Qt windows/panels")

    # AI state
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="AI conversation history (last 100 turns)"
    )

    # Paths and settings
    data_dir: str = Field(default="./data", description="Data storage directory")
    workflow_code_dir: str = Field(default="./workflows/code", description="Workflow code storage")
    catalogue_db: str = Field(default="./data/catalogue.db", description="Data catalogue database")
    rag_persist_dir: str = Field(default="./data/rag", description="RAG vector store directory")

    # User preferences
    preferences: dict[str, Any] = Field(default_factory=dict, description="User preferences")

    class Config:
        """Pydantic configuration."""
        extra = "allow"  # Allow extra fields for forward compatibility

    def save(self, path: str | Path) -> None:
        """Save session config to file.

        Args:
            path: File path to save configuration.

        Raises:
            OSError: If file cannot be written.
            ValueError: If configuration is invalid.
        """
        config_path = Path(path)

        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Update timestamp
        self.saved_at = time.time()

        # Write to file atomically (write to temp file, then move)
        temp_path = config_path.with_suffix(config_path.suffix + ".tmp")

        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(
                    self.model_dump(),
                    f,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True
                )

            # Atomic move
            temp_path.replace(config_path)

        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise

    @classmethod
    def load(cls, path: str | Path) -> SessionConfig:
        """Load session config from file.

        Args:
            path: File path to load configuration from.

        Returns:
            Loaded SessionConfig instance.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config file is invalid.
        """
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"Session config not found: {config_path}")

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            return cls.model_validate(data)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            raise ValueError(f"Invalid session config: {e}") from e

    @classmethod
    def create_default(
        self,
        session_name: str = "Default Session",
        description: str = ""
    ) -> SessionConfig:
        """Create default session configuration.

        Args:
            session_name: Name for the session.
            description: Optional description.

        Returns:
            New SessionConfig with default values.
        """
        return SessionConfig(
            session_name=session_name,
            description=description,
            preferences={
                "auto_save_interval": 60,  # seconds
                "max_conversation_history": 100,
                "qt_theme": "dark",
                "default_integration_time": 100,  # ms
                "auto_connect_devices": True,
                "restore_panels_on_load": True
            }
        )

    def add_device(self, name: str, adapter: str, config: dict[str, Any]) -> None:
        """Add device to session configuration.

        Args:
            name: Device name.
            adapter: Adapter key.
            config: Device configuration dict.
        """
        # Remove existing device with same name
        self.devices = [d for d in self.devices if d.name != name]

        # Add new device
        device_config = DeviceConfig(
            name=name,
            adapter=adapter,
            config=config,
            connected_at=time.time()
        )
        self.devices.append(device_config)

    def remove_device(self, name: str) -> bool:
        """Remove device from session configuration.

        Args:
            name: Device name to remove.

        Returns:
            True if device was removed, False if not found.
        """
        original_count = len(self.devices)
        self.devices = [d for d in self.devices if d.name != name]
        return len(self.devices) < original_count

    def get_device(self, name: str) -> DeviceConfig | None:
        """Get device configuration by name.

        Args:
            name: Device name.

        Returns:
            DeviceConfig if found, None otherwise.
        """
        for device in self.devices:
            if device.name == name:
                return device
        return None

    def add_workflow(self, workflow_id: str, graph_json: str) -> None:
        """Add workflow to session state.

        Args:
            workflow_id: Workflow identifier.
            graph_json: Serialized WorkflowGraph.
        """
        # Remove existing workflow with same ID
        self.workflows = [w for w in self.workflows if w.workflow_id != workflow_id]

        # Add new workflow
        workflow_state = WorkflowState(
            workflow_id=workflow_id,
            graph_json=graph_json
        )
        self.workflows.append(workflow_state)

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        """Get workflow state by ID.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            WorkflowState if found, None otherwise.
        """
        for workflow in self.workflows:
            if workflow.workflow_id == workflow_id:
                return workflow
        return None

    def add_panel(
        self,
        panel_id: str,
        title: str,
        window_spec: dict[str, Any],
        position: dict[str, Any] | None = None
    ) -> None:
        """Add Qt panel to session state.

        Args:
            panel_id: Panel identifier.
            title: Window title.
            window_spec: DSL window specification.
            position: Window position/size dict.
        """
        # Remove existing panel with same ID
        self.open_panels = [p for p in self.open_panels if p.panel_id != panel_id]

        # Extract device sources from window spec
        device_sources = self._extract_device_sources(window_spec)

        # Add new panel
        panel_spec = PanelSpec(
            panel_id=panel_id,
            title=title,
            window_spec=window_spec,
            position=position or {},
            device_sources=device_sources
        )
        self.open_panels.append(panel_spec)

    def remove_panel(self, panel_id: str) -> bool:
        """Remove panel from session state.

        Args:
            panel_id: Panel identifier.

        Returns:
            True if panel was removed, False if not found.
        """
        original_count = len(self.open_panels)
        self.open_panels = [p for p in self.open_panels if p.panel_id != panel_id]
        return len(self.open_panels) < original_count

    def add_conversation_turn(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Add turn to conversation history.

        Args:
            role: Speaker role (user, assistant, system).
            content: Message content.
            metadata: Optional metadata dict.
        """
        turn = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }

        self.conversation_history.append(turn)

        # Trim history to max length
        max_history = self.preferences.get("max_conversation_history", 100)
        if len(self.conversation_history) > max_history:
            self.conversation_history = self.conversation_history[-max_history:]

    def get_summary(self) -> dict[str, Any]:
        """Get session summary for display.

        Returns:
            Summary dict with key statistics.
        """
        connected_devices = [d for d in self.devices if d.last_status == "connected"]
        running_workflows = [w for w in self.workflows if w.status == "running"]

        return {
            "session_name": self.session_name,
            "saved_at": self.saved_at,
            "devices_total": len(self.devices),
            "devices_connected": len(connected_devices),
            "workflows_total": len(self.workflows),
            "workflows_running": len(running_workflows),
            "panels_open": len(self.open_panels),
            "conversation_turns": len(self.conversation_history),
            "data_dir": self.data_dir
        }

    def _extract_device_sources(self, window_spec: dict[str, Any]) -> list[str]:
        """Extract device sources from window specification.

        Args:
            window_spec: DSL window specification.

        Returns:
            List of device sources referenced in the spec.
        """
        sources = set()

        def extract_from_dict(obj: dict[str, Any]) -> None:
            for key, value in obj.items():
                if key in ("source", "x_source", "y_source") and isinstance(value, str):
                    if "." in value:
                        device_name = value.split(".")[0]
                        sources.add(device_name)
                elif isinstance(value, dict):
                    extract_from_dict(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            extract_from_dict(item)

        extract_from_dict(window_spec)
        return list(sources)


# Session manager for auto-save and restoration
class SessionManager:
    """Manages session persistence and auto-save functionality."""

    def __init__(self, session: Session, auto_save_interval: float = 60.0) -> None:
        """Initialize session manager.

        Args:
            session: Active LabPilot session.
            auto_save_interval: Auto-save interval in seconds.
        """
        self.session = session
        self.auto_save_interval = auto_save_interval
        self.current_config: SessionConfig | None = None
        self.config_path: Path | None = None
        self._auto_save_task: Any | None = None  # asyncio.Task

    async def load_session(self, config_path: str | Path) -> None:
        """Load session configuration and restore state.

        Args:
            config_path: Path to session configuration file.
        """
        self.config_path = Path(config_path)
        self.current_config = SessionConfig.load(self.config_path)

        # Restore devices
        for device_config in self.current_config.devices:
            try:
                await self.session.connect_device(
                    device_config.name,
                    device_config.adapter,
                    device_config.config
                )
            except Exception as e:
                # Log error but continue with other devices
                print(f"Failed to restore device {device_config.name}: {e}")

        # Restore workflows (implementation depends on workflow system)
        # TODO: Implement workflow restoration

        # Restore Qt panels (implementation depends on Qt system)
        # TODO: Implement panel restoration

    async def save_session(self, config_path: str | Path | None = None) -> None:
        """Save current session state.

        Args:
            config_path: Optional path to save to (uses current path if None).
        """
        if config_path:
            self.config_path = Path(config_path)

        if self.config_path is None:
            raise ValueError("No config path specified")

        # Create config from current session state
        if self.current_config is None:
            self.current_config = SessionConfig.create_default()

        # Update config with current state
        await self._update_config_from_session()

        # Save to file
        self.current_config.save(self.config_path)

    async def start_auto_save(self) -> None:
        """Start auto-save background task."""
        import asyncio

        async def auto_save_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(self.auto_save_interval)
                    if self.config_path:
                        await self.save_session()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"Auto-save error: {e}")

        self._auto_save_task = asyncio.create_task(auto_save_loop())

    def stop_auto_save(self) -> None:
        """Stop auto-save background task."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None

    async def _update_config_from_session(self) -> None:
        """Update config object from current session state."""
        if self.current_config is None:
            return

        # Update devices
        self.current_config.devices.clear()
        # TODO: Get devices from session.device_registry

        # Update workflows
        self.current_config.workflows.clear()
        # TODO: Get workflows from session.workflow_store

        # Update panels
        self.current_config.open_panels.clear()
        # TODO: Get open panels from Qt bridge
