"""Workflow node types for LabPilot.

Pydantic v2 models representing different types of workflow execution units.
Each node type has specific parameters and execution behavior.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "AcquireNode",
    "AnalyseNode",
    "BranchNode",
    "LoopNode",
    "NodeStatus",
    "NotifyNode",
    "OptimiseNode",
    "SetNode",
    "WaitNode",
    "WorkflowNode",
]


class NodeStatus(Enum):
    """Workflow node execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowNode(BaseModel):
    """Base workflow node with common fields.

    All workflow nodes inherit from this base class and add type-specific fields.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="Human-readable node name")
    kind: str = Field(description="Node type (acquire, analyse, branch, etc.)")
    status: NodeStatus = Field(default=NodeStatus.PENDING)
    device_refs: list[str] = Field(
        default_factory=list, description="Referenced device names"
    )
    result: dict[str, Any] | None = Field(
        default=None, description="Execution result data"
    )
    created_at: float = Field(default_factory=time.time)
    started_at: float | None = Field(default=None)
    completed_at: float | None = Field(default=None)
    error_message: str | None = Field(default=None)

    class Config:
        """Pydantic v2 configuration."""

        frozen = False  # Nodes can be modified during execution
        extra = "forbid"


class AcquireNode(WorkflowNode):
    """Data acquisition node.

    Executes a scan plan on a specified device and returns the acquired data.
    This is typically the starting point of measurement workflows.
    """

    kind: str = Field(default="acquire", frozen=True)
    device: str = Field(description="Device name from session registry")
    plan: dict[str, Any] = Field(description="ScanPlan parameters as dict")

    # Optional acquisition parameters
    num_points: int = Field(default=100, description="Number of data points")
    integration_time: float = Field(default=0.1, description="Integration time per point (s)")
    trigger_mode: str = Field(default="software", description="Triggering mode")

    def __init__(self, **data: Any) -> None:
        """Initialize acquire node."""
        super().__init__(**data)
        if self.device not in self.device_refs:
            self.device_refs.append(self.device)


class AnalyseNode(WorkflowNode):
    """Data analysis node.

    Executes user-provided Python code in a sandboxed environment.
    Takes input data from other nodes and returns analysis results.
    """

    kind: str = Field(default="analyse", frozen=True)
    code: str = Field(description="Python function code to execute")
    inputs: list[str] = Field(
        default_factory=list, description="Input node IDs whose results feed in"
    )
    allowed_imports: list[str] = Field(
        default_factory=lambda: ["numpy", "scipy", "xarray", "sklearn", "matplotlib"],
        description="Allowed Python imports for security",
    )
    timeout_s: float = Field(default=30.0, description="Execution timeout")

    # The code must define a function with this signature:
    # def analyse(data: xr.Dataset, params: dict) -> dict: ...


class BranchNode(WorkflowNode):
    """Conditional branching node.

    Evaluates a Python expression and chooses execution path based on result.
    Enables if/else logic in workflows.
    """

    kind: str = Field(default="branch", frozen=True)
    condition: str = Field(
        description="Python expression evaluated against input results"
    )
    true_branch: str = Field(description="Node ID to execute if condition is True")
    false_branch: str = Field(
        description="Node ID to execute if condition is False"
    )


class LoopNode(WorkflowNode):
    """Loop execution node.

    Repeatedly executes a subgraph until max iterations or convergence condition.
    Enables iterative measurements and feedback control.
    """

    kind: str = Field(default="loop", frozen=True)
    subgraph: dict[str, Any] = Field(
        description="Nested WorkflowGraph as dict (contains nodes + edges)"
    )
    max_iterations: int = Field(description="Maximum loop iterations")
    convergence_expr: str | None = Field(
        default=None,
        description="Python expression - stop early if evaluates to True",
    )
    current_iteration: int = Field(default=0, description="Current iteration count")


class OptimiseNode(WorkflowNode):
    """Parameter optimization node.

    Uses numerical optimization to maximize/minimize an objective function.
    Supports multiple optimization algorithms.
    """

    kind: str = Field(default="optimise", frozen=True)
    target_device: str = Field(description="Device to optimize")
    target_param: str = Field(description="Parameter to vary")
    objective_node: str = Field(
        description="AnalyseNode ID whose output is maximized/minimized"
    )
    method: str = Field(
        default="bayesian",
        description="Optimization method: bayesian, grid, nelder_mead",
    )
    bounds: tuple[float, float] = Field(description="Parameter bounds (min, max)")
    n_iterations: int = Field(default=20, description="Number of optimization steps")
    maximize: bool = Field(default=True, description="Maximize vs minimize objective")

    # Optimization state
    best_value: float | None = Field(default=None)
    best_params: dict[str, Any] | None = Field(default=None)
    iteration_history: list[dict[str, Any]] = Field(default_factory=list)

    def __init__(self, **data: Any) -> None:
        """Initialize optimize node."""
        super().__init__(**data)
        if self.target_device not in self.device_refs:
            self.device_refs.append(self.target_device)


class SetNode(WorkflowNode):
    """Parameter setting node.

    Sets a device parameter to a fixed value or value from another node's result.
    Enables device control and feedback loops.
    """

    kind: str = Field(default="set", frozen=True)
    device: str = Field(description="Device name to configure")
    param: str = Field(description="Parameter name to set")
    value: float | str | None = Field(
        default=None, description="Fixed value to set"
    )
    from_node: str | None = Field(
        default=None, description="Take value from this node's result"
    )
    from_key: str | None = Field(
        default=None, description="Which key in the result dict to use"
    )

    def __init__(self, **data: Any) -> None:
        """Initialize set node."""
        super().__init__(**data)
        if self.device not in self.device_refs:
            self.device_refs.append(self.device)

        # Validate value source
        if self.value is None and self.from_node is None:
            raise ValueError("Must specify either 'value' or 'from_node'")
        if self.value is not None and self.from_node is not None:
            raise ValueError("Cannot specify both 'value' and 'from_node'")


class WaitNode(WorkflowNode):
    """Wait/delay node.

    Waits for a specified time duration or until a device reaches a target value.
    Enables timing control and synchronization.
    """

    kind: str = Field(default="wait", frozen=True)
    duration_s: float | None = Field(
        default=None, description="Wait duration in seconds"
    )
    device: str | None = Field(
        default=None, description="Device to monitor (for condition-based waiting)"
    )
    target_param: str | None = Field(
        default=None, description="Parameter to monitor"
    )
    target_value: float | None = Field(
        default=None, description="Target value to wait for"
    )
    tolerance: float = Field(
        default=0.01, description="Tolerance for target value matching"
    )
    timeout_s: float = Field(
        default=60.0, description="Maximum wait time before timeout"
    )

    def __init__(self, **data: Any) -> None:
        """Initialize wait node."""
        super().__init__(**data)

        # Validate wait configuration
        time_wait = self.duration_s is not None
        condition_wait = (
            self.device is not None
            and self.target_param is not None
            and self.target_value is not None
        )

        if not (time_wait or condition_wait):
            raise ValueError(
                "Must specify either 'duration_s' or device condition parameters"
            )
        if time_wait and condition_wait:
            raise ValueError("Cannot specify both time and condition waits")

        if self.device and self.device not in self.device_refs:
            self.device_refs.append(self.device)


class NotifyNode(WorkflowNode):
    """Notification node.

    Sends notifications via various channels (email, Slack, webhook).
    Enables workflow monitoring and alerts.
    """

    kind: str = Field(default="notify", frozen=True)
    message_template: str = Field(
        description="Message template (supports f-string format with results)"
    )
    webhook_url: str | None = Field(
        default=None, description="Webhook URL for notifications"
    )
    email_to: list[str] = Field(
        default_factory=list, description="Email recipients"
    )
    include_data_summary: bool = Field(
        default=True, description="Include data summary in notification"
    )

    # Message formatting
    title: str | None = Field(default=None, description="Notification title")
    priority: str = Field(default="normal", description="Priority: low, normal, high")


# Create a mapping for node type dispatch
NODE_TYPE_MAP = {
    "acquire": AcquireNode,
    "analyse": AnalyseNode,
    "branch": BranchNode,
    "loop": LoopNode,
    "optimise": OptimiseNode,
    "set": SetNode,
    "wait": WaitNode,
    "notify": NotifyNode,
}


def create_node(node_dict: dict[str, Any]) -> WorkflowNode:
    """Create appropriate node instance from dictionary.

    Args:
        node_dict: Node data with 'kind' field specifying type.

    Returns:
        Concrete WorkflowNode subclass instance.

    Raises:
        ValueError: If kind not supported.
    """
    kind = node_dict.get("kind")
    if kind not in NODE_TYPE_MAP:
        raise ValueError(f"Unknown node kind: {kind}")

    node_class = NODE_TYPE_MAP[kind]
    return node_class(**node_dict)
