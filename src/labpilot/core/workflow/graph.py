"""Workflow graph model for LabPilot.

Pydantic v2 models for representing experiment workflows as directed acyclic graphs (DAGs).
Fully serializable to/from JSON for persistence and AI manipulation.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["WorkflowEdge", "WorkflowGraph"]


class WorkflowEdge(BaseModel):
    """Directed edge connecting two workflow nodes.

    Represents data flow from one node to another. The output dictionary from
    the source node is passed as input to the destination node.
    """

    from_node: str = Field(description="Source node ID")
    to_node: str = Field(description="Destination node ID")
    label: str = Field(default="", description="Optional edge label")

    class Config:
        """Pydantic v2 configuration."""

        frozen = True  # Edges are immutable once created


class WorkflowGraph(BaseModel):
    """Workflow graph: nodes + edges with full JSON serialization.

    A workflow graph represents an experiment as a directed acyclic graph (DAG).
    Nodes are execution units (data acquisition, analysis, control flow).
    Edges represent data dependencies between nodes.

    The graph is fully serializable to JSON for:
    - Persistence (save/load workflows)
    - AI manipulation (Claude/Ollama can modify graphs via tools)
    - Version control (track workflow changes over time)

    Example:
        >>> graph = WorkflowGraph(name="PL scan")
        >>> graph.add_node(acquir_node)
        >>> graph.add_node(analysis_node)
        >>> graph.connect(acquire_node.id, analysis_node.id)
        >>> json_str = graph.to_json()
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="Human-readable workflow name")
    nodes: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Nodes keyed by ID. Values are node dicts (type-specific).",
    )
    edges: list[WorkflowEdge] = Field(
        default_factory=list, description="Directed edges between nodes"
    )
    created_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="User-defined metadata"
    )

    def add_node(self, node: dict[str, Any]) -> None:
        """Add a node to the graph.

        Args:
            node: Node dictionary with at minimum {"id": str, "kind": str}.
                  Full node structure depends on kind (see nodes.py).

        Raises:
            ValueError: If node ID already exists or node missing required fields.
        """
        if "id" not in node:
            raise ValueError("Node must have 'id' field")
        if "kind" not in node:
            raise ValueError("Node must have 'kind' field")

        node_id = node["id"]
        if node_id in self.nodes:
            raise ValueError(f"Node '{node_id}' already exists in graph")

        self.nodes[node_id] = node

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all connected edges.

        Args:
            node_id: ID of node to remove.

        Raises:
            KeyError: If node not found.
        """
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not found")

        # Remove node
        del self.nodes[node_id]

        # Remove all edges connected to this node
        self.edges = [
            edge
            for edge in self.edges
            if edge.from_node != node_id and edge.to_node != node_id
        ]

    def connect(self, from_id: str, to_id: str, label: str = "") -> None:
        """Create directed edge from one node to another.

        Args:
            from_id: Source node ID.
            to_id: Destination node ID.
            label: Optional edge label.

        Raises:
            KeyError: If either node not found.
            ValueError: If edge would create a cycle.
        """
        if from_id not in self.nodes:
            raise KeyError(f"Source node '{from_id}' not found")
        if to_id not in self.nodes:
            raise KeyError(f"Destination node '{to_id}' not found")

        # Check for existing edge
        if any(e.from_node == from_id and e.to_node == to_id for e in self.edges):
            raise ValueError(f"Edge {from_id} → {to_id} already exists")

        # Add edge
        edge = WorkflowEdge(from_node=from_id, to_node=to_id, label=label)
        self.edges.append(edge)

        # Verify no cycles (DAG requirement)
        if self._has_cycle():
            # Rollback - remove the edge we just added
            self.edges = [e for e in self.edges if e != edge]
            raise ValueError(f"Edge {from_id} → {to_id} would create a cycle")

    def disconnect(self, from_id: str, to_id: str) -> None:
        """Remove edge between two nodes.

        Args:
            from_id: Source node ID.
            to_id: Destination node ID.

        Raises:
            ValueError: If edge not found.
        """
        original_count = len(self.edges)
        self.edges = [
            e for e in self.edges if not (e.from_node == from_id and e.to_node == to_id)
        ]

        if len(self.edges) == original_count:
            raise ValueError(f"Edge {from_id} → {to_id} not found")

    def get_node(self, node_id: str) -> dict[str, Any]:
        """Get node by ID.

        Args:
            node_id: Node ID.

        Returns:
            Node dictionary.

        Raises:
            KeyError: If node not found.
        """
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not found")
        return self.nodes[node_id]

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order (dependencies first).

        Uses Kahn's algorithm for topological sorting.

        Returns:
            List of node IDs in execution order.

        Raises:
            ValueError: If graph has a cycle (should never happen if connect() is used).
        """
        # Build adjacency list and in-degree count
        in_degree = dict.fromkeys(self.nodes, 0)
        adjacency = {node_id: [] for node_id in self.nodes}

        for edge in self.edges:
            adjacency[edge.from_node].append(edge.to_node)
            in_degree[edge.to_node] += 1

        # Queue of nodes with no incoming edges
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        sorted_nodes = []

        while queue:
            # Pop node with no dependencies
            node_id = queue.pop(0)
            sorted_nodes.append(node_id)

            # Reduce in-degree for neighbors
            for neighbor in adjacency[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If not all nodes processed, graph has a cycle
        if len(sorted_nodes) != len(self.nodes):
            raise ValueError("Graph contains a cycle")

        return sorted_nodes

    def _has_cycle(self) -> bool:
        """Check if graph contains a cycle (DFS-based).

        Returns:
            True if cycle detected, False otherwise.
        """
        # Build adjacency list
        adjacency = {node_id: [] for node_id in self.nodes}
        for edge in self.edges:
            adjacency[edge.from_node].append(edge.to_node)

        # Track visit state: 0=unvisited, 1=visiting, 2=visited
        state = dict.fromkeys(self.nodes, 0)

        def visit(node_id: str) -> bool:
            """DFS visit. Returns True if cycle detected."""
            if state[node_id] == 1:
                # Currently visiting - cycle detected
                return True
            if state[node_id] == 2:
                # Already visited - no cycle from this node
                return False

            # Mark as visiting
            state[node_id] = 1

            # Visit neighbors
            for neighbor in adjacency[node_id]:
                if visit(neighbor):
                    return True

            # Mark as visited
            state[node_id] = 2
            return False

        # Check all nodes (graph might be disconnected)
        for node_id in self.nodes:
            if state[node_id] == 0:
                if visit(node_id):
                    return True

        return False

    def to_json(self) -> str:
        """Serialize graph to JSON string.

        Returns:
            JSON string representation.
        """
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> WorkflowGraph:
        """Deserialize graph from JSON string.

        Args:
            json_str: JSON string representation.

        Returns:
            WorkflowGraph instance.
        """
        return cls.model_validate_json(json_str)

    class Config:
        """Pydantic v2 configuration."""

        # Allow mutation (graphs are modified during creation/editing)
        frozen = False
        # Reject unknown fields
        extra = "forbid"
