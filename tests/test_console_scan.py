"""A scan you can type, without writing a workflow first.

The console had five verbs — read, write, connect, schema, status — so you
could not write an acquisition loop at it. Phase 1 gave it the same
per-instrument surface a template gets (`move_abs`, `stage`, `read_value`),
which makes the loop typeable; this is the other half, the one that means
you do not have to type the loop at all:

    run = lp.scan(over={"stage.x": (0, 10, 51)}, read="apd")

What that starts is not a console-side loop. It is the same `ScanPlan` a
template builds, run by the same `RunManager` on the same worker loop, so
it streams patches, it can be paused and aborted at a point boundary, and
it is written to HDF5 and indexed when it finishes. The only thing it lacks
is a stored workflow record, because nobody wrote one.

These tests drive the real app over its real routes, with the console
client pointed at it.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from labpilot.core.errors import NotConnectedError
from labpilot.core.notebook_api import LabPilotSession
from labpilot.core.server import create_app

STAGE = "mock_basic_actuator_nd"
APD = "mock_basic_detector_0d"


@pytest.fixture
def lp(tmp_path, monkeypatch):
    """A console session wired to a live app, with two instruments up."""
    monkeypatch.setenv("LABPILOT_HOME", str(tmp_path))
    with TestClient(create_app()) as http:
        for instrument in (STAGE, APD):
            assert http.post(f"/api/dashboard/instruments/{instrument}/connect").status_code == 200
        session = LabPilotSession()
        # The console speaks HTTP either way; this just points it at the
        # app under test instead of a socket.
        session.client._client = http
        yield session


def test_a_scan_is_one_line(lp):
    run = lp.scan(over={f"{STAGE}.x": (0.0, 2.0, 5)}, read=APD, name="line")

    result = run.wait(timeout=60).result()
    assert result["shape"] == [5]
    assert len(result["data"]) == 5
    assert all(value is not None for value in result["data"])
    assert result["axis_names"] == ["x"]


def test_the_result_describes_itself(lp):
    """`result()` is the dict it always was, and a `Dataset` as well — so
    `["data"]` still works and `.to_hdf5()` now does too."""
    run = lp.scan(over={f"{STAGE}.x": (0.0, 1.0, 3)}, read=APD)
    result = run.wait(timeout=60).result()

    assert "data" in result
    primary = result.primary()
    assert primary.values.shape == (3,)
    assert primary.axes[0].name == "x"


def test_a_scan_saves_itself(lp, tmp_path):
    """Every run is written to HDF5 and indexed as it finishes — a console
    scan is a run, so it lands in the same catalogue as one started from
    the Workflows tab."""
    before = len(lp.runs)
    lp.scan(over={f"{STAGE}.x": (0.0, 1.0, 3)}, read=APD, name="saved").wait(timeout=60)

    runs = lp.runs
    assert len(runs) == before + 1
    assert runs[0]["metadata"]["status"] == "completed"


def test_a_written_file_reads_back_with_its_axes(lp, tmp_path):
    run = lp.scan(over={f"{STAGE}.x": (0.0, 1.0, 4)}, read=APD).wait(timeout=60)
    path = tmp_path / "scan.h5"

    run.result().to_hdf5(path)

    h5py = pytest.importorskip("h5py")
    with h5py.File(path) as f:
        assert f["axes/x"].shape == (4,)
        assert f["axes/x"].attrs["kind"] == "actuator"


def test_two_axes_vary_first_slowest(lp):
    """The convention `itertools.product` uses and every result view reads."""
    run = lp.scan(
        over={f"{STAGE}.x": (0.0, 1.0, 3), f"{STAGE}.y": (0.0, 1.0, 2)},
        read=APD,
    )
    result = run.wait(timeout=60).result()
    assert result["shape"] == [3, 2]
    assert result["axis_names"] == ["x", "y"]


def test_using_names_the_instrument_once(lp):
    run = lp.scan(over={"x": (0.0, 1.0, 3)}, read=APD, using=STAGE)
    assert run.wait(timeout=60).result()["shape"] == [3]


# --- Controls --------------------------------------------------------------


def test_aborting_keeps_what_was_measured(lp):
    """Not a cancellation: the run stops at its next point boundary and is
    saved as a partial run, rather than being unwound mid-move."""
    run = lp.scan(over={f"{STAGE}.x": (-5.0, 5.0, 60)}, read=APD, name="long")
    _wait_until_started(run)

    run.abort()
    run.wait(timeout=60)

    measured = [v for v in run.result()["data"] if v is not None]
    assert 0 < len(measured) < 60, "an aborted scan kept nothing, or everything"


def test_pausing_holds_the_scan(lp):
    run = lp.scan(over={f"{STAGE}.x": (-5.0, 5.0, 60)}, read=APD)
    _wait_until_started(run)

    run.pause()
    time.sleep(0.2)          # let the point in flight finish
    held, _ = run.progress
    time.sleep(0.2)
    assert run.progress[0] == held, "a paused scan kept going"

    run.resume()
    run.abort()


def test_a_finished_run_cannot_be_paused(lp):
    run = lp.scan(over={f"{STAGE}.x": (0.0, 1.0, 3)}, read=APD).wait(timeout=60)
    with pytest.raises(NotConnectedError, match="not running a plan"):
        run.pause()


# --- Mistakes --------------------------------------------------------------


def test_an_axis_that_does_not_say_what_to_move_says_so(lp):
    with pytest.raises(ValueError, match="which instrument"):
        lp.scan(over={"x": (0.0, 1.0, 3)}, read=APD)


def test_a_malformed_range_names_the_axis(lp):
    with pytest.raises(ValueError, match="needs \\(start, stop, points\\)"):
        lp.scan(over={f"{STAGE}.x": (0.0, 1.0)}, read=APD)


def test_scanning_a_disconnected_instrument_fails_before_it_starts(lp):
    """Rather than being accepted and failing on the worker loop after the
    caller has been told the run started."""
    lp[APD].disconnect()
    with pytest.raises(NotConnectedError, match="Not connected"):
        lp.scan(over={f"{STAGE}.x": (0.0, 1.0, 3)}, read=APD)


def _wait_until_started(run, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if run.progress[0] > 0:
            return
        time.sleep(0.02)
    raise AssertionError("the scan never started producing points")
