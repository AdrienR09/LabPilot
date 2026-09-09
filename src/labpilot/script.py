"""What a workflow script imports.

    from labpilot.script import bind, report, scan

    TAU = (20e-9, 2e-6, 50)

    mw = bind("mw")
    mw.write(frequency=2.87e9)
    result = scan(over={"tau": TAU}, read="apd")

Ordinary top-level Python: no `async def run(session)`, no `await`, no
injected globals. Everything a script uses it imports, so the file is
valid Python on its own — editors complete it, `ruff` checks it, and
`python my_workflow.py` runs it.

## The same names everywhere

`bind("apd")` hands back the same surface as `session.get("apd")` in a
template and `lp["apd"]` at the console: `read`, `write`, `stage`,
`unstage`, `call`, and for a motor `move_abs`, `move_rel`, `get_position`.
One API over three transports — awaited in a template, blocking here,
blocking over REST at the console — rather than three APIs.

## Run it inside LabPilot or run it directly

Inside a run, these resolve through the session that owns the hardware,
role names included, and every call is an abort checkpoint. Run the file
directly and they fall back to the REST client against `LABPILOT_URL`, so
a script can be debugged from a terminal against a live backend. Role
names have nothing to resolve against there — a role is bound by the
workflow, not by the file — so name an instrument id when debugging
standalone.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from labpilot.core.run.script import ScriptAbortedError, current_script

if TYPE_CHECKING:
    from collections.abc import Mapping

    from labpilot.core.run.script import ScriptContext

__all__ = [
    "ScriptAbortedError",
    "aborted",
    "bind",
    "execute",
    "report",
    "scan",
    "session",
]


class _Blocking:
    """An instrument whose coroutines block instead.

    Not a reimplementation of the instrument API — a transport over it.
    Every method comes from the kind wrapper in `core/device/kinds.py`, so
    a method added there appears here with no change, and the two cannot
    drift.
    """

    def __init__(self, target: Any, context: ScriptContext, name: str) -> None:
        self._target = target
        self._context = context
        self._name = name

    def write(self, values: Mapping[str, Any] | None = None, **named: Any) -> None:
        """`write(x=1.0)` or `write({"x": 1.0})`.

        The keyword form is what the console takes and what reads best in a
        script; the dict form is what a template passes. Both, because a
        script moved from one to the other should not need editing.
        """
        self._context.call(self._target.write({**(values or {}), **named}))

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._target, name)
        if not inspect.iscoroutinefunction(attribute):
            return attribute

        def blocking(*args: Any, **kwargs: Any) -> Any:
            return self._context.call(attribute(*args, **kwargs))

        blocking.__name__ = name
        blocking.__doc__ = attribute.__doc__
        return blocking

    def __repr__(self) -> str:
        return f"<{type(self._target).__name__} {self._name!r}>"


def _context() -> ScriptContext:
    context = current_script()
    if context is None:
        raise RuntimeError(
            "This is not running inside a LabPilot workflow. Run it from the "
            "Workflows tab or the console, or set LABPILOT_URL and run the "
            "file directly to talk to a running backend."
        )
    return context


def _remote() -> Any:
    from labpilot.core.notebook_api import LabPilotSession

    return LabPilotSession()


def bind(role: str, optional: bool = False) -> Any:
    """The instrument bound to `role`, ready to use.

    Inside a run, `role` is whatever this workflow's bindings resolve —
    `"detector"`, `"mw"`, a literal instrument id. Standalone, it must be
    an instrument id, because a role is bound by the workflow and there is
    no workflow.

    `optional=True` returns `None` when nothing is bound, for a role a
    script can work without.
    """
    context = current_script()
    if context is None:
        try:
            return _remote()[role]
        except KeyError:
            if optional:
                return None
            raise

    if not context.session.has(role):
        if optional:
            return None
        available = ", ".join(sorted(context.session.devices)) or "none"
        raise KeyError(
            f"Nothing is bound to {role!r}. Bind it in this workflow's "
            f"instrument bindings. Registered: {available}"
        )
    return _Blocking(context.session.get(role), context, role)


def scan(
    over: Mapping[str, tuple[float, float, int]],
    read: str,
    using: str | None = None,
    name: str = "scan",
    hold: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Move over a grid, read a detector at every point, return the result.

        result = scan(over={"stage.x": (0, 10, 51)}, read="apd")

    The same `ScanPlan` the console runs and a template builds, so it
    streams patches, holds on pause, stops its actuators on abort and
    lands in HDF5 — none of which a hand-written loop gets.

    `over` maps each swept axis to `(start, stop, points)`, named as
    `"<instrument>.<parameter>"` or as a bare parameter with `using=`.
    Axes vary in the order given, the first slowest.
    """
    from labpilot.core.run import ScanPlan
    from labpilot.core.run.plans import scan_axes

    return execute(
        ScanPlan(
            scan_axes(over, using), detector=read, name=name, hold=dict(hold or {})
        )
    )


def execute(plan: Any) -> dict[str, Any]:
    """Run any plan and return its result.

    What `scan()` is built on, and the way to run the plans it has no
    sugar for — `OptimizePlan`, `TimeSeriesPlan`, `HardwareTimedScanPlan`.
    The result is also recorded as this script's result, so a script whose
    whole job is one plan needs no `RESULT`.
    """
    context = _context()
    result = context.call(context.session.execute(plan))
    if isinstance(result, dict):
        context.result = result
    return result


def report(**data: Any) -> None:
    """Publish progress from inside a script, for the live views.

    A no-op outside a run, so a script can call it unconditionally.
    """
    context = current_script()
    if context is not None:
        context.call(context.session.report_progress(dict(data)))


def aborted() -> bool:
    """Whether Stop has been pressed.

    Rarely needed: every instrument call is already a checkpoint and
    raises `ScriptAbortedError` on its own. This is for a long computation
    between calls that should notice.
    """
    context = current_script()
    return bool(context and context.abort.is_set())


def session() -> Any:
    """The `Session` this script is running in — the escape hatch.

    For the async API, the event bus, or anything this module does not
    wrap. Its methods are coroutines; `bind()` exists so that most scripts
    never need to know that.
    """
    return _context().session
