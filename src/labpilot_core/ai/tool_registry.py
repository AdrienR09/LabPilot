"""AI tool registry for LabPilot.

Manages registration, discovery, and execution of AI tools.
Provides function calling interface for AI providers with automatic
JSON schema generation and parameter validation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from labpilot_core.ai.tools.instrument_tools import (
    ConnectDeviceTool,
    DisconnectDeviceTool,
    GetDeviceStatusTool,
    ListAdaptersTool,
    ReconfigureDeviceTool,
)
from labpilot_core.ai.tools.workflow_generation import (
    GenerateWorkflowTool,
    GetWorkflowTemplateTool,
    ListWorkflowTemplatesTool,
    # NEW: Direct Python code generation tools
    GenerateWorkflowCodeTool,
    SaveWorkflowCodeTool,
    ShowWorkflowCodeTool,
)
from labpilot_core.ai.tools.workflow_tools import (
    AddNodeTool,
    ConnectNodesTool,
    CreateWorkflowTool,
    EditNodeTool,
    GetWorkflowTool,
    ListWorkflowsTool,
    RemoveNodeTool,
    SetAnalysisCodeTool,
    StartWorkflowTool,
    StopWorkflowTool,
)
from labpilot_core.core.session import Session

__all__ = ["AITool", "ToolExecutionError", "ToolRegistry"]


class AITool(BaseModel):
    """AI tool metadata and executor."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    tool_class: type

    class Config:
        arbitrary_types_allowed = True


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""


class ToolRegistry:
    """Registry for AI tools with function calling support.

    Features:
    - Automatic tool discovery and registration
    - JSON schema generation for AI function calling
    - Parameter validation and type conversion
    - Session-aware tool execution
    - Error handling with user-friendly messages

    Usage:
        registry = ToolRegistry(session)
        tools = registry.get_function_schemas()  # For AI provider
        result = await registry.execute_tool("connect_device", {"name": "laser"})
    """

    def __init__(self, session: Session):
        """Initialize tool registry.

        Args:
            session: LabPilot session for device and workflow access.
        """
        self.session = session
        self._tools: dict[str, AITool] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        """Register all built-in LabPilot tools."""
        # Instrument tools
        instrument_tools = [
            ListAdaptersTool,
            ConnectDeviceTool,
            DisconnectDeviceTool,
            GetDeviceStatusTool,
            ReconfigureDeviceTool,
        ]

        # Workflow tools
        workflow_tools = [
            CreateWorkflowTool,
            AddNodeTool,
            EditNodeTool,
            ConnectNodesTool,
            RemoveNodeTool,
            SetAnalysisCodeTool,
            StartWorkflowTool,
            StopWorkflowTool,
            GetWorkflowTool,
            ListWorkflowsTool,
            # Template-based workflow generation tools
            GenerateWorkflowTool,
            ListWorkflowTemplatesTool,
            GetWorkflowTemplateTool,
            # NEW: Direct Python code generation tools
            GenerateWorkflowCodeTool,
            SaveWorkflowCodeTool,
            ShowWorkflowCodeTool,
        ]

        # Register all tools
        for tool_class in instrument_tools + workflow_tools:
            self.register_tool(tool_class)

    def register_tool(self, tool_class: type) -> None:
        """Register a tool class.

        Args:
            tool_class: Tool class with name, description, and execute method.
        """
        # Get tool metadata
        name = tool_class.name
        description = tool_class.description

        # Generate JSON schema from parameter model
        if hasattr(tool_class, 'Parameters'):
            schema = tool_class.Parameters.model_json_schema()
            # Convert to function calling format
            parameters_schema = {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        else:
            parameters_schema = {"type": "object", "properties": {}}

        # Register tool
        self._tools[name] = AITool(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            tool_class=tool_class,
        )

    def get_function_schemas(self) -> list[dict[str, Any]]:
        """Get function schemas for AI provider function calling.

        Returns:
            List of function schemas in OpenAI function calling format.
        """
        schemas = []
        for tool in self._tools.values():
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                }
            }
            schemas.append(schema)

        return schemas

    async def execute_tool(self, name: str, parameters: dict[str, Any]) -> Any:
        """Execute a registered tool.

        Args:
            name: Tool name.
            parameters: Tool parameters dict.

        Returns:
            Tool execution result.

        Raises:
            ToolExecutionError: If tool not found or execution fails.
        """
        if name not in self._tools:
            available = ", ".join(self._tools.keys())
            raise ToolExecutionError(f"Tool '{name}' not found. Available: {available}")

        tool_info = self._tools[name]

        try:
            # Validate and construct parameters object if tool has parameter model
            if hasattr(tool_info.tool_class, 'Parameters'):
                validated_params = tool_info.tool_class.Parameters(**parameters)
            else:
                # No parameters expected
                validated_params = None

            # Execute tool (uses static method, no instantiation needed)
            if validated_params is not None:
                result = await tool_info.tool_class.execute(self.session, validated_params)
            else:
                result = await tool_info.tool_class.execute(self.session, None)

            return result

        except Exception as e:
            raise ToolExecutionError(f"Tool '{name}' execution failed: {e}")

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names.
        """
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> AITool | None:
        """Get tool information.

        Args:
            name: Tool name.

        Returns:
            AITool instance or None if not found.
        """
        return self._tools.get(name)

    def get_tools_by_category(self) -> dict[str, list[str]]:
        """Group tools by category.

        Returns:
            Dict mapping category to list of tool names.
        """
        categories = {}

        for name, tool in self._tools.items():
            # Determine category from tool name prefix
            if name.startswith(('list_adapters', 'connect_', 'disconnect_', 'get_device', 'reconfigure_')):
                category = "instruments"
            elif name.startswith(('create_workflow', 'add_node', 'edit_node', 'connect_nodes', 'remove_node', 'set_analysis', 'start_workflow', 'stop_workflow', 'get_workflow', 'list_workflows')):
                category = "workflows"
            else:
                category = "other"

            if category not in categories:
                categories[category] = []
            categories[category].append(name)

        return categories
