"""LabPilot workflow engine.

A workflow is a Python module exposing `async def run(session) -> dict`.
`WorkflowGraph` is its persistence record — id, name, metadata, and the
role -> instrument bindings resolved at run time — not an execution model;
see engine.py for why the node interpreter that once read it was removed.

Key components:
- WorkflowGraph: the stored record for one workflow
- WorkflowEngine: runs a workflow's script and reports its lifecycle
- WorkflowStore: append-only SQLite storage with version history
"""

from labpilot.core.workflow.engine import WorkflowEngine, WorkflowExecutionError
from labpilot.core.workflow.graph import WorkflowEdge, WorkflowGraph
from labpilot.core.workflow.store import WorkflowStore, WorkflowSummary, WorkflowVersion

__all__ = [
    "WorkflowEdge",
    "WorkflowEngine",
    "WorkflowExecutionError",
    "WorkflowGraph",
    "WorkflowStore",
    "WorkflowSummary",
    "WorkflowVersion",
]
