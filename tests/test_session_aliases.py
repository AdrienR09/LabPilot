"""Role aliases must be per-execution, not shared session state.

WorkflowEngine binds a workflow's roles (`register_alias`) immediately before
running it and clears them afterwards. When those lived in a plain instance
dict on the shared Session, two workflows running at once shared one
namespace: both templates use the role name "detector", so the second to start
silently rebound the first, and whichever finished first called
clear_aliases() and unbound the other mid-run.
"""

from __future__ import annotations

import asyncio

from labpilot.core.session import Session
from labpilot.instruments.MockBasic.simple import MockBasicDetector0D


async def _make_session() -> Session:
    session = Session()
    for name in ("apd_a", "apd_b"):
        adapter = MockBasicDetector0D(name=name)
        await adapter.connect()
        session.register(adapter, name=name)
    return session


async def test_concurrent_workflows_do_not_clobber_each_others_roles():
    session = await _make_session()
    seen: dict[str, list[str]] = {"a": [], "b": []}
    both_bound = asyncio.Event()
    bound_count = 0

    async def run(tag: str, instrument: str) -> None:
        nonlocal bound_count
        session.register_alias("detector", instrument)
        try:
            # Force the interleaving the bug needed: both tasks bind the same
            # role name before either resolves it.
            bound_count += 1
            if bound_count == 2:
                both_bound.set()
            await both_bound.wait()

            for _ in range(3):
                seen[tag].append(session.get_raw("detector").schema.name)
                await asyncio.sleep(0)
        finally:
            session.clear_aliases()

    await asyncio.gather(run("a", "apd_a"), run("b", "apd_b"))

    assert seen["a"] == ["apd_a"] * 3
    assert seen["b"] == ["apd_b"] * 3


async def test_clear_aliases_in_one_task_leaves_another_bound():
    session = await _make_session()
    long_bound = asyncio.Event()
    cleared = asyncio.Event()
    resolved: list[str] = []

    async def short_lived() -> None:
        # Bind and clear only *after* the other task is already bound, so this
        # deterministically reproduces the finish-order the bug depended on
        # rather than relying on how gather happens to schedule.
        await long_bound.wait()
        session.register_alias("detector", "apd_a")
        session.clear_aliases()
        cleared.set()

    async def long_lived() -> None:
        session.register_alias("detector", "apd_b")
        long_bound.set()
        await cleared.wait()
        resolved.append(session.get_raw("detector").schema.name)

    await asyncio.gather(short_lived(), long_lived())
    assert resolved == ["apd_b"]


async def test_aliases_do_not_leak_between_sequential_runs():
    session = await _make_session()

    async def run(instrument: str) -> None:
        session.register_alias("detector", instrument)
        try:
            assert session.has("detector")
        finally:
            session.clear_aliases()

    await run("apd_a")
    # A fresh task with no bindings must not see the previous run's role.
    await asyncio.gather(asyncio.sleep(0))
    assert not session.has("detector")
