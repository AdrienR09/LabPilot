"""Scan execution, against the path that actually runs.

These tests used to cover `core/plans/scan.py`: a bluesky-shaped async
generator emitting DESCRIPTOR -> READING -> STOP, reachable only through
`Session.run(plan)`, which no REST route, template or UI ever called. It
was the best-tested module in the repository and none of it ran — its
`anyio.CancelScope` cancellation check was a no-op in all three places it
appeared, and nothing noticed, because nothing executed it.

The guarantees it asserted are real guarantees, so they are kept and
pointed at `ScanPlan`/`Run`, which is what a scan runs on now. The dead
generator and its `ScanPlan` TOML model are deleted.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

from labpilot.core.events import EventKind
from labpilot.core.run import ScanAxis, ScanPlan, execute, prepare
from labpilot.core.session import Session
from labpilot.instruments.MockBasic.simple import (
    MockBasicActuatorND,
    MockBasicDetector0D,
)


class _Recording:
    """Wraps an adapter and records what it was told to do."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.writes: list[dict[str, Any]] = []
        self.staged: list[bool] = []

    async def write(self, values: dict[str, Any]) -> None:
        self.writes.append(dict(values))
        await self._inner.write(values)

    async def stage(self) -> None:
        self.staged.append(True)
        await self._inner.stage()

    async def unstage(self) -> None:
        self.staged.append(False)
        await self._inner.unstage()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


async def _lab(
    actuator: Any = None, detector: Any = None
) -> tuple[Session, _Recording, _Recording]:
    session = Session()
    stage = _Recording(actuator or MockBasicActuatorND())
    counter = _Recording(detector or MockBasicDetector0D())
    for name, device in (("actuator", stage), ("detector", counter)):
        await device.connect()
        session.register(device, name)
    return session, stage, counter


def _plan(start: float = 10.0, stop: float = 11.0, points: int = 5) -> ScanPlan:
    return ScanPlan(
        [ScanAxis("x", "actuator", start, stop, points)],
        detector="detector",
        name="test_scan",
    )


async def test_a_scan_visits_every_declared_position():
    session, stage, _ = await _lab()

    await execute(session, _plan())

    commanded = [write["x"] for write in stage.writes]
    np.testing.assert_allclose(commanded, np.linspace(10.0, 11.0, 5))


async def test_a_single_point_scan_is_one_point_at_the_start_position():
    session, stage, _ = await _lab()

    result = await execute(session, _plan(50.0, 50.0, 1))

    assert result["shape"] == [1]
    assert [write["x"] for write in stage.writes] == [50.0]
    assert len(result["data"]) == 1


async def test_the_detector_is_staged_for_the_scan_and_released_after_it():
    session, _, detector = await _lab()

    await execute(session, _plan(points=3))

    assert detector.staged == [True, False]


async def test_every_point_carries_the_same_run_uid():
    """One run, one identity — what the descriptor's `run_uid` is for, and
    what a client splicing patches together relies on."""
    session, _, _ = await _lab()
    plan = _plan(points=4)
    run = await prepare(session, plan)

    uids = {
        patch.run_uid async for patch in plan.points(session, run.descriptor)
    }

    assert uids == {run.descriptor.run_uid}
    assert run.descriptor.run_uid


async def test_the_run_reaches_the_event_bus():
    """A scan is watched from another process, so what it publishes is the
    product, not a side effect."""
    session, _, _ = await _lab()
    received: list[EventKind] = []

    async def subscriber() -> None:
        async for event in session.bus.subscribe(
            EventKind.READING, EventKind.WORKFLOW_PROGRESS
        ):
            received.append(event.kind)

    collector = asyncio.create_task(subscriber())
    while session.bus.subscriber_count() == 0:
        await asyncio.sleep(0)

    session.set_progress_context("wf", "exec", {})
    await execute(session, _plan(points=3))
    await asyncio.sleep(0.05)
    collector.cancel()

    assert received.count(EventKind.READING) == 3
    assert received.count(EventKind.WORKFLOW_PROGRESS) == 3


async def test_what_the_run_was_launched_with_travels_with_it():
    """The plan's own parameters and the schema of every device that took
    part — what makes a saved run reproducible rather than just numbers."""
    session, _, _ = await _lab()
    plan = _plan(points=3)
    plan.params = {"sample": "test_sample", "user": "alice"}

    run = await prepare(session, plan)

    assert run.descriptor.params["sample"] == "test_sample"
    assert set(run.descriptor.devices) == {"actuator", "detector"}
    assert "x" in run.descriptor.devices["actuator"]["readable"]


async def test_a_failing_actuator_stops_the_scan_and_says_why():
    class _Failing(MockBasicActuatorND):
        async def write(self, values: dict[str, Any]) -> None:
            raise RuntimeError("Motor hardware error")

    session, _, detector = await _lab(actuator=_Failing())

    with pytest.raises(RuntimeError, match="Motor hardware error"):
        await execute(session, _plan(points=3))

    # And the detector is not left armed by the failure.
    assert detector.staged == [True, False]


async def test_a_detector_that_cannot_be_read_fails_before_anything_is_armed():
    """Describing the run reads the detector once, so a detector that
    cannot be read at all fails there — before the scan stages hardware or
    moves a stage, rather than partway through a run."""
    class _Failing(MockBasicDetector0D):
        async def read(self) -> dict[str, Any]:
            raise RuntimeError("Detector read error")

    session, stage, detector = await _lab(detector=_Failing())

    with pytest.raises(RuntimeError, match="Detector read error"):
        await execute(session, _plan(points=3))

    assert detector.staged == []
    assert stage.writes == []


async def test_a_detector_that_fails_mid_scan_is_still_released():
    class _FailsLater(MockBasicDetector0D):
        reads = 0

        async def read(self) -> dict[str, Any]:
            type(self).reads += 1
            if type(self).reads > 2:  # one probe read, one point, then fail
                raise RuntimeError("Detector read error")
            return await super().read()

    session, _, detector = await _lab(detector=_FailsLater())

    with pytest.raises(RuntimeError, match="Detector read error"):
        await execute(session, _plan(points=3))

    assert detector.staged == [True, False]
