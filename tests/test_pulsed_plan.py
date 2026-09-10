"""`PulsedMeasurementPlan` — the run that drives a pulsed rig.

The claim being pinned is that a pulsed measurement needed *no* new
engine. It is a `Plan` like every other, and pause, abort, patch
streaming and a descriptor with real coordinates come from `Run` — which
is only possible because the sequence knows its own sweep and the
analysis method declares its own units, so `describe()` can answer
before the pulser is touched.

The second claim is about shape. Nothing moves between points: the whole
sweep plays in a few hundred microseconds and every point of the curve
improves together. So the axis this plan iterates is **accumulation**,
and the result is a 2-D `(sweeps, tau)` history whose last row is the
answer. These check that the history is real rather than the same curve
written twenty times.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.analysis.fits import fit_rabi
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.run.plans import PulsedMeasurementPlan
from labpilot.core.run.run import Run, RunAbortedError
from labpilot.core.session import Session
from labpilot.instruments import adapter_registry

pytestmark = pytest.mark.anyio

#: The mock rig's physical channels. Symbolic names never reach a driver.
CHANNELS = {"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def rig(**sample: float | str) -> Session:
    session = Session()
    for role, key in (("pulser", "mock_pulser"), ("counter", "mock_gated_counter")):
        adapter = adapter_registry.get(key)()
        await adapter.connect()
        session.register(adapter, role)
    if sample:
        await session.get("counter").write(dict(sample))
    return session


def rabi(points: int = 20) -> object:
    return build("rabi", RigProfile(), tau_start=10e-9, tau_step=10e-9, points=points)


def plan(sequence: object = None, **kwargs) -> PulsedMeasurementPlan:
    return PulsedMeasurementPlan(
        sequence if sequence is not None else rabi(),
        channels=CHANNELS, bin_width=8e-9,
        **{"sweeps": 200, "checkpoints": 4, **kwargs},
    )


# --- Everything knowable before the first readout ---------------------------


async def test_describe_states_the_sweep_before_any_hardware_is_touched():
    """The whole reason this is a plan. Qudi's pulsed measurement logic
    configures its x-axis from a side-channel dict handed over after
    generation, which is why it needs its own engine."""
    session = await rig()
    sequence = rabi(20)
    descriptor = await plan(sequence).describe(session)

    sweeps, tau = descriptor.axes
    assert tau.name == "tau"
    assert tau.unit == "s"
    assert len(tau) == 20
    assert tau.values == pytest.approx(sequence.sweep.array)
    assert sweeps.name == "sweeps"


async def test_the_iterated_axis_is_accumulation_not_position():
    """Nothing moves between points, so `points` counts checkpoints and
    every one of them delivers the whole curve."""
    descriptor = await plan(checkpoints=5).describe(await rig())
    assert descriptor.scan_axis_count == 1
    assert descriptor.points == 5
    assert descriptor.per_point == 20
    assert descriptor.shape == (5, 20)


async def test_nothing_in_this_run_is_movable():
    """No crosshair, and nothing for `abort` to drive to a stop — the
    plan's own `finally` closes the laser gate instead."""
    descriptor = await plan().describe(await rig())
    assert descriptor.actuator_axis_count == 0
    assert descriptor.actuators == ()


async def test_the_value_name_and_unit_come_from_the_analysis_method():
    """Declared rather than returned, so they are known with no readout
    yet in existence."""
    session = await rig()
    normalised = await plan(analyse="mean_norm").describe(session)
    assert normalised.value_name == "normalised fluorescence"
    assert normalised.value_unit == ""

    raw = await plan(analyse="mean").describe(session)
    assert raw.value_unit == "counts/bin"


async def test_auto_picks_the_method_from_the_sequence():
    """A Rabi has one readout per point; a Ramsey has two. A fixed
    default would be wrong for half the experiments."""
    assert plan(rabi()).method == "mean_norm"
    assert plan(build("ramsey", RigProfile(), points=8)).method == "mean_reference"


async def test_the_descriptor_carries_the_sequence_as_provenance():
    descriptor = await plan().describe(await rig())
    assert descriptor.params["sequence"] == "rabi"
    assert descriptor.params["readouts"] == 20
    assert descriptor.params["analyse"] == "mean_norm"
    assert set(descriptor.devices) == {"pulser", "counter"}


async def test_an_unplayable_sequence_is_refused_before_the_pulser_sees_it():
    from labpilot.core.pulse import PulseBlock, PulseElement, PulseSequence, SequenceError

    broken = PulseSequence(
        "broken",
        (PulseBlock("b", (PulseElement(1e-6, {"mw": True}),)),),
    )
    with pytest.raises(SequenceError):
        await plan(broken).describe(await rig())


# --- Checkpoints ------------------------------------------------------------


def test_checkpoints_are_evenly_spaced_and_end_on_the_last_sweep():
    assert plan(sweeps=100, checkpoints=4).checkpoint_sweeps == (25, 50, 75, 100)


def test_more_checkpoints_than_sweeps_records_each_sweep_once():
    """Rather than writing the same trace twice under two labels."""
    assert plan(sweeps=3, checkpoints=20).checkpoint_sweeps == (1, 2, 3)


def test_one_checkpoint_records_only_the_finished_measurement():
    assert plan(sweeps=500, checkpoints=1).checkpoint_sweeps == (500,)


def test_the_record_length_is_derived_from_the_sequence():
    """Longer than the readout window, so the record holds dark bins
    either side for extraction to find its edges in."""
    sequence = rabi()
    derived = plan(sequence).record_length_s
    assert derived > sequence.readout_window()
    assert plan(sequence, record_length=9e-6).record_length_s == 9e-6


# --- Running it -------------------------------------------------------------


async def test_a_run_streams_one_patch_per_checkpoint():
    session = await rig()
    measurement = plan(checkpoints=3, sweeps=60)
    descriptor = await measurement.describe(session)

    patches = [p async for p in measurement.points(session, descriptor)]
    assert len(patches) == 3
    assert [p.index for p in patches] == [0, 20, 40]
    assert all(p.size == 20 for p in patches)


async def test_the_result_is_an_accumulation_history_not_one_curve():
    """Each row is the analysed curve after that many sweeps, so a saved
    file shows whether the measurement had converged."""
    session = await rig(bright_rate=4e8)
    measurement = plan(checkpoints=4, sweeps=400)
    descriptor = await measurement.describe(session)
    result = await Run(descriptor, session).execute(
        measurement.points(session, descriptor)
    )

    data = np.asarray(result["data"], dtype=float).reshape(descriptor.shape)
    assert data.shape == (4, 20)
    assert np.isfinite(data).all()
    # Not the same curve four times: the error bars shrink as counts
    # accumulate, so the rows differ.
    assert not np.allclose(data[0], data[-1])


async def test_a_rabi_recovers_the_period_that_was_injected():
    """The end-to-end claim: sequence -> pulser -> counter -> extraction
    -> analysis -> fit, with the answer known because the simulated
    sample was told what to be."""
    session = await rig(
        experiment="rabi", rabi_period=200e-9, contrast=0.3, bright_rate=4e8
    )
    sequence = build("rabi", RigProfile(), tau_start=10e-9, tau_step=10e-9, points=40)
    measurement = plan(sequence, sweeps=800, checkpoints=2)
    descriptor = await measurement.describe(session)
    result = await Run(descriptor, session).execute(
        measurement.points(session, descriptor)
    )

    curve = np.asarray(result["data"], dtype=float).reshape(descriptor.shape)[-1]
    fit = fit_rabi(descriptor.axes[1].values, curve)
    assert fit is not None
    assert fit["period"] == pytest.approx(200e-9, rel=0.1)
    assert fit["pi_pulse"] == pytest.approx(fit["period"] / 2)


async def test_the_extraction_found_the_mock_s_own_laser_pulse():
    """The mock puts the pulse `gate_delay` into the record with dark
    counts either side, so this is a real edge rather than a window
    starting conveniently at bin zero."""
    session = await rig(bright_rate=4e8)
    counter = session.get("counter")
    measurement = plan(sweeps=100, checkpoints=1)
    descriptor = await measurement.describe(session)
    async for _ in measurement.points(session, descriptor):
        pass

    start, stop = measurement.extraction.window
    width = measurement.config.bin_width_s
    assert measurement.extraction.found
    assert start * width == pytest.approx(counter._adapter.gate_delay, abs=100e-9)
    assert (stop - start) * width == pytest.approx(
        measurement.sequence.readout_window(), rel=0.05
    )


async def test_what_the_run_reports_beyond_the_numbers():
    session = await rig(bright_rate=4e8)
    measurement = plan(sweeps=100, checkpoints=1)
    descriptor = await measurement.describe(session)
    async for _ in measurement.points(session, descriptor):
        pass

    report = measurement.result
    assert report["pulser"]["readouts"] == 20
    assert report["counter"]["bin_width_s"] == 8e-9
    assert report["extraction"]["found"] is True
    assert len(report["analysis"]["values"]) == 20
    assert len(report["analysis"]["errors"]) == 20


# --- Stopping ---------------------------------------------------------------


async def test_an_abort_leaves_the_pulser_off_and_the_counter_stopped():
    """The one thing a pulsed abort must get right: a sample left under
    continuous illumination bleaches."""
    session = await rig(bright_rate=4e8)
    measurement = plan(sweeps=400, checkpoints=8)
    descriptor = await measurement.describe(session)
    run = Run(descriptor, session)
    run.abort()

    with pytest.raises(RunAbortedError):
        await run.execute(measurement.points(session, descriptor))

    assert (await session.get("pulser").read())["running"] is False
    assert (await session.get("counter").counter_status())["running"] is False


async def test_an_abort_keeps_the_checkpoints_already_measured():
    session = await rig(bright_rate=4e8)
    measurement = plan(sweeps=400, checkpoints=8)
    descriptor = await measurement.describe(session)
    run = Run(descriptor, session)
    run.abort()

    with pytest.raises(RunAbortedError):
        await run.execute(measurement.points(session, descriptor))

    assert run.completed == 1
    assert run.data[0] is not None
    assert run.data[-1] is None


async def test_a_counter_that_never_advances_says_which_cable_to_check():
    """Otherwise a pulser that failed to start looks exactly like a slow
    measurement, and looks like it forever."""

    class Stuck:
        async def counter_status(self) -> dict:
            return {"running": True, "sweeps": 0}

    measurement = plan(stall_timeout=0.05, poll_interval=0.01)
    with pytest.raises(RuntimeError, match="gate channel"):
        await measurement._accumulate(Stuck(), target=10)


async def test_a_short_trace_leaves_a_gap_rather_than_shifting_the_row():
    """A patch narrower than the sweep would silently shift every later
    row of the result by the shortfall."""
    from labpilot.core.run.plans import _fit_to

    assert np.isnan(_fit_to(np.array([1.0, 2.0]), 4)[2:]).all()
    assert _fit_to(np.array([1.0, 2.0]), 4)[:2] == pytest.approx([1.0, 2.0])


# --- The rest of the rig ----------------------------------------------------


async def source(session: Session) -> Session:
    adapter = adapter_registry.get("mock_microwave_source")()
    await adapter.connect()
    session.register(adapter, "microwave")
    return session


async def test_a_microwave_source_is_switched_on_and_off_around_the_run():
    """By its own declared action, not by a settable named `output`.
    `Source` has no generic enable/disable precisely because real
    sources disagree about which of the two they offer."""
    session = await source(await rig(bright_rate=4e8))

    measurement = plan(microwave="microwave", sweeps=60, checkpoints=1)
    descriptor = await measurement.describe(session)
    seen = []
    async for _ in measurement.points(session, descriptor):
        seen.append((await session.get("microwave").read())["output_on"])

    assert seen == [True]
    assert (await session.get("microwave").read())["output_on"] is False
    assert "microwave" in descriptor.devices


async def test_an_action_the_source_does_not_have_says_which_it_does():
    """Rather than a list of plausible names tried in turn — the failure
    mode being a run that measures nothing and reports success."""
    session = await source(await rig(bright_rate=4e8))
    measurement = plan(microwave="microwave", microwave_on="enable_rf", checkpoints=1)
    descriptor = await measurement.describe(session)

    with pytest.raises(ValueError, match="cw_on"):
        async for _ in measurement.points(session, descriptor):
            pass


async def test_a_source_that_declares_no_actions_at_all_is_left_alone():
    """The ordinary digital rig: the source runs continuously and the
    pulser gates it, so there is nothing to switch. Distinguished from a
    wrong action name, which is refused above."""
    session = await rig(bright_rate=4e8)
    plain = adapter_registry.get("mock_basic_source")()
    await plain.connect()
    session.register(plain, "microwave")

    measurement = plan(microwave="microwave", sweeps=60, checkpoints=1)
    descriptor = await measurement.describe(session)
    patches = [p async for p in measurement.points(session, descriptor)]
    assert len(patches) == 1


async def test_switching_can_be_turned_off_explicitly():
    session = await source(await rig(bright_rate=4e8))
    measurement = plan(
        microwave="microwave", microwave_on="", microwave_off="",
        sweeps=60, checkpoints=1,
    )
    descriptor = await measurement.describe(session)
    async for _ in measurement.points(session, descriptor):
        pass

    assert (await session.get("microwave").read())["output_on"] is False


async def test_a_role_that_is_not_bound_is_simply_not_driven():
    session = await rig(bright_rate=4e8)
    measurement = plan(microwave="microwave", laser="laser", sweeps=60, checkpoints=1)
    descriptor = await measurement.describe(session)
    assert set(descriptor.devices) == {"pulser", "counter"}

    patches = [p async for p in measurement.points(session, descriptor)]
    assert len(patches) == 1
