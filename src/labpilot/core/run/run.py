"""`Run` — one execution of a `Plan`, with the control a scan actually needs.

Pause, resume and abort exist today only as FSM transitions. Their own
docstrings say so: `Session.pause` notes it "transitions state but does not
yet implement actual pause/resume logic", and `Session.abort` that "full
abort implementation requires anyio cancellation scope integration". What
`WorkflowEngine.stop_workflow` really does is cancel the asyncio task, which
lands wherever the script happens to be awaiting — mid-move, mid-read — and
nothing tells the actuator to stop. The hardware finishes travelling to
whatever position was last commanded, after the run has been reported
stopped.

A `Run` makes those three operations mean something, by owning the loop
between points rather than leaving it inside each template:

- **pause** waits at a point boundary, so the detector is not left staged
  mid-integration and the actuator is at a known position;
- **abort** stops at the next boundary, calls `stop()` on every actuator the
  descriptor names, and keeps the points already measured;
- **resume** continues from the point where it stopped.

It also owns what the templates each hand-roll: the flat result buffer, the
`completed`/`total` counters, the progress event and the per-point
`DatasetPatch`. A plan yields one patch per point and knows nothing about
any of it.

## Why the loop is here and not in the plan

Cancellation between points is the only place a scan can be interrupted
*safely*, and it is also where progress is reported and where a patch is
published. Keeping all three in one place is what lets pause be real: a
plan written as a plain async generator gets pausable, abortable, streaming
execution without a line of its own about any of it.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from labpilot.core.fsm import ScanState, State

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from labpilot.core.data.dataset import DatasetPatch
    from labpilot.core.run.descriptor import RunDescriptor
    from labpilot.core.session import Session

__all__ = ["Run", "RunAbortedError", "active_run"]

# Runs currently executing, by workflow id. A run executes on the workflow
# loop inside a template's own call stack, so there is otherwise no handle
# on it from the server loop where a Stop or Pause request arrives — which
# is why stopping a workflow could only ever cancel the whole task. Keyed
# by workflow id because that is what the REST routes address.
_ACTIVE: dict[str, Run] = {}


def active_run(workflow_id: str) -> Run | None:
    """The run this workflow is currently executing, if any."""
    return _ACTIVE.get(workflow_id)


class RunAbortedError(Exception):
    """Raised inside a run when `abort()` has been requested.

    Deliberately not `asyncio.CancelledError`: an abort is a *result* — the
    points measured before it are kept and saved — while a cancelled task
    is an unwind. Catching this one cannot swallow a real cancellation.
    """


class Run:
    """One execution of a plan: its descriptor, its data, and its controls."""

    def __init__(self, descriptor: RunDescriptor, session: Session) -> None:
        self.descriptor = descriptor
        self.session = session
        self.state = ScanState.idle()
        self.data: list[Any] = descriptor.allocate()
        self.completed = 0
        self._filled = 0
        self.started_at: float | None = None
        self.finished_at: float | None = None

        self.workflow_id: str | None = None
        self._abort_requested = False
        self._loop: asyncio.AbstractEventLoop | None = None
        # Set = "keep going". Cleared by pause(), which is what the point
        # boundary waits on.
        self._gate = asyncio.Event()
        self._gate.set()

    # --- Controls ---------------------------------------------------------
    #
    # Called from the server's event loop while the run executes on the
    # workflow loop (see WorkflowEngine._WorkflowRunner), so each one hops
    # loops rather than touching an asyncio primitive from the wrong thread.

    def pause(self) -> None:
        """Stop at the next point boundary, staying resumable."""
        self._call_on_run_loop(self._gate.clear)
        self.state = ScanState(state=State.PAUSED, message="Paused by user")

    def resume(self) -> None:
        self._call_on_run_loop(self._gate.set)
        self.state = ScanState(state=State.RUNNING, message="Resumed")

    def abort(self) -> None:
        """Stop for good at the next point boundary, keeping what was measured.

        Sets the flag and releases the pause gate, so a paused run aborts
        rather than waiting for a resume that is not coming. The actuators
        are stopped by the run itself, on its own loop — doing it from here
        would drive hardware from the HTTP thread.
        """
        self._abort_requested = True
        self._call_on_run_loop(self._gate.set)

    @property
    def aborting(self) -> bool:
        return self._abort_requested

    @property
    def paused(self) -> bool:
        return not self._gate.is_set()

    def _call_on_run_loop(self, fn: Any) -> None:
        loop = self._loop
        if loop is None or loop is _current_loop():
            fn()
            return
        loop.call_soon_threadsafe(fn)

    # --- Execution --------------------------------------------------------

    async def execute(self, points: AsyncIterator[DatasetPatch]) -> dict[str, Any]:
        """Consume a plan's patches to completion, and return the result.

        The return value is the flat N-D scan convention every template
        already emits and every view already reads (`data` + `shape` +
        `axis_names` + `axis_positions` + ...), assembled from the
        descriptor rather than by hand — so a template rewritten onto a
        plan returns exactly what its predecessor did.
        """
        self._loop = _current_loop()
        self.started_at = time.time()
        self.state = ScanState(state=State.RUNNING, message="Running")
        total = self.descriptor.points
        self.workflow_id = self.session.progress_context_id()
        if self.workflow_id:
            # Publish the handle a Stop or Pause request needs. Registered
            # here rather than by the engine because the engine hands
            # control to the template, and it is the template that decides
            # to run a plan.
            _ACTIVE[self.workflow_id] = self

        try:
            per_point = max(1, self.descriptor.per_point)
            async for patch in points:
                patch.apply(self.data)
                # Progress is measured in values delivered, not in patches
                # received: a per-point plan yields one point per patch, but
                # a hardware-timed scanner delivers whatever arrived since
                # the last poll, which is a burst of samples.
                self._filled += patch.size
                self.completed = min(total, self._filled // per_point)
                await self._publish(patch, total)

                # The point boundary: the one place a scan can be paused or
                # aborted without leaving hardware mid-operation.
                if not self._gate.is_set():
                    await self._gate.wait()
                if self._abort_requested:
                    raise RunAbortedError(
                        f"aborted after {self.completed} of {total} points"
                    )
        except RunAbortedError:
            self.state = ScanState(state=State.ERROR, message="Aborted by user")
            await self._stop_actuators()
            raise
        except Exception as e:
            self.state = ScanState(state=State.ERROR, message=str(e))
            raise
        else:
            self.state = ScanState(state=State.DONE, message="Completed")
        finally:
            self.finished_at = time.time()
            if self.workflow_id and _ACTIVE.get(self.workflow_id) is self:
                del _ACTIVE[self.workflow_id]

        return self.result()

    def result(self) -> dict[str, Any]:
        """What the run measured, in the convention the views read."""
        return {
            **self.descriptor.result_fields(),
            **dict(self.descriptor.params),
            "data": self.data,
            "completed": self.completed,
            "total": self.descriptor.points,
        }

    def dataset(self):
        """The same data as a `Dataset` — units, coordinates, provenance."""
        return self.descriptor.dataset(self.data)

    # --- Internals --------------------------------------------------------

    async def _publish(self, patch: DatasetPatch, total: int) -> None:
        """One progress frame and one patch per point.

        The description (shape, axis names and positions) rides along with
        the first patch only. Repeating it costs an axis array per point,
        which for a 1800-channel spectrometer is most of the traffic the
        patch exists to avoid; clients merge what is present and keep the
        rest.
        """
        fields = self.descriptor.result_fields()
        await self.session.report_progress({
            **fields,
            "data": self.data,
            "completed": self.completed,
            "total": total,
        })
        await self.session.report_reading(
            patch,
            completed=self.completed,
            total=total,
            **(fields if self.completed == 1 else {}),
        )

    async def _stop_actuators(self) -> None:
        """Tell every device this run drives to stop where it is.

        The missing half of abort: cancelling the task ends the *software*
        loop, while a stage that was commanded to a position keeps
        travelling there. Failures are swallowed deliberately — an abort
        that raises because one device has no way to stop must still stop
        the others, and must still leave the run reported as aborted rather
        than failed.
        """
        for name in self.descriptor.actuators:
            try:
                device = self.session.get(name)
            except KeyError:
                continue
            stop = getattr(device, "stop", None)
            if stop is None:
                continue
            try:
                await stop()
            except Exception as e:
                print(f"⚠️  Could not stop {name} on abort: {e}")


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
