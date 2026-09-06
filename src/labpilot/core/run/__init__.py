"""Runs: an acquisition as an object, with real pause and abort.

    plan = ScanPlan([ScanAxis("x", "stage", -4, 4, 51)], detector="apd")
    result = await execute(session, plan)

`execute` is the whole surface a template needs. See `plans.py` for what a
plan is and `run.py` for what the run does around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from labpilot.core.run.descriptor import RunDescriptor
from labpilot.core.run.plans import Plan, ScanAxis, ScanPlan, TimeSeriesPlan
from labpilot.core.run.run import Run, RunAbortedError

if TYPE_CHECKING:
    from labpilot.core.session import Session

__all__ = [
    "Plan",
    "Run",
    "RunAbortedError",
    "RunDescriptor",
    "ScanAxis",
    "ScanPlan",
    "TimeSeriesPlan",
    "execute",
    "prepare",
]


async def prepare(session: Session, plan: Plan) -> Run:
    """Describe `plan` and build the run that will execute it.

    Separate from `execute` because the descriptor is the useful thing to
    have *before* anything moves: it is what the run manager registers, what
    a UI lays itself out from, and what tells a caller how big this run will
    be while it is still free to decline.
    """
    return Run(await plan.describe(session), session)


async def execute(session: Session, plan: Plan) -> dict[str, Any]:
    """Run `plan` to completion and return its result.

    The result is the flat N-D scan convention every existing template
    emits and every view reads, so a template rewritten onto a plan is a
    drop-in for the loop it replaces.
    """
    run = await prepare(session, plan)
    return await run.execute(plan.points(session, run.descriptor))
