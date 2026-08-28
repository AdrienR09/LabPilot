"""AI tool registry for LabPilot.

Manages registration, discovery, and execution of AI tools.
Provides function calling interface for AI providers with automatic
JSON schema generation and parameter validation.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from core.ai.tools.instrument_tools import (
    ConnectDeviceTool,
    DisconnectDeviceTool,
    GetDeviceStatusTool,
    ListAdaptersTool,
    ReconfigureDeviceTool,
)
from core.ai.tools.workflow_tools import (
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
    WriteWorkflowScriptTool,
)
from core.session import Session

# TYPE_CHECKING-only: core.config (which core.workflow_sets lives under)
# imports core.ai.ai_session at module level, and this module is imported
# by ai_session.py — a real, module-level import here would be a circular
# import. Only ever used as a type hint / for `getattr(self, dep_name)`
# below (never instantiated in this file), so this is safe.
if TYPE_CHECKING:
    from core.config.workflow_sets import WorkflowSetPersistence
    from core.workflow.engine import WorkflowEngine
    from core.workflow.store import WorkflowStore

__all__ = ["AITool", "ToolExecutionError", "ToolRegistry"]

# Extra dependencies (beyond `session` and the validated params) that some
# tools' execute() need, by declared parameter name — see execute_tool()
# below. Only workflow_tools.py's tools use these today; instrument_tools.py
# tools only ever take (session, params).
_DEP_PARAM_NAMES = ("workflow_store", "workflow_engine", "workflow_set_store")


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

    def __init__(
        self,
        session: Session,
        workflow_store: WorkflowStore | None = None,
        workflow_engine: WorkflowEngine | None = None,
        workflow_set_store: WorkflowSetPersistence | None = None,
    ):
        """Initialize tool registry.

        Args:
            session: LabPilot session for device and workflow access.
            workflow_store: Needed by most workflow_tools.py tools
                (create/add_node/edit_node/.../get/list). None disables
                those tools' actual dependency but they'll still register —
                calling one without a store raises a clear error at
                execute_tool() time rather than at import time.
            workflow_engine: Needed by StartWorkflowTool/StopWorkflowTool.
            workflow_set_store: Needed by CreateWorkflowTool/
                WriteWorkflowScriptTool to register a new workflow as
                "loaded" (see WorkflowSetPersistence.add_to_active) —
                otherwise an AI-created workflow would save fine but never
                show up in the Workflows tab.
        """
        self.session = session
        self.workflow_store = workflow_store
        self.workflow_engine = workflow_engine
        self.workflow_set_store = workflow_set_store
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

        # Workflow tools — operate on the real WorkflowGraph/WorkflowStore/
        # WorkflowEngine (core/workflow/). A separate, disconnected
        # template-matching "workflow generation" tool set used to be
        # registered here too (GenerateWorkflowTool and friends in
        # core/ai/tools/workflow_generation.py) — it saved code to a
        # directory nothing else ever read and was never wired to
        # WorkflowStore/the Workflows tab, so it's been retired rather than
        # kept alongside the real system.
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
            WriteWorkflowScriptTool,
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

            # Most tools are execute(session, params) — but workflow_tools.py's
            # need an extra dependency (workflow_store or workflow_engine)
            # threaded in between, per their declared parameter name. Built
            # from the real signature rather than hardcoding which tools need
            # which, so a new tool just declaring `workflow_store: WorkflowStore`
            # in its execute() gets it automatically.
            sig_params = list(inspect.signature(tool_info.tool_class.execute).parameters)
            call_args: list[Any] = [self.session]
            for dep_name in _DEP_PARAM_NAMES:
                if dep_name in sig_params:
                    dep = getattr(self, dep_name)
                    if dep is None:
                        raise ToolExecutionError(
                            f"Tool '{name}' requires {dep_name}, which isn't available "
                            f"(ToolRegistry was constructed without one)"
                        )
                    call_args.append(dep)
            call_args.append(validated_params)

            result = await tool_info.tool_class.execute(*call_args)
            return result

        except ToolExecutionError:
            raise
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
