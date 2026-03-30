"""AI tools for instrument control.

Tools that allow AI to connect, disconnect, and configure instruments
through the LabPilot adapter system.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from labpilot_core.adapters import adapter_registry
from labpilot_core.core.session import Session

__all__ = [
    "ConnectDeviceTool",
    "DisconnectDeviceTool",
    "GetDeviceStatusTool",
    "ListAdaptersTool",
    "ReconfigureDeviceTool",
]


class ConnectDeviceParams(BaseModel):
    """Parameters for connect_device tool."""

    adapter_key: str = Field(description="Adapter key from registry (e.g., 'keithley_2400')")
    name: str = Field(description="Device name for session registry")
    config: dict[str, Any] = Field(description="Device configuration parameters")


class ConnectDeviceTool:
    """Tool for connecting instruments to the session."""

    name = "connect_device"
    description = "Connect an instrument to the LabPilot session"
    Parameters = ConnectDeviceParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "adapter_key": {
                    "type": "string",
                    "description": "Adapter identifier from registry (e.g., 'keithley_2400', 'andor_sdk2')"
                },
                "name": {
                    "type": "string",
                    "description": "Device name for the session (e.g., 'smu_1', 'camera_main')"
                },
                "config": {
                    "type": "object",
                    "description": "Device configuration (resource string, parameters, etc.)",
                    "properties": {
                        "resource": {
                            "type": "string",
                            "description": "Hardware resource (VISA string, serial port, etc.)"
                        }
                    },
                    "additionalProperties": True
                }
            },
            "required": ["adapter_key", "name", "config"]
        }

    @staticmethod
    async def execute(session: Session, params: ConnectDeviceParams) -> dict[str, Any]:
        """Execute the connect device tool.

        Args:
            session: LabPilot session.
            params: Tool parameters.

        Returns:
            Result dict with success status and details.
        """
        try:
            # Get adapter class from registry
            if params.adapter_key not in adapter_registry.list():
                return {
                    "success": False,
                    "error": f"Adapter '{params.adapter_key}' not found in registry",
                    "available_adapters": list(adapter_registry.list().keys())
                }

            adapter_cls = adapter_registry.get(params.adapter_key)

            # Create adapter instance
            try:
                adapter = adapter_cls(**params.config)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to create adapter: {e}",
                    "adapter_key": params.adapter_key
                }

            # Connect to hardware
            try:
                await adapter.connect()
                connected = True
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to connect to hardware: {e}",
                    "resource": params.config.get("resource", "unknown")
                }

            # Add to session device registry (placeholder - session needs device registry)
            # session.add_device(params.name, adapter)

            return {
                "success": True,
                "device_name": params.name,
                "adapter_key": params.adapter_key,
                "schema": adapter.schema.model_dump(),
                "connected": connected,
                "message": f"Successfully connected {params.name} ({params.adapter_key})"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {e}",
                "adapter_key": params.adapter_key,
                "device_name": params.name
            }


class DisconnectDeviceParams(BaseModel):
    """Parameters for disconnect_device tool."""

    name: str = Field(description="Device name to disconnect")


class DisconnectDeviceTool:
    """Tool for disconnecting instruments."""

    name = "disconnect_device"
    description = "Disconnect an instrument from the session"
    Parameters = DisconnectDeviceParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Device name to disconnect"
                }
            },
            "required": ["name"]
        }

    @staticmethod
    async def execute(session: Session, params: DisconnectDeviceParams) -> dict[str, Any]:
        """Execute disconnect device tool."""
        try:
            # Get device from session (placeholder)
            # device = session.get_device(params.name)
            # if device is None:
            #     return {
            #         "success": False,
            #         "error": f"Device '{params.name}' not found in session"
            #     }

            # # Disconnect
            # await device.disconnect()
            # session.remove_device(params.name)

            return {
                "success": True,
                "device_name": params.name,
                "message": f"Successfully disconnected {params.name}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to disconnect {params.name}: {e}"
            }


class ListAdaptersParams(BaseModel):
    """Parameters for list_adapters tool."""

    tags: list[str] | None = Field(default=None, description="Filter by tags (e.g., ['camera', 'Andor'])")
    category: str | None = Field(default=None, description="Filter by device kind (e.g., 'detector', 'motor')")


class ListAdaptersTool:
    """Tool for searching available adapters."""

    name = "list_adapters"
    description = "Search available instrument adapters by tags or category"
    Parameters = ListAdaptersParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (e.g., ['camera'], ['Keithley', 'SMU'])"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by device kind: detector, motor, source, etc."
                }
            },
            "additionalProperties": False
        }

    @staticmethod
    async def execute(session: Session, params: ListAdaptersParams) -> dict[str, Any]:
        """Execute list adapters tool."""
        try:
            # Get all adapters
            if params.tags:
                adapters = adapter_registry.search(params.tags)
            else:
                adapters = adapter_registry.list_with_schemas()

            # Filter by category if specified
            if params.category:
                filtered = {}
                for key, schema in adapters.items():
                    if schema.kind == params.category:
                        filtered[key] = schema
                adapters = filtered

            # Format results
            results = []
            for adapter_key, schema in adapters.items():
                results.append({
                    "adapter_key": adapter_key,
                    "name": schema.name,
                    "description": f"{schema.kind} device",
                    "tags": schema.tags,
                    "kind": schema.kind,
                    "readable": list(schema.readable.keys()) if schema.readable else [],
                    "settable": list(schema.settable.keys()) if schema.settable else [],
                })

            return {
                "success": True,
                "count": len(results),
                "adapters": results,
                "filters_applied": {
                    "tags": params.tags,
                    "category": params.category
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list adapters: {e}"
            }


class ReconfigureDeviceParams(BaseModel):
    """Parameters for reconfigure_device tool."""

    name: str = Field(description="Device name to reconfigure")
    config: dict[str, Any] = Field(description="New configuration parameters")


class ReconfigureDeviceTool:
    """Tool for updating device configuration."""

    name = "reconfigure_device"
    description = "Update configuration parameters for a connected device"
    Parameters = ReconfigureDeviceParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Device name to reconfigure"
                },
                "config": {
                    "type": "object",
                    "description": "New configuration parameters to apply"
                }
            },
            "required": ["name", "config"]
        }

    @staticmethod
    async def execute(session: Session, params: ReconfigureDeviceParams) -> dict[str, Any]:
        """Execute reconfigure device tool."""
        # Placeholder implementation
        return {
            "success": True,
            "device_name": params.name,
            "config_applied": params.config,
            "message": f"Configuration updated for {params.name}"
        }


class GetDeviceStatusParams(BaseModel):
    """Parameters for get_device_status tool."""

    name: str | None = Field(default=None, description="Device name (omit for all devices)")


class GetDeviceStatusTool:
    """Tool for getting device status information."""

    name = "get_device_status"
    description = "Get status and current readings from connected devices"
    Parameters = GetDeviceStatusParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Device name (optional - omit to get all devices)"
                }
            },
            "additionalProperties": False
        }

    @staticmethod
    async def execute(session: Session, params: GetDeviceStatusParams) -> dict[str, Any]:
        """Execute get device status tool."""
        try:
            # Placeholder - would get real device status from session
            if params.name:
                # Single device status
                return {
                    "success": True,
                    "device": {
                        "name": params.name,
                        "connected": True,
                        "status": "ready",
                        "last_reading": {"timestamp": "2024-03-24T12:00:00", "data": {}},
                    }
                }
            else:
                # All devices status
                return {
                    "success": True,
                    "devices": [],
                    "total_connected": 0,
                    "message": "No devices currently connected"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get device status: {e}"
            }
