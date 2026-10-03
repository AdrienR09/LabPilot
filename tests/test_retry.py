"""Surviving hardware that refuses mid-run.

The only place a mock rig and a real one differ in kind: a mock detector
always answers. Everything here uses a detector that does not, because
that is the behaviour there is otherwise no way to exercise before the
instrument is on the bench — and the failure it guards against (six hours
of scan lost to one VISA timeout at hour five) is expensive exactly once.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from labpilot.core.run import ScanAxis, ScanPlan, execute
from labpilot.core.run.retry import RetryPolicy, attempt
from labpilot.core.run.run import RunAbortedError
from labpilot.core.session import Session
from labpilot.instruments import adapter_registry

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- The policy on its own -------------------------------------------------


async def test_a_call_that_succeeds_is_not_retried():
    calls = []

    async def work():
        calls.append(1)
        return "ok"

    assert await attempt(RetryPolicy(), work) == ("ok", None)
    assert len(calls) == 1


async def test_a_transient_failure_is_retried_and_then_succeeds():
    calls = []

    async def work():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("instrument busy")
        return "ok"

    value, failure = await attempt(RetryPolicy(attempts=3, backoff=0), work)
    assert (value, failure) == ("ok", None)
    assert len(calls) == 3


async def test_exhausting_the_attempts_reports_when_told_to_skip():
    async def work():
        raise TimeoutError("gone")

    value, failure = await attempt(
        RetryPolicy(attempts=2, backoff=0, on_failure="skip"), work
    )
    assert value is None
    assert isinstance(failure, TimeoutError)


async def test_the_default_is_to_raise_once_the_attempts_are_gone():
    """The pre-existing contract, kept deliberately: a failure nobody sees
    is worse than a run that stops. Skipping is opt-in."""
    assert RetryPolicy().on_failure == "abort"

    async def work():
        raise TimeoutError("gone")

    with pytest.raises(TimeoutError):
        await attempt(RetryPolicy(attempts=2, backoff=0), work)


async def test_attempts_of_one_means_no_retry():
    calls = []

    async def work():
        calls.append(1)
        raise TimeoutError("gone")

    await attempt(
        RetryPolicy(attempts=1, backoff=0, on_failure="skip"), work
    )
    assert len(calls) == 1


@pytest.mark.parametrize("fatal", [TypeError, AttributeError, NameError])
async def test_a_programming_error_is_never_retried(fatal):
    """A `TypeError` in the point loop is a bug in the script and will not
    come good on the third try; retrying only makes a clear failure slow."""
    calls = []

    async def work():
        calls.append(1)
        raise fatal("typo")

    with pytest.raises(fatal):
        await attempt(RetryPolicy(attempts=3, backoff=0), work)
    assert len(calls) == 1


async def test_a_user_abort_is_never_retried():
    """Retrying it would ignore someone who pressed Stop."""
    async def work():
        raise RunAbortedError("stopped")

    with pytest.raises(RunAbortedError):
        await attempt(RetryPolicy(attempts=3, backoff=0), work)


async def test_cancellation_passes_straight_through():
    async def work():
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await attempt(RetryPolicy(attempts=3, backoff=0), work)


def test_backoff_doubles():
    policy = RetryPolicy(backoff=0.5)
    assert [policy.delay(n) for n in (1, 2, 3)] == [0.5, 1.0, 2.0]


# --- A scan against a detector that fails ----------------------------------


class _Flaky:
    """Wraps a real mock detector and refuses on chosen reads."""

    def __init__(self, inner, fail_on: set[int], transient: bool = False):
        self._inner = inner
        self._fail_on = set(fail_on)
        self._transient = transient
        self.reads = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def read(self):
        self.reads += 1
        if self.reads in self._fail_on:
            if self._transient:
                self._fail_on.discard(self.reads)
            raise TimeoutError(f"read {self.reads} timed out")
        return await self._inner.read()


async def _rig(fail_on, transient=False) -> tuple[Session, _Flaky]:
    session = Session()
    actuator = adapter_registry.get("mock_basic_actuator_nd")()
    await actuator.connect()
    session.register(actuator, "actuator")

    detector = adapter_registry.get("mock_basic_detector_0d")()
    await detector.connect()
    flaky = _Flaky(detector, fail_on, transient)
    session.register(flaky, "detector")
    return session, flaky


def _plan(**kwargs) -> ScanPlan:
    return ScanPlan(
        axes=[ScanAxis("x", "actuator", 0.0, 1.0, 4)],
        detector="detector", name="scan", **kwargs,
    )


#: `describe()` takes one reading to learn the detector's shape before any
#: point is acquired, so read 1 is always the probe and the grid starts at
#: read 2. Stated here rather than buried in each test's numbers.
PROBE = 1


async def test_a_scan_survives_a_transient_read_failure():
    """The whole point: one timeout must not cost the run."""
    session, _ = await _rig(fail_on={PROBE + 2}, transient=True)
    result = await execute(session, _plan(retry=RetryPolicy(backoff=0)))

    assert result["completed"] == 4
    assert all(v is not None for v in result["data"])
    assert "skipped_points" not in result


async def test_a_flaky_detector_does_not_fail_the_run_before_it_starts():
    """The probe is retried too. Without that, one timeout on the single
    read `describe()` takes would kill a scan at the worst moment — before
    anything had been measured to show it was worth starting."""
    session, _ = await _rig(fail_on={PROBE}, transient=True)
    result = await execute(session, _plan(retry=RetryPolicy(backoff=0)))
    assert result["completed"] == 4


async def test_a_detector_that_never_answers_cannot_be_described():
    """The shape of the result is not optional, so the probe is retried but
    never skipped."""
    session, _ = await _rig(fail_on=set(range(1, 100)))
    with pytest.raises(TimeoutError):
        await execute(session, _plan(retry=RetryPolicy(attempts=2, backoff=0)))


async def test_a_point_that_never_answers_is_skipped_not_fatal():
    session, _ = await _rig(fail_on=set(range(PROBE + 1, 100)))
    result = await execute(
        session,
        _plan(retry=RetryPolicy(attempts=2, backoff=0, on_failure="skip")),
    )

    assert result["skipped_points"] == 4
    assert all(v is None for v in result["data"])
    assert len(result["failures"]) == 4
    assert "TimeoutError" in result["failures"][0]["error"]
    assert result["failures"][0]["position"] == {"x": 0.0}


async def test_a_skipped_point_becomes_nan_in_the_dataset():
    session, _ = await _rig(fail_on={PROBE + 1})
    result = await execute(
        session,
        _plan(retry=RetryPolicy(attempts=1, backoff=0, on_failure="skip")),
    )
    values = np.asarray(
        [np.nan if v is None else v for v in result["data"]], dtype=float
    )
    assert np.isnan(values[0])
    assert not np.isnan(values[1:]).any()


async def test_abort_on_failure_stops_the_whole_run():
    session, _ = await _rig(fail_on=set(range(PROBE + 1, 100)))
    with pytest.raises(TimeoutError):
        await execute(
            session,
            _plan(retry=RetryPolicy(attempts=1, backoff=0, on_failure="abort")),
        )


async def test_the_failure_record_is_capped_but_the_count_is_not():
    """A detector that has died would otherwise record one entry per point
    for the rest of the grid; the first few say everything."""
    session = Session()
    for index in range(Session.MAX_RECORDED_FAILURES + 10):
        session.note_failure("uid", point=index)
    assert len(session.failures("uid")) == Session.MAX_RECORDED_FAILURES
    assert session.failure_count("uid") == Session.MAX_RECORDED_FAILURES + 10


async def test_failures_can_be_forgotten_so_a_session_does_not_grow():
    session = Session()
    session.note_failure("uid", point=0)
    session.forget_failures("uid")
    assert session.failures("uid") == []
    assert session.failure_count("uid") == 0
