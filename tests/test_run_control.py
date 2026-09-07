"""Stopping a workflow stops the experiment, not just the task.

`RunManager.stop_workflow` cancelled the asyncio task running the
script. That lands wherever the script happens to be awaiting — inside a
move, inside a detector read — and nothing tells the actuator to stop, so
the stage keeps travelling to its last commanded position after the run has
been reported stopped. Pause was worse: `Session.pause` moved the FSM to
PAUSED and the scan carried on, which its own docstring admitted.

These tests drive a real engine, running a real template, against mock
instruments, and assert on what the *experiment* does.
"""

from __future__ import annotations

import asyncio
import textwrap

import pytest

from labpilot.core.session import Session
from labpilot.core.run.manager import RunManager
from labpilot.core.workflow.graph import WorkflowGraph
from labpilot.core.workflow.store import WorkflowStore
from labpilot.instruments.MockBasic.simple import (
    MockBasicActuatorND,
    MockBasicDetector0D,
)

SCRIPT = textwrap.dedent(
    '''
    """A slow scan, so a stop request lands mid-run."""
    from labpilot.core.run import ScanAxis, ScanPlan, execute

    REQUIRED_INSTRUMENTS = {
        "actuator": {"kind": "motor", "dimensionality": "ND"},
        "detector": {"kind": "detector"},
    }

    async def run(session):
        return await execute(session, ScanPlan(
            [ScanAxis("x", "actuator", -5.0, 5.0, 60)],
            detector="detector",
            name="slow_scan",
        ))
    '''
)


@pytest.fixture
async def engine(tmp_path):
    session = Session()
    for role, cls in (("actuator", MockBasicActuatorND), ("detector", MockBasicDetector0D)):
        device = cls()
        await device.connect()
        session.register(device, role)

    engine = RunManager(session, WorkflowStore(tmp_path / "workflows.db"))
    engine.runs.root = tmp_path / "data"
    engine.runs.catalogue_path = tmp_path / "data" / "catalogue.db"

    script = tmp_path / "slow_scan.py"
    script.write_text(SCRIPT)
    graph = WorkflowGraph(name="Slow scan")
    graph.metadata["script_path"] = str(script)
    graph.metadata["instrument_bindings"] = {"actuator": "actuator", "detector": "detector"}
    engine.store.save(graph, "test")

    try:
        yield engine, graph.id
    finally:
        engine._runner.shutdown()


async def _started(engine: RunManager, workflow_id: str) -> None:
    """Wait until the run is actually executing points."""
    await engine.start_workflow(workflow_id)
    for _ in range(500):
        state = engine.run_state(workflow_id)
        if state and state["completed"] > 0:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the workflow never started producing points")


async def test_a_running_workflow_reports_how_far_through_it_is(engine):
    """Progress as a fact about the run, rather than something a client
    infers from the size of the last frame it happened to receive."""
    engine, workflow_id = engine
    await _started(engine, workflow_id)

    state = engine.run_state(workflow_id)
    assert state["plan_name"] == "slow_scan"
    assert state["total"] == 60
    assert 0 < state["completed"] <= 60
    assert state["paused"] is False


async def test_pausing_holds_the_scan_and_resuming_continues_it(engine):
    engine, workflow_id = engine
    await _started(engine, workflow_id)

    assert await engine.pause_workflow(workflow_id)
    await asyncio.sleep(0.15)
    held = engine.run_state(workflow_id)["completed"]
    await asyncio.sleep(0.15)
    assert engine.run_state(workflow_id)["completed"] == held, "a paused scan kept going"

    assert await engine.resume_workflow(workflow_id)
    for _ in range(500):
        if not engine.is_running(workflow_id):
            break
        await asyncio.sleep(0.01)
    assert not engine.is_running(workflow_id)


async def test_stopping_keeps_the_measured_points_and_records_a_cancelled_run(engine):
    """The Stop button previously discarded the run: the task was cancelled
    and whatever it had measured went with it."""
    engine, workflow_id = engine
    await _started(engine, workflow_id)

    await engine.stop_workflow(workflow_id)

    latest = engine.store.get_latest_execution(workflow_id)
    assert latest["status"] == "cancelled"
    progress = engine.get_live_progress(workflow_id)
    measured = [v for v in progress["data"] if v is not None]
    assert 0 < len(measured) < 60, "an aborted scan kept nothing, or everything"

    runs = await engine.runs.list_runs()
    assert runs and runs[0]["metadata"]["status"] == "cancelled"


async def test_stopping_leaves_the_stage_where_it_stopped(engine):
    """Not still travelling to the target the cancelled loop last
    commanded."""
    engine, workflow_id = engine
    await _started(engine, workflow_id)

    await engine.stop_workflow(workflow_id)
    stage = engine.session.get("actuator")
    settled = await stage.get_position("x")
    await asyncio.sleep(0.2)

    # The mock reports position with 0.005 noise, so equality is the wrong
    # test; what distinguishes stopped from still-moving is the scale. This
    # stage runs at 10 mm/s, so 0.2 s of continued travel is 2 mm — two
    # orders of magnitude outside the tolerance below.
    assert await stage.get_position("x") == pytest.approx(settled, abs=0.05)


async def test_pausing_something_that_is_not_a_plan_says_so(engine):
    """Rather than reporting a pause that did not happen, which is exactly
    what the FSM-only pause did."""
    engine, workflow_id = engine
    assert await engine.pause_workflow(workflow_id) is False
    assert engine.run_state(workflow_id) is None
