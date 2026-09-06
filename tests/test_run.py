"""A run as an object: it knows its shape up front, and it can be stopped.

Two claims are under test, and they are the two Phase 3 exists for.

1. **The shape is knowable before the first point.** Twelve of fifteen
   templates hand-allocate their result grid and hand-count progress
   because nothing else knew it. `RunDescriptor` knows it, so the
   allocation, the counters, the axis metadata and the streaming happen
   once instead of per template.

2. **Pause and abort mean something.** They were FSM transitions —
   `Session.pause`'s own docstring said it "transitions state but does not
   yet implement actual pause/resume logic" — and stopping a workflow
   cancelled a task while the stage kept travelling to its last commanded
   position. Here a run stops at a point boundary, keeps what it measured,
   and tells the hardware to stop.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from labpilot.core.data.dataset import Axis, DatasetPatch
from labpilot.core.run import ScanAxis, ScanPlan, TimeSeriesPlan, execute, prepare
from labpilot.core.run.descriptor import RunDescriptor
from labpilot.core.run.run import Run, RunAbortedError
from labpilot.core.session import Session
from labpilot.instruments import adapter_registry


async def _session(**devices: str) -> Session:
    """A session with each role bound to a freshly connected mock."""
    session = Session()
    for role, key in devices.items():
        adapter = adapter_registry.get(key)()
        await adapter.connect()
        session.register(adapter, role)
    return session


# --- What is knowable before the first point ------------------------------


def _descriptor() -> RunDescriptor:
    return RunDescriptor(
        run_uid="u", plan_name="scan",
        axes=(
            Axis("x", np.zeros(3), "mm", kind="actuator", device="stage"),
            Axis("y", np.zeros(2), "mm", kind="actuator", device="stage"),
            Axis("wavelength", np.zeros(5), "nm", kind="detector"),
        ),
        scan_axis_count=2,
        value_unit="counts",
    )


def test_a_descriptor_splits_its_shape_into_points_and_values_per_point():
    """The arithmetic every template repeats by hand, stated once."""
    descriptor = _descriptor()
    assert descriptor.shape == (3, 2, 5)
    assert descriptor.points == 6
    assert descriptor.per_point == 5
    assert descriptor.size == 30
    assert len(descriptor.allocate()) == 30


def test_which_axes_are_drivable_is_a_property_of_the_axes():
    """`actuator_axis_count` is a hand-maintained integer in every template
    and matched positionally against `axis_names` in every view; a typo or
    a reordering silently moves a crosshair onto an axis nothing can
    drive."""
    descriptor = _descriptor()
    assert descriptor.actuator_axis_count == 2
    assert descriptor.actuators == ("stage",)


def test_the_descriptor_emits_exactly_the_convention_the_views_read():
    """What makes a plan-based template a drop-in: the result keys are
    unchanged, so the Qt views, the React client, `pick_view` and the HDF5
    writer need no change at all."""
    fields = _descriptor().result_fields()
    assert fields["axis_names"] == ["x", "y", "wavelength"]
    assert fields["shape"] == [3, 2, 5]
    assert fields["actuator_axis_count"] == 2
    assert fields["value_unit"] == "counts"
    assert fields["axis_units"] == {"x": "mm", "y": "mm", "wavelength": "nm"}
    assert [len(p) for p in fields["axis_positions"]] == [3, 2, 5]


async def test_a_plan_describes_a_1d_detector_before_moving_anything():
    """A schema says a spectrometer returns a 1-D array but not how long it
    is, so describing costs one reading — and then the whole run is
    allocated up front instead of on the first point."""
    session = await _session(stage="mock_basic_actuator_nd", detector="mock_basic_detector_1d")
    plan = ScanPlan([ScanAxis("x", "stage", 0.0, 1.0, 4)], detector="detector")

    descriptor = await plan.describe(session)

    assert descriptor.points == 4
    assert descriptor.per_point > 1  # the detector's own axis, discovered
    assert descriptor.scan_axis_count == 1
    assert next(a.name for a in descriptor.axes) == "x"
    assert descriptor.actuators == ("stage",)


async def test_a_grid_can_span_two_different_instruments():
    """The generalisation. `ScanCapability` takes exactly one actuator and
    one detector, which is why `odmr_sweep.py` — stepping a *source's*
    frequency rather than a motor's position — reimplements the same loop
    instead of reusing it. An axis names its own device, so one grid can
    sweep a stage and a microwave source together."""
    session = await _session(
        stage="mock_basic_actuator_nd",
        source="mock_microwave_source",
        detector="mock_basic_detector_0d",
    )
    plan = ScanPlan(
        [
            ScanAxis("x", "stage", 0.0, 1.0, 2),
            ScanAxis("cw_frequency", "source", 2.82e9, 2.86e9, 3),
        ],
        detector="detector",
    )

    result = await execute(session, plan)

    assert result["shape"] == [2, 3]
    assert result["axis_names"] == ["x", "cw_frequency"]
    assert result["completed"] == 6
    assert all(value is not None for value in result["data"])


async def test_a_scan_produces_the_result_its_hand_written_predecessor_did():
    session = await _session(stage="mock_basic_actuator_nd", detector="mock_basic_detector_1d")
    plan = ScanPlan(
        [ScanAxis("x", "stage", -1.0, 1.0, 3), ScanAxis("y", "stage", -1.0, 1.0, 2)],
        detector="detector",
    )

    result = await execute(session, plan)

    assert set(result) >= {
        "data", "shape", "axis_names", "axis_positions",
        "actuator_axis_count", "value_unit", "axis_units",
    }
    assert result["actuator_axis_count"] == 2
    assert len(result["data"]) == int(np.prod(result["shape"]))
    assert not any(value is None for value in result["data"])


async def test_a_time_series_is_the_same_object_with_a_time_axis():
    session = await _session(detector="mock_basic_detector_0d")
    result = await execute(
        session, TimeSeriesPlan(detector="detector", samples=5, interval=0.0)
    )
    assert result["axis_names"] == ["time"]
    assert result["actuator_axis_count"] == 0  # nothing to drag a crosshair along
    assert len(result["data"]) == 5


# --- Streaming ------------------------------------------------------------


async def test_each_point_is_published_as_one_patch_not_the_whole_array():
    from labpilot.core.events import EventKind

    session = await _session(stage="mock_basic_actuator_nd", detector="mock_basic_detector_1d")
    patches: list[dict] = []

    async def collect() -> None:
        async for event in session.bus.subscribe(EventKind.READING):
            patches.append(event.data)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)  # let it register before the run starts

    plan = ScanPlan([ScanAxis("x", "stage", 0.0, 1.0, 4)], detector="detector")
    run = await prepare(session, plan)
    session.set_progress_context("wf", run.descriptor.run_uid, {})

    await run.execute(plan.points(session, run.descriptor))
    await asyncio.sleep(0.05)
    collector.cancel()

    assert len(patches) == 4
    assert all(len(p["values"]) == run.descriptor.per_point for p in patches)
    # The run-level description rides on the first patch only: repeating it
    # would ship the axis arrays once per point.
    assert "axis_positions" in patches[0]
    assert "axis_positions" not in patches[-1]


# --- Pause and abort ------------------------------------------------------


class _CountingPoints:
    """A plan's point stream, controllable from the test."""

    def __init__(self, descriptor: RunDescriptor) -> None:
        self.descriptor = descriptor
        self.produced = 0

    async def __aiter__(self):
        for index in range(self.descriptor.points):
            self.produced += 1
            yield DatasetPatch("data", index, np.asarray([float(index)]))
            await asyncio.sleep(0)


def _bare_run(points: int) -> tuple[Run, _CountingPoints]:
    descriptor = RunDescriptor(
        run_uid="u", plan_name="p",
        axes=(Axis("i", np.arange(points), kind="index"),),
        scan_axis_count=1,
    )
    return Run(descriptor, Session()), _CountingPoints(descriptor)


async def test_a_paused_run_stops_advancing_and_resumes_where_it_stopped():
    """Pause was an FSM transition and nothing else: the scan kept going."""
    run, points = _bare_run(20)
    task = asyncio.create_task(run.execute(points.__aiter__()))
    await asyncio.sleep(0)
    run.pause()

    # Let the point already in flight finish, then check it stays there.
    for _ in range(50):
        await asyncio.sleep(0)
    at_pause = run.completed
    assert 0 < at_pause < 20
    for _ in range(50):
        await asyncio.sleep(0)
    assert run.completed == at_pause, "a paused run kept acquiring"
    assert run.paused

    run.resume()
    await task
    assert run.completed == 20


async def test_an_aborted_run_keeps_the_points_it_already_measured():
    """Stopping at point 900 of 1000 must not discard 900 points."""
    run, points = _bare_run(50)
    task = asyncio.create_task(run.execute(points.__aiter__()))
    while run.completed < 3:
        await asyncio.sleep(0)
    run.abort()

    with pytest.raises(RunAbortedError):
        await task

    assert 3 <= run.completed < 50
    measured = [v for v in run.data if v is not None]
    assert len(measured) == run.completed
    assert run.data[0] == 0.0


async def test_aborting_tells_the_stage_to_stop_rather_than_only_the_loop():
    """The half of abort that reaches hardware. Cancelling the task ends
    the software loop; a stage commanded to a position keeps travelling
    there, so the sample was still moving after the run reported stopped."""
    session = await _session(stage="mock_basic_actuator_nd")
    stopped: list[str] = []

    class _Recording:
        def __init__(self, inner):
            self._inner = inner

        async def stop(self):
            stopped.append("stage")

        def __getattr__(self, name):
            return getattr(self._inner, name)

    session.devices["stage"] = _Recording(session.devices["stage"])
    descriptor = RunDescriptor(
        run_uid="u", plan_name="p",
        axes=(Axis("x", np.zeros(10), kind="actuator", device="stage"),),
        scan_axis_count=1,
    )
    run = Run(descriptor, session)
    points = _CountingPoints(descriptor)

    task = asyncio.create_task(run.execute(points.__aiter__()))
    while run.completed < 2:
        await asyncio.sleep(0)
    run.abort()
    with pytest.raises(RunAbortedError):
        await task

    assert stopped == ["stage"], "the actuator was never told to stop"


async def test_a_motor_with_no_halt_command_is_stopped_by_holding_position():
    """Measured across the registry: essentially no adapter declares a stop
    action, so the fallback is what actually runs. Re-commanding the
    current position supersedes the setpoint in flight, which is how a
    controller without a halt command is stopped."""
    session = await _session(stage="mock_basic_actuator_nd")
    stage = session.get("stage")
    await stage.move_abs(x=1.0, y=0.0, z=0.0)

    await stage.stop()

    position = await stage.get_position()
    assert position["x"] == pytest.approx(1.0, abs=0.05)


async def test_an_aborted_scan_still_unstages_the_detector():
    """A detector left staged after an abort is an integrating sensor still
    integrating, and the next run inherits it."""
    session = await _session(stage="mock_basic_actuator_nd", detector="mock_basic_detector_1d")
    detector = session.devices["detector"]
    plan = ScanPlan([ScanAxis("x", "stage", 0.0, 1.0, 20)], detector="detector")
    run = await prepare(session, plan)

    task = asyncio.create_task(run.execute(plan.points(session, run.descriptor)))
    while run.completed < 2:
        await asyncio.sleep(0.01)
    run.abort()
    with pytest.raises(RunAbortedError):
        await task

    assert not getattr(detector, "_staged", False)


# --- The template that was rewritten onto a plan --------------------------


async def _run_omniscan(**roles: str) -> tuple[dict, dict]:
    """omniscan on a 2x3 grid, returning its result and its last frame."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "src/labpilot/core/workflow_templates/omniscan.py"
    )
    spec = importlib.util.spec_from_file_location("omniscan_under_test", path)
    template = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(template)
    template.SCAN_AXES = ["x", "y"]
    template.AXIS_RANGES = {"x": (-1.0, 1.0, 2), "y": (-1.0, 1.0, 3)}

    session = await _session(**roles)
    sink: dict = {}
    session.set_progress_context("wf", "exec", sink)
    result = await template.run(session)
    return result, sink.get("wf", {})


async def test_omniscan_on_a_plan_returns_what_it_returned_before():
    """The template lost ~100 executable statements — the block that
    discovered its own result's size on the first callback and allocated
    mid-flight. What it returns is unchanged, which is the whole claim:
    the Qt views, the React client, `pick_view` and the HDF5 writer see
    exactly what they saw."""
    result, frame = await _run_omniscan(
        actuator="mock_basic_actuator_nd", detector="mock_basic_detector_1d"
    )

    assert result["axis_names"][:2] == ["x", "y"]
    assert result["shape"][:2] == [2, 3]
    assert result["actuator_axis_count"] == 2
    assert result["axis_units"]["x"] == "mm"
    assert len(result["data"]) == int(np.prod(result["shape"]))
    assert not any(value is None for value in result["data"])
    # The roles that produced it still travel with the result, for the
    # provenance recorded in the saved file.
    assert result["actuator"] == "actuator"
    assert set(frame) >= {"data", "shape", "axis_names", "completed", "total"}


async def test_omniscans_hardware_timed_path_still_works_and_now_streams():
    """The scanner path used to re-publish the whole accumulated frame on
    every poll. It yields the samples that arrived since the last one."""
    result, frame = await _run_omniscan(scanner="mock_ni_scanner")

    assert result["shape"] == [2, 3]
    assert result["axis_names"] == ["x", "y"]
    assert result["scanner"] == "scanner"
    assert not any(value is None for value in result["data"])
    assert frame["completed"] == frame["total"] == 6


# --- Refusing an impossible run -------------------------------------------


async def test_an_oversized_grid_is_refused_before_anything_moves():
    """A misconfigured point count used to allocate a multi-billion-element
    array and thrash memory, looking like a hang rather than a bad config."""
    session = await _session(stage="mock_basic_actuator_nd", detector="mock_basic_detector_0d")
    plan = ScanPlan(
        [ScanAxis(name, "stage", 0.0, 1.0, 100) for name in ("x", "y", "z")],
        detector="detector",
    )
    with pytest.raises(ValueError, match="safety limit"):
        await plan.describe(session)
