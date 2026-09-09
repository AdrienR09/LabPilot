"""Starting a plan from outside the server process.

`POST /api/runs/scan` could rebuild a `ScanPlan` and nothing else, and
`LabPilotSession.execute` rejected anything without `axes` and
`detector`. That wall was hit once by `HardwareTimedScanPlan` and again
by `PulsedMeasurementPlan`, so what these pin is that a plan type now
*declares* how it crosses the boundary and the route, the client and the
console all read that declaration — rather than each growing a branch.

The end-to-end half runs a real pulsed measurement over real HTTP
routes, with the console client pointed at the app.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from labpilot.core.notebook_api import LabPilotSession
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.run import (
    HardwareTimedScanPlan,
    PulsedMeasurementPlan,
    ScanAxis,
    ScanPlan,
    TimeSeriesPlan,
    build_plan,
    plan_devices,
    plan_request,
)
from labpilot.core.server import create_app

PULSER = "mock_pulser"
COUNTER = "mock_gated_counter"
CHANNELS = {"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"}


def rabi(points: int = 12):
    return build("rabi", RigProfile(), tau_start=10e-9, tau_step=10e-9, points=points)


# --- Both directions, for every plan that declares one ---------------------


def test_a_scan_survives_the_round_trip():
    original = ScanPlan(
        [ScanAxis("x", "stage", 0.0, 10.0, 51)], detector="apd", name="line",
    )
    name, params = plan_request(original)
    rebuilt = build_plan(name, params)

    assert name == "scan"
    assert rebuilt.detector == "apd"
    assert rebuilt.name == "line"
    assert [(a.name, a.device, a.points) for a in rebuilt.axes] == [("x", "stage", 51)]


def test_a_time_series_survives_the_round_trip():
    name, params = plan_request(TimeSeriesPlan(detector="apd", samples=17))
    rebuilt = build_plan(name, params)
    assert (name, rebuilt.samples, rebuilt.detector) == ("time_series", 17, "apd")


def test_a_pulsed_measurement_carries_its_whole_sequence():
    """The server has no copy: a console may have generated the sequence
    or loaded it from a file, and the run has to record which one."""
    sequence = rabi(20)
    original = PulsedMeasurementPlan(
        sequence, pulser="p", counter="c", channels=CHANNELS,
        sweeps=2000, checkpoints=5, analyse="mean_norm",
    )
    name, params = plan_request(original)
    rebuilt = build_plan(name, params)

    assert name == "pulsed"
    assert rebuilt.sequence.name == sequence.name
    assert rebuilt.sequence.points == sequence.points
    assert rebuilt.sequence.readouts() == sequence.readouts()
    assert rebuilt.sequence.duration == pytest.approx(sequence.duration)
    assert rebuilt.sequence.alternating == sequence.alternating
    assert rebuilt.channels == CHANNELS
    assert (rebuilt.sweeps, rebuilt.checkpoints) == (2000, 5)
    assert rebuilt.method == "mean_norm"


def test_the_request_is_json_and_nothing_else():
    """It crosses a process boundary; an object that only pickles would
    tie the console to the server's Python."""
    import json

    _, params = plan_request(
        PulsedMeasurementPlan(rabi(), pulser="p", counter="c", channels=CHANNELS)
    )
    assert json.loads(json.dumps(params))["sequence"]["name"] == "rabi"


def test_a_plan_with_no_transport_says_which_have_one():
    """`HardwareTimedScanPlan` is the one that hit this wall first, and
    still has no transport — the message has to say so rather than
    failing at the route."""
    with pytest.raises(TypeError, match="pulsed"):
        plan_request(HardwareTimedScanPlan([ScanAxis("x", "scanner", 0, 1, 8)]))


def test_an_unknown_plan_name_lists_the_real_ones():
    with pytest.raises(ValueError, match="scan"):
        build_plan("telepathy", {})


# --- What must be connected before the run is accepted ----------------------


def test_a_scan_needs_its_stage_and_its_detector():
    _, params = plan_request(
        ScanPlan([ScanAxis("x", "stage", 0, 1, 5)], detector="apd")
    )
    assert plan_devices("scan", params) == {"stage", "apd"}


def test_a_pulsed_run_needs_its_pulser_and_counter():
    _, params = plan_request(
        PulsedMeasurementPlan(rabi(), pulser="ps", counter="tt", channels=CHANNELS)
    )
    assert plan_devices("pulsed", params) == {"ps", "tt"}


def test_a_named_microwave_source_is_needed_too_and_a_laser_is_not():
    """The laser is recorded for provenance but never driven — on a
    pulsed rig the pulser gates it through an AOM."""
    _, params = plan_request(
        PulsedMeasurementPlan(
            rabi(), pulser="ps", counter="tt", microwave="mw", laser="green",
            channels=CHANNELS,
        )
    )
    assert plan_devices("pulsed", params) == {"ps", "tt", "mw"}


# --- Over the real routes ---------------------------------------------------


@pytest.fixture
def lp(tmp_path, monkeypatch):
    monkeypatch.setenv("LABPILOT_HOME", str(tmp_path))
    with TestClient(create_app()) as http:
        for adapter in (PULSER, COUNTER):
            # The dashboard manager outlives one app instance, so a
            # second test in this file finds these already created.
            created = http.post(
                "/api/dashboard/instruments",
                json={"adapter_key": adapter, "id": adapter, "name": adapter},
            )
            assert created.status_code in (201, 400), created.text
            connected = http.post(f"/api/dashboard/instruments/{adapter}/connect")
            assert connected.status_code == 200, connected.text
        session = LabPilotSession()
        session.client._client = http
        yield session


def test_a_pulsed_measurement_is_one_console_line(lp):
    """The end-to-end claim: a Rabi runs with no GUI and no workflow, and
    the editor is one way to drive it rather than the only way."""
    lp[COUNTER].write(
        experiment="rabi", rabi_period=200e-9, contrast=0.3, bright_rate=4e8
    )
    sequence = lp.pulse.rabi(tau=(10e-9, 400e-9, 40))
    run = lp.pulsed(
        sequence, pulser=PULSER, counter=COUNTER,
        sweeps=400, checkpoints=2, channels=CHANNELS, bin_width=8e-9,
    )

    result = run.wait(timeout=120).result()
    assert result["shape"] == [2, 40]
    assert result["axis_names"] == ["sweeps", "tau"]
    assert result["axis_units"]["tau"] == "s"

    from labpilot.core.analysis.fits import fit_rabi

    curve = np.asarray(result["data"], dtype=float).reshape(2, 40)[-1]
    fit = fit_rabi(result["axis_positions"][1], curve)
    assert fit is not None
    assert fit["period"] == pytest.approx(200e-9, rel=0.15)


def test_the_generators_run_in_the_console_s_own_process(lp):
    """A sequence is pure data — no hardware, no connection, no server —
    so it can be built and inspected before any pulser exists."""
    sequence = lp.pulse.ramsey(tau=(20e-9, 2e-6, 30), rabi_period=180e-9)
    assert sequence.points == 30
    assert sequence.alternating
    assert sequence.readouts() == 60


def test_tau_is_the_same_sugar_whichever_pair_the_generator_declares():
    """A linear sweep takes a step and a log-spaced one takes an
    endpoint; neither is something to remember at a console."""
    session = LabPilotSession()
    linear = session.pulse.rabi(tau=(10e-9, 100e-9, 10))
    logarithmic = session.pulse.t1(tau=(1e-6, 1e-3, 8))

    assert linear.sweep.values[0] == pytest.approx(10e-9)
    assert linear.sweep.values[-1] == pytest.approx(100e-9)
    assert logarithmic.sweep.values[0] == pytest.approx(1e-6)
    assert logarithmic.sweep.values[-1] == pytest.approx(1e-3)


def test_rig_physics_and_generator_settings_read_as_one_argument_list():
    sequence = LabPilotSession().pulse.rabi(
        tau=(10e-9, 100e-9, 10), rabi_period=120e-9, laser_length=2e-6
    )
    assert sequence.readout_window() == pytest.approx(2e-6)


def test_a_disconnected_instrument_is_refused_before_the_run_starts(lp):
    """Rather than on the worker loop, after the caller was told it
    started — which is how a missing counter becomes a run that reports
    success and measures nothing."""
    from labpilot.core.errors import NotConnectedError

    with pytest.raises(NotConnectedError, match="not_a_counter"):
        lp.pulsed(
            lp.pulse.rabi(tau=(10e-9, 100e-9, 8)),
            pulser=PULSER, counter="not_a_counter", channels=CHANNELS,
        )


def test_a_pulsed_run_can_be_stopped_from_the_console(lp):
    lp[COUNTER].write(bright_rate=4e8)
    run = lp.pulsed(
        lp.pulse.rabi(tau=(10e-9, 400e-9, 40)),
        pulser=PULSER, counter=COUNTER,
        sweeps=100_000, checkpoints=50, channels=CHANNELS, bin_width=8e-9,
    )
    deadline = time.time() + 30
    while run.progress[0] < 1 and time.time() < deadline:
        time.sleep(0.05)

    run.stop()
    assert run.wait(timeout=60).progress[0] < 50
