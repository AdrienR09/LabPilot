"""The optimizer as a plan, and the two other shapes a run can take.

`OptimizerCapability` ran the optimize sequence itself: its own
move-and-read loop, its own progress callback, and no way to stop it
except cancelling the task — which left the sub-scan's detector staged and
the stage still travelling to the position it was last sent to.

As a plan it inherits what every run has: it stops at a point boundary, it
keeps the points it measured, and each of its sub-scans *is* a `ScanPlan`,
which is the "an optimizer is built on a scan" relationship as shared code
rather than as a docstring.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from labpilot.core.device.schema import DeviceSchema
from labpilot.core.run import (
    OptimizePlan,
    ScanAxis,
    ScanPlan,
    ScriptPlan,
    execute,
    prepare,
)
from labpilot.core.run.plans import decompose
from labpilot.core.run.run import Run, RunAbortedError
from labpilot.core.session import Session
from labpilot.instruments._base import AdapterBase

AXIS_RANGES = {"x": (-4.0, 4.0, 5), "y": (-4.0, 4.0, 5), "z": (-2.0, 2.0, 3)}
PEAK = {"x": 1.25, "y": -0.75, "z": 0.0}


class _Stage(AdapterBase):
    """A stage that arrives instantly and reports exactly where it is.

    Synthetic rather than a `MockBasic` mock on purpose: those share a
    simulated sample whose reading is noisy and drifts with time, which is
    right for exercising a scan end to end and wrong for asserting where a
    peak fit landed. Here the landscape is known exactly, so a fit either
    finds it or the test has found a real defect.
    """

    AXES = ("x", "y", "z")

    def __init__(self) -> None:
        super().__init__()
        self.position = dict.fromkeys(self.AXES, -3.0)

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name="stage", kind="motor",
            readable=dict.fromkeys(self.AXES, "float64"),
            settable=dict.fromkeys(self.AXES, "float64"),
            units=dict.fromkeys(self.AXES, "mm"),
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, float]:
        return dict(self.position)

    # `write()` dispatches to an awaitable `set_<key>`, the naming
    # convention every adapter follows (see instruments/_base.py).
    async def set_x(self, value: float) -> None:
        self.position["x"] = float(value)

    async def set_y(self, value: float) -> None:
        self.position["y"] = float(value)

    async def set_z(self, value: float) -> None:
        self.position["z"] = float(value)


class _Peak(AdapterBase):
    """A detector reading a Gaussian in the stage's position."""

    def __init__(self, stage: _Stage, *, ramp: bool = False) -> None:
        super().__init__()
        self._stage = stage
        self._ramp = ramp

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name="peak", kind="detector",
            readable={"counts": "float64"}, units={"counts": "counts"},
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, float]:
        if self._ramp:
            # A monotonic slope, never a peak — what a step that started
            # far off-target actually measures.
            return {"counts": 10.0 + self._stage.position["x"]}
        distance = sum(
            (self._stage.position[axis] - centre) ** 2 for axis, centre in PEAK.items()
        )
        return {"counts": float(np.exp(-distance / 2.0))}


async def _lab(*, ramp: bool = False) -> Session:
    session = Session()
    stage = _Stage()
    detector = _Peak(stage, ramp=ramp)
    for role, device in (("actuator", stage), ("detector", detector)):
        await device.connect()
        session.register(device, role)
    return session


def _plan(axes: list[str], **kwargs) -> OptimizePlan:
    kwargs.setdefault("points_per_axis", dict.fromkeys(axes, 3))
    return OptimizePlan(axes=axes, axis_ranges=AXIS_RANGES, **kwargs)


# --- Decomposition --------------------------------------------------------


def test_axes_decompose_into_at_most_two_dimensional_steps():
    """qudi's own confocal three-axis case. A genuine N-D peak fit exists
    here no more than it does there, so N axes are a sequence of 1-D and
    2-D sub-scans."""
    assert decompose(["x", "y", "z"]) == [("x", "y"), ("z",)]
    assert decompose(["x"]) == [("x",)]
    assert decompose(["a", "b", "c", "d"]) == [("a", "b"), ("c", "d")]


# --- What it knows before it runs ----------------------------------------


async def test_the_probe_points_are_counted_up_front():
    session = await _lab()
    descriptor = await _plan(["x", "y", "z"]).describe(session)

    # 3x3 for the (x, y) step, 3 for the (z,) step.
    assert descriptor.points == 12
    assert descriptor.per_point == 1


async def test_its_axis_is_a_point_index_because_the_coordinates_move():
    """Each step scans around the position the previous step's fit
    produced, so where step 2 will look is not knowable until step 1 has
    run. Saying so beats inventing coordinates that a fit then moves."""
    session = await _lab()
    descriptor = await _plan(["x", "y"]).describe(session)

    (axis,) = descriptor.axes
    assert axis.name == "point"
    assert axis.kind == "index"
    assert not axis.movable  # nothing to drag a crosshair along


# --- What it does ---------------------------------------------------------


async def test_it_centres_the_actuator_on_the_peak():
    session = await _lab()
    stage = session.get("actuator")
    await stage.move_abs(x=0.0, y=0.0, z=0.0)
    plan = _plan(["x", "y"], points_per_axis={"x": 9, "y": 9},
                 search_range={"x": 4.0, "y": 4.0})

    await execute(session, plan)

    assert plan.best_position["x"] == pytest.approx(PEAK["x"], abs=0.1)
    assert plan.best_position["y"] == pytest.approx(PEAK["y"], abs=0.1)
    # And the stage is left there: each step moves to its own fit centre
    # before the next one runs, which is what "re-centre" means.
    assert await stage.get_position("x") == pytest.approx(PEAK["x"], abs=0.1)


async def test_a_fit_centred_outside_the_window_it_scanned_is_refused():
    """A least-squares peak fit is unconstrained: given a slope rather than
    a peak it reports a centre far outside the window that was measured.
    Observed on the simulated sample — a sweep of x over [-4, 4] returning
    a centre of 21.65, which the optimizer then drove to, ending with less
    signal than it started with and the stage outside its declared range."""
    session = await _lab(ramp=True)
    stage = session.get("actuator")
    await stage.move_abs(x=0.0, y=0.0, z=0.0)
    plan = _plan(["x", "y"], points_per_axis={"x": 5, "y": 5})

    await execute(session, plan)

    assert plan.steps[0]["fit"] is None
    assert len(plan.steps) == 1, "a failed fit must stop the sequence"
    assert plan.best_position["x"] == pytest.approx(0.0, abs=0.05)
    # The stage is left where the scan reached, which is inside the window
    # it swept — not driven to a centre nothing measured.
    swept = plan.steps[0]["positions"][0]
    assert min(swept) <= await stage.get_position("x") <= max(swept)


async def test_each_step_reports_its_own_positions_and_its_fit():
    """What the optimizer panel renders, one pane per step — the payload
    shape is unchanged from the capability this replaces, so the Qt view
    needs no changes."""
    session = await _lab()
    frames: list[dict] = []

    async def on_step(payload: dict) -> None:
        frames.append(payload)

    await execute(session, _plan(["x", "y"], on_step=on_step))

    live = [f for f in frames if not f["done"]]
    finished = [f for f in frames if f["done"]]
    assert live and finished
    assert set(live[0]) >= {
        "step_index", "step_axes", "sequence", "positions", "shape",
        "values", "completed", "total",
    }
    assert set(finished[-1]) >= {"fit", "positions", "values", "shape"}
    assert finished[-1]["shape"] == [3, 3]
    assert len(finished[-1]["values"]) == 9


async def test_a_sub_scan_is_a_scan_plan():
    """Not a second implementation of move-and-read. The optimizer's own
    grid comes from `ScanPlan`, which is what made this worth doing."""
    session = await _lab()
    seen: list[str] = []
    original = ScanPlan.points

    def record(self, session, descriptor):
        seen.append(self.name)
        return original(self, session, descriptor)

    ScanPlan.points = record
    try:
        await execute(session, _plan(["x"]))
    finally:
        ScanPlan.points = original

    assert seen == ["optimize[0]"]


# --- Stopping it ----------------------------------------------------------


async def test_aborting_an_optimize_keeps_its_points_and_stops_the_stage():
    session = await _lab()
    stopped: list[str] = []

    class _Recording:
        def __init__(self, inner):
            self._inner = inner

        async def stop(self):
            stopped.append("actuator")

        def __getattr__(self, name):
            return getattr(self._inner, name)

    session.devices["actuator"] = _Recording(session.devices["actuator"])

    run: Run | None = None

    async def stop_after_three(payload: dict) -> None:
        # Asked for from inside the sequence, which is where a Stop
        # actually arrives: partway through, not between runs.
        if payload["completed"] >= 3 and run is not None:
            run.abort()

    plan = _plan(["x", "y", "z"], points_per_axis={"x": 5, "y": 5, "z": 5},
                 on_step=stop_after_three)
    run = await prepare(session, plan)

    with pytest.raises(RunAbortedError):
        await run.execute(plan.points(session, run.descriptor))

    measured = [v for v in run.data if v is not None]
    assert 0 < len(measured) < run.descriptor.points
    # The actuator is not left travelling to the last probe point.
    assert stopped == ["actuator"]


async def test_an_aborted_optimize_leaves_the_detector_unstaged():
    session = await _lab()
    detector = session.devices["detector"]
    run: Run | None = None

    async def stop_at_once(payload: dict) -> None:
        if run is not None:
            run.abort()

    plan = _plan(["x"], points_per_axis={"x": 25}, on_step=stop_at_once)
    run = await prepare(session, plan)

    with pytest.raises(RunAbortedError):
        await run.execute(plan.points(session, run.descriptor))

    assert not getattr(detector, "_staged", False)


def test_a_process_that_aborts_a_run_still_exits(tmp_path):
    """Stopping early leaves the plan's generator suspended at its yield,
    and an abandoned async generator is finalised whenever the loop gets
    round to it — at interpreter shutdown, in the worst case. Its `finally`
    is where the detector is unstaged, so "eventually" is the wrong time:
    this process was observed hanging at exit on a worker thread parked
    inside that never-finalised generator. Asserted on a real subprocess,
    because never exiting is the entire symptom."""
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        f"""
        import asyncio, sys
        sys.path.insert(0, {str(Path(__file__).parent)!r})
        import test_optimize_plan as t
        from labpilot.core.run import prepare
        from labpilot.core.run.run import RunAbortedError

        async def main():
            session = await t._lab()
            run = None
            async def stop_at_once(payload):
                run.abort()
            plan = t._plan(["x"], points_per_axis={{"x": 25}}, on_step=stop_at_once)
            run = await prepare(session, plan)
            try:
                await run.execute(plan.points(session, run.descriptor))
            except RunAbortedError:
                pass

        asyncio.run(main())
        """
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=90)


# --- The script escape hatch ----------------------------------------------


async def test_a_script_runs_through_the_same_entry_point(tmp_path):
    """"A workflow is a .py file with `async def run(session)`" is kept
    deliberately, so a plan object must not be the only way in."""
    script = tmp_path / "plain.py"
    script.write_text(
        "POINTS = 3\n"
        "async def run(session):\n"
        "    return {'points': POINTS}\n"
    )
    session = await _lab()

    result = await execute(session, ScriptPlan(str(script), params={"POINTS": 7}))

    assert result == {"points": 7}


async def test_a_script_plan_describes_what_can_be_known_without_running_it(tmp_path):
    script = tmp_path / "declares.py"
    script.write_text(
        'REQUIRED_INSTRUMENTS = {"detector": {"kind": "detector"}}\n'
        "AVERAGES = 4\n"
        "async def run(session):\n"
        "    return {}\n"
    )
    session = await _lab()

    descriptor = await ScriptPlan(str(script)).describe(session)

    assert descriptor.plan_name == "declares"
    assert descriptor.params["AVERAGES"] == 4
    assert "detector" in descriptor.devices
    # Not its shape: only the script knows that, and only once it has run.
    assert descriptor.axes == ()


# --- Following a run ------------------------------------------------------


async def test_a_run_can_be_followed_through_its_own_events():
    """One run's events, without filtering another's out by hand."""
    session = await _lab()
    session.set_progress_context("wf", "exec", {})
    plan = ScanPlan([ScanAxis("x", "actuator", -1.0, 1.0, 4)], detector="detector")
    run = await prepare(session, plan)

    seen: list[int] = []

    async def follow() -> None:
        async for event in run.events():
            if "completed" in (event.data or {}):
                seen.append(event.data["completed"])

    follower = asyncio.create_task(follow())
    while session.bus.subscriber_count() == 0:
        await asyncio.sleep(0)
    await run.execute(plan.points(session, run.descriptor))
    await asyncio.sleep(0.05)
    follower.cancel()

    assert seen[-1] == 4
    assert sorted(set(seen)) == [1, 2, 3, 4]


async def test_a_time_series_is_measured_in_values_not_patches():
    """A per-point plan yields one point per patch; a scanner delivers a
    burst per poll. Progress counts values either way."""
    from labpilot.core.data.dataset import Axis, DatasetPatch
    from labpilot.core.run.descriptor import RunDescriptor

    descriptor = RunDescriptor(
        run_uid="u", plan_name="burst",
        axes=(Axis("i", np.arange(4), kind="index"), Axis("ch", np.arange(2), kind="index")),
        scan_axis_count=1,
    )
    run = Run(descriptor, await _lab())

    async def bursts():
        yield DatasetPatch("data", 0, np.arange(4.0))  # two points at once
        yield DatasetPatch("data", 4, np.arange(4.0))

    await run.execute(bursts())

    assert run.completed == 4
    assert descriptor.per_point == 2
