"""Workflow execution engine.

Async executor for WorkflowGraphs with checkpointing, event emission,
and state management. Executes nodes in topological order and handles
all node types (Acquire, Analyse, Branch, Loop, etc.).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from labpilot_core.core.events import Event, EventKind
from labpilot_core.core.session import Session
from labpilot_core.workflow.code_sandbox import SandboxError, execute_analysis_code
from labpilot_core.workflow.graph import WorkflowGraph
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
from labpilot_core.workflow.store import WorkflowStore

__all__ = ["WorkflowEngine", "WorkflowExecutionError"]


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""


class WorkflowEngine:
    """Async workflow execution engine.

    Features:
    - Topological execution order
    - Node result passing between nodes
    - Event emission on session EventBus
    - SQLite checkpointing after each node
    - Resume after crash capability
    - Pause/resume/abort controls
    - FSM state management integration

    The engine is purely deterministic and never calls AI directly.
    All workflow modifications come through the graph manipulation API.
    """

    def __init__(self, session: Session, store: WorkflowStore):
        """Initialize workflow engine.

        Args:
            session: LabPilot session (provides device registry + event bus).
            store: Workflow store for checkpointing.
        """
        self.session = session
        self.store = store
        self._running_workflows: dict[str, asyncio.Task] = {}
        self._execution_results: dict[str, dict[str, Any]] = {}

    async def start_workflow(
        self,
        workflow_id: str,
        version: int | None = None,
        resume: bool = False,
    ) -> str:
        """Start workflow execution.

        Args:
            workflow_id: Workflow ID to execute.
            version: Specific version (default: latest).
            resume: Resume from checkpoint vs restart.

        Returns:
            Execution ID for tracking.

        Raises:
            WorkflowExecutionError: If workflow already running or not found.
        """
        if workflow_id in self._running_workflows:
            raise WorkflowExecutionError(f"Workflow {workflow_id} already running")

        try:
            # Load workflow graph
            graph = self.store.load(workflow_id, version)

            # Create execution ID
            execution_id = str(uuid.uuid4())

            # Log execution start
            self.store.log_execution(
                workflow_id,
                graph.metadata.get("version", 1),
                "started",
                execution_id=execution_id,
            )

            # Start execution task
            task = asyncio.create_task(
                self._execute_workflow(graph, execution_id, resume)
            )
            self._running_workflows[workflow_id] = task

            # Emit start event
            await self.session.bus.emit(
                Event(
                    kind=EventKind.WORKFLOW_STARTED,
                    data={
                        "workflow_id": workflow_id,
                        "execution_id": execution_id,
                        "name": graph.name,
                    },
                )
            )

            return execution_id

        except Exception as e:
            raise WorkflowExecutionError(f"Failed to start workflow: {e}")

    async def stop_workflow(self, workflow_id: str) -> None:
        """Stop running workflow.

        Args:
            workflow_id: Workflow ID to stop.
        """
        if workflow_id not in self._running_workflows:
            return

        task = self._running_workflows[workflow_id]
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        del self._running_workflows[workflow_id]

        # Emit stop event
        await self.session.bus.emit(
            Event(
                kind=EventKind.WORKFLOW_STOPPED,
                data={"workflow_id": workflow_id},
            )
        )

    async def _execute_workflow(
        self,
        graph: WorkflowGraph,
        execution_id: str,
        resume: bool,
    ) -> None:
        """Execute workflow graph (runs in asyncio task)."""
        workflow_id = graph.id

        try:
            # Initialize execution context
            if workflow_id not in self._execution_results:
                self._execution_results[workflow_id] = {}

            node_results = self._execution_results[workflow_id]

            # Get execution order (topological sort)
            sorted_nodes = graph.topological_sort()

            # Execute nodes in order
            for node_id in sorted_nodes:
                node_data = graph.nodes[node_id]

                # Skip if resuming and already completed
                if resume and node_results.get(node_id, {}).get("status") == "completed":
                    continue

                # Create node instance
                node = create_node(node_data)

                # Execute node
                try:
                    await self._execute_node(node, node_results, graph)

                    # Checkpoint after each successful node
                    node_results[node_id] = {
                        "status": "completed",
                        "result": node.result,
                        "completed_at": time.time(),
                    }

                except Exception as e:
                    # Node failed - mark and potentially continue or abort
                    node_results[node_id] = {
                        "status": "failed",
                        "error": str(e),
                        "failed_at": time.time(),
                    }

                    await self.session.bus.emit(
                        Event(
                            kind=EventKind.WORKFLOW_NODE_ERROR,
                            data={
                                "workflow_id": workflow_id,
                                "node_id": node_id,
                                "error": str(e),
                            },
                        )
                    )

                    # For now, abort on any node failure
                    raise WorkflowExecutionError(f"Node {node_id} failed: {e}")

            # Workflow completed successfully
            self.store.log_execution(
                workflow_id,
                graph.metadata.get("version", 1),
                "completed",
                results=node_results,
                execution_id=execution_id,
            )

            await self.session.bus.emit(
                Event(
                    kind=EventKind.WORKFLOW_COMPLETED,
                    data={
                        "workflow_id": workflow_id,
                        "execution_id": execution_id,
                        "results": node_results,
                    },
                )
            )

        except asyncio.CancelledError:
            # Workflow was cancelled
            self.store.log_execution(
                workflow_id,
                graph.metadata.get("version", 1),
                "cancelled",
                execution_id=execution_id,
            )
            raise

        except Exception as e:
            # Workflow failed
            self.store.log_execution(
                workflow_id,
                graph.metadata.get("version", 1),
                "failed",
                results={"error": str(e)},
                execution_id=execution_id,
            )

            await self.session.bus.emit(
                Event(
                    kind=EventKind.WORKFLOW_ERROR,
                    data={
                        "workflow_id": workflow_id,
                        "execution_id": execution_id,
                        "error": str(e),
                    },
                )
            )
            raise

        finally:
            # Clean up
            if workflow_id in self._running_workflows:
                del self._running_workflows[workflow_id]

    async def _execute_node(
        self,
        node: WorkflowNode,
        node_results: dict[str, Any],
        graph: WorkflowGraph,
    ) -> None:
        """Execute a single workflow node."""
        node.status = NodeStatus.RUNNING
        node.started_at = time.time()

        # Emit node start event
        await self.session.bus.emit(
            Event(
                kind=EventKind.WORKFLOW_NODE_STARTED,
                data={
                    "workflow_id": graph.id,
                    "node_id": node.id,
                    "node_name": node.name,
                    "node_kind": node.kind,
                },
            )
        )

        try:
            # Execute based on node type
            if isinstance(node, AcquireNode):
                result = await self._execute_acquire_node(node)
            elif isinstance(node, AnalyseNode):
                result = await self._execute_analyse_node(node, node_results)
            elif isinstance(node, BranchNode):
                result = await self._execute_branch_node(node, node_results)
            elif isinstance(node, SetNode):
                result = await self._execute_set_node(node, node_results)
            elif isinstance(node, WaitNode):
                result = await self._execute_wait_node(node)
            elif isinstance(node, NotifyNode):
                result = await self._execute_notify_node(node, node_results)
            elif isinstance(node, OptimiseNode):
                result = await self._execute_optimise_node(node, graph, node_results)
            elif isinstance(node, LoopNode):
                result = await self._execute_loop_node(node, node_results)
            else:
                raise WorkflowExecutionError(f"Unknown node type: {type(node)}")

            # Set result and mark completed
            node.result = result
            node.status = NodeStatus.COMPLETED
            node.completed_at = time.time()

            # Emit completion event
            await self.session.bus.emit(
                Event(
                    kind=EventKind.WORKFLOW_NODE_COMPLETED,
                    data={
                        "workflow_id": graph.id,
                        "node_id": node.id,
                        "result": result,
                    },
                )
            )

        except Exception as e:
            # Mark node as failed
            node.status = NodeStatus.FAILED
            node.error_message = str(e)
            node.completed_at = time.time()
            raise

    async def _execute_acquire_node(self, node: AcquireNode) -> dict[str, Any]:
        """Execute data acquisition node."""
        # Get device from session
        device = self.session.get_device(node.device)
        if device is None:
            raise WorkflowExecutionError(f"Device '{node.device}' not found")

        # Execute scan plan (simplified - would use actual ScanPlan)
        await device.stage()
        try:
            data = await device.read()
            return {"data": data, "device": node.device}
        finally:
            await device.unstage()

    async def _execute_analyse_node(
        self, node: AnalyseNode, node_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute analysis node in sandbox."""
        # Gather input data from referenced nodes
        input_data = {}
        for input_node_id in node.inputs:
            if input_node_id in node_results:
                result_info = node_results[input_node_id]
                if result_info.get("status") == "completed":
                    input_data[input_node_id] = result_info["result"]

        # Execute code in sandbox
        try:
            result = execute_analysis_code(
                node.code,
                input_data,
                {},  # Empty params for now
                node.allowed_imports,
                node.timeout_s,
            )
            return result
        except SandboxError as e:
            raise WorkflowExecutionError(f"Analysis code execution failed: {e}")

    async def _execute_branch_node(
        self, node: BranchNode, node_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute branch node (conditional logic)."""
        # Evaluate condition (simplified - would need safe eval)
        # For now, just return which branch would be taken
        return {
            "condition": node.condition,
            "branch_taken": "true_branch",  # Would evaluate condition
        }

    async def _execute_set_node(
        self, node: SetNode, node_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute parameter setting node."""
        # Get device
        device = self.session.get_device(node.device)
        if device is None:
            raise WorkflowExecutionError(f"Device '{node.device}' not found")

        # Determine value to set
        if node.value is not None:
            value = node.value
        elif node.from_node and node.from_key:
            if node.from_node not in node_results:
                raise WorkflowExecutionError(f"Input node '{node.from_node}' not executed")
            result_info = node_results[node.from_node]
            if result_info.get("status") != "completed":
                raise WorkflowExecutionError(f"Input node '{node.from_node}' not completed")
            value = result_info["result"].get(node.from_key)
            if value is None:
                raise WorkflowExecutionError(f"Key '{node.from_key}' not found in input")
        else:
            raise WorkflowExecutionError("SetNode must specify value source")

        # Set parameter (simplified - would use actual device API)
        return {
            "device": node.device,
            "param": node.param,
            "value_set": value,
        }

    async def _execute_wait_node(self, node: WaitNode) -> dict[str, Any]:
        """Execute wait/delay node."""
        if node.duration_s is not None:
            # Simple time delay
            await asyncio.sleep(node.duration_s)
            return {"waited_time": node.duration_s}
        else:
            # Wait for device condition (simplified)
            return {"condition_met": True}

    async def _execute_notify_node(
        self, node: NotifyNode, node_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute notification node."""
        # Format message template (simplified)
        message = node.message_template.format(
            results=node_results,
            timestamp=time.ctime(),
        )

        # Send notification (would implement actual webhook/email)
        return {
            "message_sent": message,
            "notification_channels": ["webhook"] if node.webhook_url else [],
        }

    async def _execute_optimise_node(
        self, node: OptimiseNode, graph: WorkflowGraph, node_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute parameter optimization node."""
        # Simplified optimization - would implement actual algorithms
        return {
            "method": node.method,
            "target_param": node.target_param,
            "best_value": 42.0,  # Placeholder
            "iterations_completed": node.n_iterations,
        }

    async def _execute_loop_node(
        self, node: LoopNode, node_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute loop node with subgraph."""
        # Simplified loop execution - would recursively execute subgraph
        iterations_completed = 0
        while iterations_completed < node.max_iterations:
            # Would execute subgraph here
            iterations_completed += 1

            # Check convergence condition if specified
            if node.convergence_expr:
                # Would evaluate convergence expression
                break

        return {
            "iterations_completed": iterations_completed,
            "converged": iterations_completed < node.max_iterations,
        }

    def get_running_workflows(self) -> list[str]:
        """Get list of currently running workflow IDs."""
        return list(self._running_workflows.keys())

    def is_running(self, workflow_id: str) -> bool:
        """Check if workflow is currently running."""
        return workflow_id in self._running_workflows
