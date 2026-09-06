"""The console's instrument surface, exercised against a real server.

`core/notebook_api.py` is what `lp` binds to in the IPython console. Its
handles are the remote half of the same API a workflow template gets from
`session.get(role)` (`core/device/kinds.py`), so what these tests are
really asserting is that the two halves agree: same method names, same
calling conventions, same settle rule.

The server is the real one, run in-process through `TestClient` (which is
an `httpx.Client`, so it drops straight into `LabPilotClient`), against
the mock instruments the dashboard seeds itself with. No route is
stubbed — a missing endpoint fails here rather than only in a live
console.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labpilot.core.device.kinds import Detector as InProcessDetector
from labpilot.core.device.kinds import Motor as InProcessMotor
from labpilot.core.notebook_api import Detector, LabPilotSession, Motor
from labpilot.core.server import create_app

ACTUATOR = "mock_basic_actuator_nd"
DETECTOR = "mock_basic_detector_0d"
# The 0D mock has no integration time at all (its one setting is an
# averaging count), so the tag lookup is exercised against the 1D one.
TIMED_DETECTOR = "mock_basic_detector_1d"


@pytest.fixture
def lab():
    """A LabPilotSession talking to a real in-process server."""
    with TestClient(create_app()) as http:
        session = LabPilotSession(base_url="http://testserver")
        session.client._client = http
        for instrument_id in (ACTUATOR, DETECTOR, TIMED_DETECTOR):
            session[instrument_id].connect()
        yield session


# --- The two transports offer the same API --------------------------------


@pytest.mark.parametrize(
    ("remote", "in_process"),
    [(Motor, InProcessMotor), (Detector, InProcessDetector)],
)
def test_the_remote_handle_offers_what_the_in_process_wrapper_does(remote, in_process):
    """A method that exists on one and not the other is a script that runs
    in a template but not at the console, or the reverse — which is the
    gap this whole surface exists to close."""
    expected = {
        name for name in vars(in_process)
        if not name.startswith("_")
    } | {"read", "write", "connect", "stage", "unstage", "schema"}
    missing = sorted(name for name in expected if not hasattr(remote, name))
    assert missing == []


# --- Motors ---------------------------------------------------------------


def test_move_abs_blocks_until_the_stage_has_arrived(lab):
    stage = lab[ACTUATOR]
    assert isinstance(stage, Motor)
    stage.move_abs(x=2.0, y=-1.0)
    assert stage.get_position("x") == pytest.approx(2.0, abs=0.05)
    assert stage.get_position("y") == pytest.approx(-1.0, abs=0.05)


def test_move_rel_is_relative_to_where_it_is(lab):
    stage = lab[ACTUATOR]
    stage.move_abs(x=1.0)
    stage.move_rel(x=2.0)
    assert stage.get_position("x") == pytest.approx(3.0, abs=0.05)


def test_a_stage_can_be_stopped_from_the_console(lab):
    """The console could read and write, so the only way to stop a stage
    running away was to kill the process. `stop()` decides how to stop
    server-side — a halt command, a declared action, or holding position —
    so the console and a workflow stop a device by the same rule."""
    stage = lab[ACTUATOR]
    stage.move_abs(x=2.0)

    stage.stop()

    assert stage.get_position("x") == pytest.approx(2.0, abs=0.05)


def test_axes_exclude_settings_that_are_not_positions(lab):
    """The ND mock declares a velocity alongside x/y/z. Offering it as a
    fourth axis is how `move_abs(5.0)` ends up refusing to work on a
    single-axis stage, and how a scan ends up sweeping a speed."""
    assert lab[ACTUATOR].axes == ["x", "y", "z"]


def test_a_multi_axis_move_by_bare_value_is_refused(lab):
    with pytest.raises(TypeError, match="exactly one axis"):
        lab[ACTUATOR].move_abs(1.0)


def test_get_position_without_an_axis_gives_every_axis(lab):
    stage = lab[ACTUATOR]
    stage.move_abs(x=0.0, y=0.0, z=0.0)
    position = stage.get_position()
    assert set(position) == {"x", "y", "z"}


# --- Detectors ------------------------------------------------------------


def test_read_value_gives_one_scalar(lab):
    assert isinstance(lab[DETECTOR].read_value(), float)


def test_stage_and_unstage_reach_the_adapter(lab):
    """These had no route at all, so an acquisition loop written at the
    console ran every point on an unstaged device."""
    detector = lab[DETECTOR]
    detector.stage()
    detector.unstage()


def test_acquire_once_brackets_the_read(lab):
    assert isinstance(lab[DETECTOR].acquire_once(), dict)


def test_set_integration_time_finds_however_the_device_spells_it(lab):
    """The caller says "integration time"; the device says
    `integration_time_ms`, or `exposure_ms`, or whatever it likes. The tag
    is the adapter's own declaration of which parameter that is."""
    detector = lab[TIMED_DETECTOR]
    detector.set_integration_time(25.0)
    assert detector.read() is not None


def test_a_detector_without_an_integration_time_says_so(lab):
    from labpilot.core.errors import UnsupportedOperationError

    with pytest.raises(UnsupportedOperationError):
        lab[DETECTOR].set_integration_time(25.0)


def test_an_out_of_range_setting_is_refused_by_the_device(lab):
    """Limits are enforced server-side, so the console gets the same
    rejection a workflow would — not a silent write to hardware, and not an
    httpx error whose message is a link to MDN's page on 422."""
    from labpilot.core.errors import ParameterError

    with pytest.raises(ParameterError) as excinfo:
        lab[TIMED_DETECTOR].set_integration_time(1e12)
    assert "outside the limits" in str(excinfo.value)
    assert excinfo.value.status_code == 422


def test_reading_a_disconnected_instrument_says_so(lab):
    detector = lab[DETECTOR]
    detector.disconnect()
    from labpilot.core.errors import NotConnectedError

    with pytest.raises(NotConnectedError):
        detector.read()


# --- Addressing -----------------------------------------------------------


def test_an_unknown_id_is_caught_with_a_suggestion(lab):
    """A registered id carries a numeric suffix, so reaching for the
    adapter's name is the common mistake; it used to surface as a bare 404
    naming a URL, from whichever method happened to be called first."""
    with pytest.raises(KeyError) as excinfo:
        lab["mock_basic_actuator_n"]
    assert ACTUATOR in str(excinfo.value)


def test_handles_are_typed_by_the_instrument_kind(lab):
    assert isinstance(lab[ACTUATOR], Motor)
    assert isinstance(lab[DETECTOR], Detector)
