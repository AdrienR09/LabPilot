"""Workflow execution engine.

Runs a workflow: imports its script module and awaits
`async def run(session) -> dict`, emitting lifecycle events on the session
bus and recording the outcome in the store.

There used to be a second execution model here — a topological interpreter
over a typed node graph (Acquire/Analyse/Branch/Loop/Optimise/Set/Wait/
Notify). It was never finished: Branch always took the true edge, Set never
wrote to hardware, Loop never executed its body, and Optimise returned a
hardcoded value. Every real workflow went down the script path instead, so
the interpreter was removed rather than left looking like a feature.
`WorkflowGraph` itself remains — it is the persistence record the store
writes, and it carries the instrument bindings.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import importlib.util
import threading
import uuid
from pathlib import Path
from typing import Any

from labpilot.core.events import Event, EventKind
from labpilot.core.session import Session
from labpilot.core.workflow.graph import WorkflowGraph
from labpilot.core.workflow.instrument_roles import read_required_instruments_from_file
from labpilot.core.workflow.store import WorkflowStore

__all__ = ["WorkflowEngine", "WorkflowExecutionError"]


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""


class _WorkflowRunner:
    """A dedicated thread running its own asyncio loop, for workflow scripts.

    Workflows used to run as tasks on the server's own event loop, so any
    blocking call inside a template — a sync numpy or scipy call, a driver
    that bypassed AdapterBase._to_thread, a bare time.sleep — froze every HTTP
    request and every WebSocket for its duration. Templates are ordinary user
    Python and cannot be assumed non-blocking, so they get their own loop.

    Events still reach the server's subscribers: EventBus records the loop each
    subscriber registered on and marshals delivery onto it (core/events.py).
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="labpilot-workflows", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        self._loop.run_forever()

    def submit(self, coro) -> concurrent.futures.Future:
        """Schedule `coro` on the workflow loop.

        Cancelling the returned future propagates to the underlying task, so
        the engine can keep using it as its cancellation handle.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def shutdown(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)


class WorkflowEngine:
    """Async workflow execution engine.

    One run per workflow id at a time; different workflows may run
    concurrently, each with its own role bindings (see Session's alias
    ContextVar). Cancellation is cooperative — stop_workflow cancels the
    task, which lands at the script's next await.
    """

    def __init__(self, session: Session, store: WorkflowStore):
        """Initialize workflow engine.

        Args:
            session: LabPilot session (provides device registry + event bus).
            store: Workflow store for checkpointing.
        """
        self.session = session
        self.store = store
        self._running_workflows: dict[str, concurrent.futures.Future] = {}
        self._runner = _WorkflowRunner()
        self._execution_results: dict[str, dict[str, Any]] = {}
        # Latest session.report_progress(...) payload per workflow_id — kept
        # after completion (only the session's progress *context* is
        # cleared, see _execute_workflow's finally block) so a poller sees
        # the last frame rather than nothing once a run finishes.
        self._live_progress: dict[str, dict] = {}

    def get_live_progress(self, workflow_id: str) -> dict | None:
        return self._live_progress.get(workflow_id)

    async def start_workflow(
        self,
        workflow_id: str,
        version: int | None = None,
    ) -> str:
        """Start workflow execution.

        Args:
            workflow_id: Workflow ID to execute.
            version: Specific version (default: latest).

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
            self._check_instrument_bindings(graph)

            # Create execution ID
            execution_id = str(uuid.uuid4())

            # Log execution start
            self.store.log_execution(
                workflow_id,
                graph.metadata.get("version", 1),
                "started",
                execution_id=execution_id,
            )

            # Start execution on the workflow loop, not the server's.
            future = self._runner.submit(
                self._execute_workflow(graph, execution_id)
            )
            self._running_workflows[workflow_id] = future

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

        except WorkflowExecutionError:
            raise
        except Exception as e:
            raise WorkflowExecutionError(f"Failed to start workflow: {e}") from e

    async def stop_workflow(self, workflow_id: str) -> None:
        """Stop running workflow.

        Args:
            workflow_id: Workflow ID to stop.
        """
        if workflow_id not in self._running_workflows:
            return

        future = self._running_workflows[workflow_id]
        future.cancel()

        # wrap_future bridges the workflow loop's completion back to this one
        # without blocking the server loop while cancellation lands.
        with contextlib.suppress(asyncio.CancelledError, concurrent.futures.CancelledError):
            await asyncio.wrap_future(future)

        # discard, not del: awaiting the cancelled task runs its own finally
        # block, which already removes this entry. A plain `del` therefore
        # raised KeyError on every *successful* stop, which server.py turned
        # into an HTTP 400 — so the Stop button always reported failure even
        # though the workflow had stopped correctly.
        self._running_workflows.pop(workflow_id, None)

        # Emit stop event
        await self.session.bus.emit(
            Event(
                kind=EventKind.WORKFLOW_STOPPED,
                data={"workflow_id": workflow_id},
            )
        )

    def _check_instrument_bindings(self, graph: WorkflowGraph) -> None:
        """For a role-based workflow (see core/workflow/instrument_roles.py
        and core/api/workflow_templates.py) — one written against role
        names like "xy_actuator" rather than literal instrument ids —
        raise a clear error naming any role that's still unbound, rather
        than letting execution start and fail deep inside the script with
        a generic `KeyError` on the role name."""
        script_path = graph.metadata.get("script_path")
        if not script_path:
            return
        required = read_required_instruments_from_file(script_path)
        if not required:
            return  # not a role-based script — nothing to check
        bindings = graph.metadata.get("instrument_bindings", {})
        # A role declared {"optional": True} (e.g. omniscan.py's "scanner"
        # role, an alternative to its "actuator"/"detector" pair — see
        # that template's own run() for the "at least one path is bound"
        # check it does instead) is allowed to stay unbound; the script
        # itself is responsible for checking session.has(role) before
        # calling session.get(role) on anything optional.
        missing = [
            role for role in required
            if not bindings.get(role) and not required[role].get("optional")
        ]
        if missing:
            raise WorkflowExecutionError(
                f"Unbound instrument role(s): {', '.join(missing)} — "
                f"bind them (e.g. via the flowchart) before running this workflow."
            )

    def _apply_instrument_bindings(self, graph: WorkflowGraph) -> None:
        bindings = graph.metadata.get("instrument_bindings")
        if not bindings:
            return
        for role, real_name in bindings.items():
            if real_name:
                self.session.register_alias(role, real_name)

    async def _execute_script(self, script_path: str) -> dict[str, Any]:
        """Import a workflow script and await its `run(session)` — the one
        contract every generated or hand/AI-written script follows (see
        core/workflow/script.py). Raises on import/attribute errors or
        whatever the script itself raises; the caller's surrounding
        try/except in `_execute_workflow` logs/emits failure the same way
        a failed node would.
        """
        path = Path(script_path)
        if not path.exists():
            raise WorkflowExecutionError(f"Script file not found: {script_path}")

        spec = importlib.util.spec_from_file_location(f"workflow_script_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise WorkflowExecutionError(f"Could not load script: {script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            raise WorkflowExecutionError(
                f"Script {script_path} has no `run(session)` function to execute"
            )

        result = await module.run(self.session)
        return result if isinstance(result, dict) else {"result": result}

    async def _execute_workflow(
        self,
        graph: WorkflowGraph,
        execution_id: str,
    ) -> None:
        """Run one workflow to completion (inside its own asyncio task)."""
        workflow_id = graph.id
        self._apply_instrument_bindings(graph)
        # Drop any frame left over from a previous run before this one's
        # own report_progress() calls start landing — otherwise a poller
        # would briefly see the *previous* run's finished frame while
        # running=True at the very start of this one.
        self._live_progress.pop(workflow_id, None)
        self.session.set_progress_context(workflow_id, execution_id, self._live_progress)

        try:
            # Start this run's results empty rather than accumulating into the
            # previous run's dict. The script path .update()s into it, so a key
            # a previous run produced but this one doesn't used to survive into
            # this run's WORKFLOW_COMPLETED payload and its persisted results.
            self._execution_results[workflow_id] = {}
            node_results = self._execution_results[workflow_id]

            script_path = graph.metadata.get("script_path")
            if not script_path:
                raise WorkflowExecutionError(
                    f"Workflow {workflow_id} has no script_path to run. "
                    f"Every workflow is a Python module exposing "
                    f"`async def run(session) -> dict`; see "
                    f"core/workflow_templates/ for the contract."
                )
            node_results.update(await self._execute_script(script_path))

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
            # Clean up — aliases and the progress context are scoped to this
            # one execution, never left registered for whatever runs next.
            # _live_progress[workflow_id] itself is NOT cleared here — the
            # last reported frame stays available for polling after the run
            # ends (see get_live_progress).
            self.session.clear_aliases()
            self.session.clear_progress_context()
            if workflow_id in self._running_workflows:
                del self._running_workflows[workflow_id]

    def get_running_workflows(self) -> list[str]:
        """Get list of currently running workflow IDs."""
        return list(self._running_workflows.keys())

    def is_running(self, workflow_id: str) -> bool:
        """Check if workflow is currently running."""
        return workflow_id in self._running_workflows
