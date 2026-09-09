"""Running a workflow script — both shapes of one.

A workflow has always been "a `.py` file", which is the best thing here
for scripting: readable, editable in the UI, diffable, runnable from the
console. What it was *not* is plain Python. It had to be

    async def run(session) -> dict:
        motor = session.get("actuator")
        await motor.move_abs(x=1.0)

so before writing five lines of physics you had to know what a coroutine
is, what `session` is, and which calls to `await`. The logic in most
templates is a handful of lines wrapped in twenty of scaffolding.

A script can now be top-level code that imports what it uses:

    from labpilot.script import bind, scan

    TAU = (20e-9, 2e-6, 50)

    mw = bind("mw")
    mw.write(frequency=2.87e9)
    result = scan(over={"tau": TAU}, read="apd")

**Imports, not injected globals.** Seeding names into the module namespace
would be less to type and cost more than it saves: the file would stop
being valid Python on its own, editors would lose completion, `ruff` would
flag every name as undefined, and it could not be run directly to debug.
`labpilot.script`'s functions find the running script through a
`ContextVar` — the mechanism role aliases and the progress context already
use — so the file stays ordinary, lintable Python.

## Both shapes, one executor

`async def run(session)` keeps working, unchanged, forever. Which shape a
file is gets decided by parsing it for a top-level `run` function — never
by executing it and looking, which would already have run a plain script's
body. That is the same never-execute-to-inspect property
`instrument_roles.py` holds for `REQUIRED_INSTRUMENTS`.

## Why a plain script runs on its own thread

Its calls are blocking, and the workflow loop is where the instrument
coroutines have to run. A synchronous body cannot block *that* thread
waiting for a coroutine scheduled on it, so the body runs in a worker
thread and each facade call marshals its coroutine back onto the loop
(`labpilot/script.py`). One consequence is an improvement: cancellation
stops depending on where the author happened to put an `await`. Every
read, write and move is a checkpoint, because every one of them checks the
abort flag around its I/O.

## Parameters

A workflow instance's settings are module-level `UPPERCASE` constants, and
that convention is untouched. The legacy shape applies them by `setattr`
after import, which works because `run()` reads them later. A plain script
has no later — its body *is* the program — so the assignments are rewritten
in the parsed tree before it executes:

    TAU = (20e-9, 2e-6, 50)
    # becomes
    TAU = __labpilot_params__.get("TAU", (20e-9, 2e-6, 50))

The file on disk is never touched. That matters: rewriting the source is
exactly what the old parameter store did, and it is why every settings
change used to produce a new timestamped copy of the template.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import contextvars
import importlib.util
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from labpilot.core.session import Session

__all__ = [
    "ScriptAbortedError",
    "ScriptContext",
    "current_script",
    "has_run_function",
    "run_script",
]

_PARAMS = "__labpilot_params__"


class ScriptAbortedError(Exception):
    """Raised inside a plain script when its run has been aborted.

    A synchronous body cannot be cancelled from outside, so abort is
    cooperative: the flag is set, and the next facade call raises this
    instead of touching hardware. Unwinding through the script's own
    `finally` blocks is the point — a script that turns its laser off in
    one gets to.
    """


@dataclass
class ScriptContext:
    """What a running plain script needs to reach the world.

    Carried in a `ContextVar` rather than passed as an argument, which is
    what lets the script's own code stay free of scaffolding. Per-run by
    construction: `asyncio.to_thread` copies the context, so two workflows
    running at once cannot see each other's.
    """

    session: Session
    loop: asyncio.AbstractEventLoop
    abort: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] = field(default_factory=dict)

    def check(self) -> None:
        """Raise if this run has been aborted. Called before each call
        that would touch hardware."""
        if self.abort.is_set():
            raise ScriptAbortedError("This run was aborted")

    def call(self, coroutine: Any, poll: float = 0.1) -> Any:
        """Run a coroutine on the workflow loop and block for its result.

        Polled rather than waited on outright, so an abort arriving during
        a long move or a slow read is noticed while it is still in flight
        instead of after it returns.
        """
        self.check()
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        while True:
            try:
                return future.result(timeout=poll)
            except TimeoutError:
                if self.abort.is_set():
                    future.cancel()
                    raise ScriptAbortedError("This run was aborted") from None


_script_var: contextvars.ContextVar[ScriptContext | None] = contextvars.ContextVar(
    "labpilot_script_context", default=None
)


def current_script() -> ScriptContext | None:
    """The script running on this thread, if any.

    `None` when the file is being run directly — `labpilot/script.py` falls
    back to the REST client then, so a workflow really can be debugged with
    `python my_workflow.py` against a live backend.
    """
    return _script_var.get()


def has_run_function(text: str) -> bool:
    """Whether this source declares a top-level `run` — i.e. is the legacy
    shape.

    Decided by parsing, never by importing: a plain script's body is its
    program, so importing to find out would already have run it.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Let the real execution raise it, with its own line number.
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
        for node in tree.body
    )


async def run_script(
    session: Session, script_path: str | Path, params: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Execute a workflow script of either shape and return its result."""
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Script file not found: {path}")

    text = path.read_text()
    if has_run_function(text):
        return await _run_legacy(session, path, dict(params or {}))
    return await _run_plain(session, path, text, dict(params or {}))


# --- The legacy shape ------------------------------------------------------


async def _run_legacy(
    session: Session, path: Path, params: dict[str, Any]
) -> dict[str, Any]:
    """`async def run(session) -> dict`, imported and awaited.

    Each run imports the module afresh, so two workflows built on the same
    template do not see each other's parameters.
    """
    spec = importlib.util.spec_from_file_location(f"workflow_script_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name, value in params.items():
        if hasattr(module, name):
            setattr(module, name, value)

    result = await module.run(session)
    return result if isinstance(result, dict) else {"result": result}


# --- The plain shape -------------------------------------------------------


async def _run_plain(
    session: Session, path: Path, text: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Top-level code, run on a worker thread against blocking facades.

    Abort is the delicate part. Cancelling the task would leave the thread
    running — and still driving hardware — because a thread cannot be
    cancelled from outside. So the task is shielded: a cancel sets the
    abort flag, waits for the body to unwind through its own `finally`
    blocks, and only then propagates.
    """
    context = ScriptContext(session=session, loop=asyncio.get_running_loop())
    token = _script_var.set(context)
    try:
        task = asyncio.ensure_future(
            asyncio.to_thread(_execute, path, text, params, context)
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            context.abort.set()
            with contextlib.suppress(BaseException):
                await task
            raise
    finally:
        _script_var.reset(token)

    return context.result


def _execute(
    path: Path, text: str, params: dict[str, Any], context: ScriptContext
) -> None:
    """Compile and run the body, on this thread."""
    tree = _with_params(ast.parse(text, filename=str(path)), params)
    module = ModuleType(f"workflow_script_{path.stem}")
    module.__file__ = str(path)
    module.__dict__[_PARAMS] = params

    try:
        exec(compile(tree, str(path), "exec"), module.__dict__)
    except ScriptAbortedError:
        # Not a failure: the user pressed Stop. Whatever the script
        # accumulated before that point is the partial result, and the
        # caller's own cancellation handling takes it from here.
        return

    override = module.__dict__.get("RESULT")
    if isinstance(override, dict):
        context.result = override
    elif override is not None:
        context.result = {"result": override}


def _with_params(tree: ast.Module, params: dict[str, Any]) -> ast.Module:
    """Rewrite top-level constant assignments to consult this instance's
    parameters, keeping the file's own value as the default.

    Only names the caller actually passed are touched, and only when they
    are assigned at module level — the same granularity `setattr` gives the
    legacy shape.
    """
    if not params:
        return tree

    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            name: str | None = statement.targets[0].id
        elif isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            name = statement.target.id if statement.value is not None else None
        else:
            continue

        if name is None or name not in params:
            continue

        statement.value = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id=_PARAMS, ctx=ast.Load()), attr="get", ctx=ast.Load()
            ),
            args=[ast.Constant(value=name), statement.value],
            keywords=[],
        )

    return ast.fix_missing_locations(tree)
