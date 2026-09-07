"""Workflow records: what a workflow *is*, as opposed to how it runs.

A workflow is a Python module exposing `async def run(session) -> dict`,
plus two rows: its parameters and its role -> instrument bindings.
`WorkflowGraph` is that record — id, name, metadata — not an execution
model; the node interpreter that once read it was removed because it never
worked (Branch always took the true edge, Set never wrote to hardware,
Loop never ran its body).

Running one is `core/run/manager.py`'s `RunManager`, which lives with
`Run` and the plans rather than here: what executes is a run, and a
workflow is one of the things that can start one. It is deliberately not
re-exported from this package — `RunManager` reads a workflow's declared
roles, so importing it from here would make the record package and the
execution package import each other.

Key components:
- WorkflowGraph: the stored record for one workflow
- WorkflowStore: append-only SQLite storage with version history
"""

from labpilot.core.workflow.graph import WorkflowEdge, WorkflowGraph
from labpilot.core.workflow.store import WorkflowStore, WorkflowSummary, WorkflowVersion

__all__ = [
    "WorkflowEdge",
    "WorkflowGraph",
    "WorkflowStore",
    "WorkflowSummary",
    "WorkflowVersion",
]
