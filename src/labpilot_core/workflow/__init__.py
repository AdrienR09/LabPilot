"""LabPilot Workflow Engine.

Provides workflow graph models, execution engine, and code sandbox for
experiment automation and AI-assisted workflow creation.

Key components:
- WorkflowGraph: DAG model with nodes and edges
- WorkflowNode types: Acquire, Analyse, Branch, Loop, Optimise, Set, Wait, Notify
- WorkflowEngine: Async executor with checkpointing
- CodeSandbox: Restricted Python execution for AnalyseNodes
- WorkflowStore: Append-only SQLite storage
"""

from labpilot_core.workflow.code_sandbox import (
    CodeSandbox,
    SandboxError,
    execute_analysis_code,
)
from labpilot_core.workflow.engine import WorkflowEngine, WorkflowExecutionError
from labpilot_core.workflow.graph import WorkflowEdge, WorkflowGraph
from labpilot_core.workflow.nodes import (
    AcquireNode,
    AnalyseNode,
    BranchNode,
    LoopNode,
    NodeStatus,
    NotifyNode,
    OptimiseNode,
    SetNode,
    WaitNode,
    WorkflowNode,
    create_node,
)
from labpilot_core.workflow.store import WorkflowStore, WorkflowSummary, WorkflowVersion

__all__ = [
    # Core graph components
    "WorkflowGraph",
    "WorkflowEdge",
    # Node types
    "WorkflowNode",
    "AcquireNode",
    "AnalyseNode",
    "BranchNode",
    "LoopNode",
    "OptimiseNode",
    "SetNode",
    "WaitNode",
    "NotifyNode",
    "NodeStatus",
    "create_node",
    # Execution components
    "WorkflowEngine",
    "WorkflowExecutionError",
    "CodeSandbox",
    "SandboxError",
    "execute_analysis_code",
    # Storage components
    "WorkflowStore",
    "WorkflowSummary",
    "WorkflowVersion",
]
