"""AI tools for workflow manipulation.

Tools that allow AI to create, modify, and execute experiment workflows
through the LabPilot workflow system.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from labpilot_core.core.session import Session
from labpilot_core.workflow import (
    WorkflowGraph,
    create_node,
)
from labpilot_core.workflow.engine import WorkflowEngine
from labpilot_core.workflow.store import WorkflowStore

__all__ = [
    "AddNodeTool",
    "ConnectNodesTool",
    "CreateWorkflowTool",
    "EditNodeTool",
    "GetWorkflowTool",
    "ListWorkflowsTool",
    "RemoveNodeTool",
    "SetAnalysisCodeTool",
    "StartWorkflowTool",
    "StopWorkflowTool",
]


class CreateWorkflowParams(BaseModel):
    """Parameters for create_workflow tool."""

    name: str = Field(description="Workflow name")
    description: str = Field(default="", description="Optional workflow description")


class CreateWorkflowTool:
    """Tool for creating new workflows."""

    name = "create_workflow"
    description = "Create a new empty workflow"
    Parameters = CreateWorkflowParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the new workflow"
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the workflow's purpose"
                }
            },
            "required": ["name"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: CreateWorkflowParams
    ) -> dict[str, Any]:
        """Execute create workflow tool."""
        try:
            # Create new workflow graph
            graph = WorkflowGraph(name=params.name)
            if params.description:
                graph.metadata["description"] = params.description

            # Save to store
            version = workflow_store.save(graph, "Initial creation")

            return {
                "success": True,
                "workflow_id": graph.id,
                "name": graph.name,
                "version": version,
                "message": f"Created workflow '{params.name}' (ID: {graph.id[:8]}...)"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create workflow: {e}"
            }


class AddNodeParams(BaseModel):
    """Parameters for add_node tool."""

    workflow_id: str = Field(description="Workflow ID to add node to")
    node_type: str = Field(description="Node type: acquire, analyse, branch, loop, optimise, set, wait, notify")
    name: str = Field(description="Human-readable node name")
    parameters: dict[str, Any] = Field(description="Node-specific parameters")


class AddNodeTool:
    """Tool for adding nodes to workflows."""

    name = "add_node"
    description = "Add a node to a workflow"
    Parameters = AddNodeParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "ID of workflow to add node to"
                },
                "node_type": {
                    "type": "string",
                    "enum": ["acquire", "analyse", "branch", "loop", "optimise", "set", "wait", "notify"],
                    "description": "Type of node to add"
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the node"
                },
                "parameters": {
                    "type": "object",
                    "description": "Node-specific parameters (device, code, conditions, etc.)"
                }
            },
            "required": ["workflow_id", "node_type", "name", "parameters"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: AddNodeParams
    ) -> dict[str, Any]:
        """Execute add node tool."""
        try:
            # Load workflow
            graph = workflow_store.load(params.workflow_id)

            # Create node data
            node_data = {
                "name": params.name,
                "kind": params.node_type,
                **params.parameters
            }

            # Create and validate node
            node = create_node(node_data)

            # Add to graph
            graph.add_node(node.model_dump())

            # Save updated workflow
            version = workflow_store.save(graph, f"Added {params.node_type} node: {params.name}")

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "node_id": node.id,
                "node_type": params.node_type,
                "node_name": params.name,
                "version": version,
                "message": f"Added {params.node_type} node '{params.name}' to workflow"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to add node: {e}",
                "workflow_id": params.workflow_id
            }


class EditNodeParams(BaseModel):
    """Parameters for edit_node tool."""

    workflow_id: str = Field(description="Workflow ID")
    node_id: str = Field(description="Node ID to edit")
    updates: dict[str, Any] = Field(description="Updates to apply to the node")


class EditNodeTool:
    """Tool for editing existing nodes."""

    name = "edit_node"
    description = "Edit parameters of an existing workflow node"
    Parameters = EditNodeParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow ID containing the node"
                },
                "node_id": {
                    "type": "string",
                    "description": "ID of node to edit"
                },
                "updates": {
                    "type": "object",
                    "description": "Parameters to update on the node"
                }
            },
            "required": ["workflow_id", "node_id", "updates"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: EditNodeParams
    ) -> dict[str, Any]:
        """Execute edit node tool."""
        try:
            # Load workflow
            graph = workflow_store.load(params.workflow_id)

            # Get node
            if params.node_id not in graph.nodes:
                return {
                    "success": False,
                    "error": f"Node '{params.node_id}' not found in workflow",
                    "available_nodes": list(graph.nodes.keys())
                }

            # Update node data
            node_data = graph.nodes[params.node_id].copy()
            node_data.update(params.updates)

            # Validate updated node
            node = create_node(node_data)
            graph.nodes[params.node_id] = node.model_dump()

            # Save workflow
            version = workflow_store.save(graph, f"Edited node: {params.node_id}")

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "node_id": params.node_id,
                "updates_applied": params.updates,
                "version": version,
                "message": f"Updated node {params.node_id}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to edit node: {e}",
                "workflow_id": params.workflow_id,
                "node_id": params.node_id
            }


class ConnectNodesParams(BaseModel):
    """Parameters for connect_nodes tool."""

    workflow_id: str = Field(description="Workflow ID")
    from_node: str = Field(description="Source node ID")
    to_node: str = Field(description="Destination node ID")
    label: str = Field(default="", description="Optional edge label")


class ConnectNodesTool:
    """Tool for connecting nodes with edges."""

    name = "connect_nodes"
    description = "Create a directed edge between two nodes in a workflow"
    Parameters = ConnectNodesParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow ID"
                },
                "from_node": {
                    "type": "string",
                    "description": "Source node ID"
                },
                "to_node": {
                    "type": "string",
                    "description": "Destination node ID"
                },
                "label": {
                    "type": "string",
                    "description": "Optional edge label"
                }
            },
            "required": ["workflow_id", "from_node", "to_node"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: ConnectNodesParams
    ) -> dict[str, Any]:
        """Execute connect nodes tool."""
        try:
            # Load workflow
            graph = workflow_store.load(params.workflow_id)

            # Connect nodes
            graph.connect(params.from_node, params.to_node, params.label)

            # Save workflow
            version = workflow_store.save(graph, f"Connected {params.from_node} → {params.to_node}")

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "edge": f"{params.from_node} → {params.to_node}",
                "label": params.label,
                "version": version,
                "message": f"Connected {params.from_node} to {params.to_node}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to connect nodes: {e}",
                "workflow_id": params.workflow_id
            }


class RemoveNodeParams(BaseModel):
    """Parameters for remove_node tool."""

    workflow_id: str = Field(description="Workflow ID")
    node_id: str = Field(description="Node ID to remove")


class RemoveNodeTool:
    """Tool for removing nodes from workflows."""

    name = "remove_node"
    description = "Remove a node and its connections from a workflow"
    Parameters = RemoveNodeParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow ID"
                },
                "node_id": {
                    "type": "string",
                    "description": "ID of node to remove"
                }
            },
            "required": ["workflow_id", "node_id"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: RemoveNodeParams
    ) -> dict[str, Any]:
        """Execute remove node tool."""
        try:
            # Load workflow
            graph = workflow_store.load(params.workflow_id)

            # Remove node (also removes connected edges)
            graph.remove_node(params.node_id)

            # Save workflow
            version = workflow_store.save(graph, f"Removed node: {params.node_id}")

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "removed_node": params.node_id,
                "version": version,
                "message": f"Removed node {params.node_id} from workflow"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to remove node: {e}",
                "workflow_id": params.workflow_id
            }


class SetAnalysisCodeParams(BaseModel):
    """Parameters for set_analysis_code tool."""

    workflow_id: str = Field(description="Workflow ID")
    node_id: str = Field(description="AnalyseNode ID")
    code: str = Field(description="Python analysis code")


class SetAnalysisCodeTool:
    """Tool for setting Python code on AnalyseNodes."""

    name = "set_analysis_code"
    description = "Set Python analysis code for an AnalyseNode"
    Parameters = SetAnalysisCodeParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow ID"
                },
                "node_id": {
                    "type": "string",
                    "description": "AnalyseNode ID to update"
                },
                "code": {
                    "type": "string",
                    "description": "Python code defining analyse(data, params) -> dict function"
                }
            },
            "required": ["workflow_id", "node_id", "code"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: SetAnalysisCodeParams
    ) -> dict[str, Any]:
        """Execute set analysis code tool."""
        try:
            # Load workflow
            graph = workflow_store.load(params.workflow_id)

            # Get node and verify it's an AnalyseNode
            if params.node_id not in graph.nodes:
                return {
                    "success": False,
                    "error": f"Node '{params.node_id}' not found"
                }

            node_data = graph.nodes[params.node_id]
            if node_data.get("kind") != "analyse":
                return {
                    "success": False,
                    "error": f"Node '{params.node_id}' is not an AnalyseNode"
                }

            # Update code
            node_data["code"] = params.code

            # Validate updated node
            node = create_node(node_data)
            graph.nodes[params.node_id] = node.model_dump()

            # Save workflow
            version = workflow_store.save(graph, f"Updated analysis code for {params.node_id}")

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "node_id": params.node_id,
                "code_lines": len(params.code.split('\n')),
                "version": version,
                "message": f"Updated analysis code for {params.node_id}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to set analysis code: {e}",
                "workflow_id": params.workflow_id
            }


class StartWorkflowParams(BaseModel):
    """Parameters for start_workflow tool."""

    workflow_id: str = Field(description="Workflow ID to start")


class StartWorkflowTool:
    """Tool for starting workflow execution."""

    name = "start_workflow"
    description = "Start executing a workflow"
    Parameters = StartWorkflowParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "ID of workflow to start"
                }
            },
            "required": ["workflow_id"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_engine: WorkflowEngine,
        params: StartWorkflowParams
    ) -> dict[str, Any]:
        """Execute start workflow tool."""
        try:
            # Start workflow execution
            execution_id = await workflow_engine.start_workflow(params.workflow_id)

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "execution_id": execution_id,
                "message": f"Started workflow {params.workflow_id}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to start workflow: {e}",
                "workflow_id": params.workflow_id
            }


class StopWorkflowParams(BaseModel):
    """Parameters for stop_workflow tool."""

    workflow_id: str = Field(description="Workflow ID to stop")


class StopWorkflowTool:
    """Tool for stopping workflow execution."""

    name = "stop_workflow"
    description = "Stop a running workflow"
    Parameters = StopWorkflowParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "ID of workflow to stop"
                }
            },
            "required": ["workflow_id"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_engine: WorkflowEngine,
        params: StopWorkflowParams
    ) -> dict[str, Any]:
        """Execute stop workflow tool."""
        try:
            await workflow_engine.stop_workflow(params.workflow_id)

            return {
                "success": True,
                "workflow_id": params.workflow_id,
                "message": f"Stopped workflow {params.workflow_id}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to stop workflow: {e}",
                "workflow_id": params.workflow_id
            }


class GetWorkflowParams(BaseModel):
    """Parameters for get_workflow tool."""

    workflow_id: str = Field(description="Workflow ID to retrieve")
    include_json: bool = Field(default=False, description="Include full workflow JSON")


class GetWorkflowTool:
    """Tool for retrieving workflow information."""

    name = "get_workflow"
    description = "Get information about a specific workflow"
    Parameters = GetWorkflowParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow ID to retrieve"
                },
                "include_json": {
                    "type": "boolean",
                    "description": "Whether to include full workflow JSON"
                }
            },
            "required": ["workflow_id"]
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: GetWorkflowParams
    ) -> dict[str, Any]:
        """Execute get workflow tool."""
        try:
            # Load workflow
            graph = workflow_store.load(params.workflow_id)

            result = {
                "success": True,
                "workflow_id": graph.id,
                "name": graph.name,
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "created_at": graph.created_at,
                "metadata": graph.metadata,
                "nodes": [
                    {
                        "id": node_id,
                        "name": node_data.get("name", ""),
                        "kind": node_data.get("kind", ""),
                    }
                    for node_id, node_data in graph.nodes.items()
                ],
                "edges": [
                    {"from": edge.from_node, "to": edge.to_node, "label": edge.label}
                    for edge in graph.edges
                ]
            }

            if params.include_json:
                result["workflow_json"] = graph.to_json()

            return result

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get workflow: {e}",
                "workflow_id": params.workflow_id
            }


class ListWorkflowsParams(BaseModel):
    """Parameters for list_workflows tool."""

    limit: int = Field(default=20, description="Maximum number of workflows to return")


class ListWorkflowsTool:
    """Tool for listing available workflows."""

    name = "list_workflows"
    description = "List all available workflows in the library"
    Parameters = ListWorkflowsParams

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of workflows to return",
                    "default": 20
                }
            }
        }

    @staticmethod
    async def execute(
        session: Session,
        workflow_store: WorkflowStore,
        params: ListWorkflowsParams
    ) -> dict[str, Any]:
        """Execute list workflows tool."""
        try:
            # Get workflow summaries
            workflows = workflow_store.list_all()[:params.limit]

            return {
                "success": True,
                "count": len(workflows),
                "workflows": [
                    {
                        "id": wf.id,
                        "name": wf.name,
                        "version": wf.current_version,
                        "created_at": wf.created_at,
                        "updated_at": wf.updated_at,
                    }
                    for wf in workflows
                ]
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list workflows: {e}"
            }
