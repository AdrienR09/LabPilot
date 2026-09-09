"""The pulser and gated-counter contracts, and the simulated rig.

Three claims carry the design and are what these pin:

1. **The adapter owns its own format.** `upload_sequence` takes the
   abstract sequence, so a digital sequencer emits instructions and never
   builds an array. The counted difference is in
   `test_a_digital_sequencer_never_samples`.
2. **Negotiation happens where the constraints live.** The same sequence
   file uploaded to two pulsers with different timing grids reports two
   different quantisations rather than silently differing.
3. **What a device actually set is what the caller uses.**
   `configure_gates` returns the real bin width, and the simulated counter
   quantises like a real one.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from labpilot.core.device.capabilities import GATED_COUNTER, PULSER, capabilities_of
from labpilot.core.device.kinds import wrap
from labpilot.core.pulse import ChannelMap, PulseSequence, SamplingError, expand, sample
from labpilot.core.pulse.library import RigProfile, build
from labpilot.instruments import adapter_registry
from labpilot.instruments.gated_counter_mixin import BIN_WIDTH, GatedCounterMixin
from labpilot.instruments.pulser_mixin import PulserConstraints, PulserMixin

pytestmark = pytest.mark.anyio

ANALOG = ChannelMap({"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"})
DIGITAL = ChannelMap({"laser": "d_ch1", "mw": "d_ch3", "gate": "d_ch2"})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def make(key: str):
    adapter = adapter_registry.get(key)()
    await adapter.connect()
    return adapter


@pytest.fixture
async def pulser():
    return await make("mock_pulser")


@pytest.fixture
async def counter():
    return await make("mock_gated_counter")


def rabi(points: int = 20, analog: bool = True) -> PulseSequence:
    return build("rabi", RigProfile(analog_mw=analog), points=points)


# --- The contracts are visible outside the process ------------------------


@pytest.mark.parametrize(
    ("key", "capability"),
    [
        ("mock_pulser", PULSER),
        ("swabian_pulse_streamer", PULSER),
        ("spincore_pulse_blaster", PULSER),
        ("mock_gated_counter", GATED_COUNTER),
    ],
)
def test_every_pulsed_device_declares_its_capability(key, capability):
    """Composed off the MRO, so it reaches the schema, the REST payload and
    `ui_blocks.toml` — not just an `isinstance` at one call site."""
    assert capability in capabilities_of(adapter_registry.get(key))


@pytest.mark.parametrize(
    "key", ["mock_pulser", "swabian_pulse_streamer", "spincore_pulse_blaster"],
)
def test_a_pulser_describes_itself_without_hardware(key):
    """A vendor SDK that is not installed must not make the device
    invisible: the catalogue lists it and `search(tags=)` finds it on a
    machine that has never had one plugged in."""
    schema = adapter_registry.get(key).describe()
    assert schema is not None
    assert "Pulsed" in schema.tags

    constraints = adapter_registry.get(key)().pulser_constraints()
    assert isinstance(constraints, PulserConstraints)
    assert constraints.channels


async def test_the_wrapper_carries_the_contract(pulser, counter):
    """A device is not required to be exactly one thing, so the wrapper is
    composed from what it implements rather than picked by an if-chain."""
    assert hasattr(wrap(pulser), "upload_sequence")
    assert hasattr(wrap(counter), "configure_gates")
    # The counter is a detector *and* a gated counter, and keeps both.
    assert hasattr(wrap(counter), "read_value")


# --- Instructions, not samples --------------------------------------------


async def test_a_digital_sequencer_never_samples(pulser):
    """The number this whole design turns on. A 20-point T1 is 120
    instructions; sampled at 1 GS/s the same sequence is 17.5 million
    booleans, five million of them a single idle."""
    sequence = build("t1", RigProfile(analog_mw=False), points=20)
    report = await pulser.upload_sequence(sequence, DIGITAL)

    assert report.instructions == len(list(expand(sequence)))
    assert report.instructions < 200
    assert report.samples == 0
    # What the alternative would have cost.
    assert round(sequence.duration * 1e9) > 10_000_000


async def test_the_report_says_what_the_counter_should_expect(pulser):
    """The sequence knows its readout count before it runs, so the counter
    is configured from it rather than by hand."""
    sequence = rabi(points=25)
    report = await pulser.upload_sequence(sequence, ANALOG)
    assert report.readouts == sequence.readouts() == 25
    assert report.points == 25


async def test_the_report_records_the_resolved_channel_map(pulser):
    report = await pulser.upload_sequence(rabi(), ANALOG)
    assert report.channels == {"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"}


# --- Negotiation ----------------------------------------------------------


async def test_the_same_file_on_two_pulsers_reports_two_quantisations():
    """The case `Constraints.quantise` was built for: an 8 ns grid and a
    1 ns grid round the same 20 ns pi/2 pulse differently, and each device
    says so rather than silently differing."""
    sequence = rabi(points=10, analog=False)

    coarse = await make("mock_pulser")
    fine = adapter_registry.get("swabian_pulse_streamer")()
    fine_map = ChannelMap({"laser": "d_ch1", "mw": "d_ch3", "gate": "d_ch2"})

    on_coarse = await coarse.upload_sequence(sequence, DIGITAL)
    on_fine = await fine.upload_sequence(sequence, fine_map)

    assert not on_coarse.exact  # 8 ns grid: the 20 ns drive does not fit
    assert on_fine.exact  # 1 ns grid: it does
    assert "8 ns timing grid" in on_coarse.report()


async def test_an_element_below_the_minimum_is_refused_not_rounded(pulser):
    """A granularity mismatch is negotiable; a pulse the hardware cannot
    express is not."""
    from labpilot.core.pulse import PulseBlock, PulseElement

    block = PulseBlock("b", (
        PulseElement(2e-9, {"mw": True, "laser": False}, name="tip"),
        PulseElement(3e-6, {"laser": True, "gate": True}, name="readout"),
        PulseElement(1e-6, {"laser": False}, name="wait"),
    ))
    with pytest.raises(SamplingError, match="minimum"):
        await pulser.upload_sequence(PulseSequence("short", (block,)), DIGITAL)


async def test_a_sequence_that_fits_no_activation_config_is_refused(pulser):
    """The constraint a mock never punishes you for and a PulseBlaster
    will — so this mock punishes you for it."""
    sequence = rabi()
    # a_ch1 and a_ch2 together cost the last two digital lines, so this
    # map needs a set the device cannot enable at once.
    mapping = ChannelMap({"laser": "d_ch7", "mw": "a_ch1", "gate": "d_ch8"})
    with pytest.raises(SamplingError, match="active together"):
        await pulser.upload_sequence(sequence, mapping)


async def test_an_unmapped_channel_is_named_before_anything_is_compiled(pulser):
    with pytest.raises(Exception, match="gate"):
        await pulser.upload_sequence(rabi(), ChannelMap({"laser": "d_ch1", "mw": "a_ch1"}))


async def test_a_pulse_blaster_refuses_an_analog_drive():
    """It has no analog output, and producing a plausible measurement with
    no microwave in it is the worst available outcome."""
    board = adapter_registry.get("spincore_pulse_blaster")()
    with pytest.raises(SamplingError, match="analog_mw=False"):
        await board.upload_sequence(rabi(analog=True), ANALOG)


async def test_a_pulse_blaster_plays_the_same_experiment_digitally():
    """One flag, and the four sequences are otherwise identical."""
    board = adapter_registry.get("spincore_pulse_blaster")()
    report = await board.upload_sequence(rabi(points=15, analog=False), DIGITAL)
    assert report.readouts == 15
    assert report.instructions > 0


# --- Playing --------------------------------------------------------------


async def test_playing_without_a_sequence_says_so(pulser):
    with pytest.raises(RuntimeError, match="upload_sequence"):
        await pulser.pulser_on()


async def test_pulser_off_is_safe_when_nothing_is_playing(pulser):
    """What an abort calls, and an abort cannot know how far the run got."""
    await pulser.pulser_off()
    assert (await pulser.read())["running"] is False


async def test_playing_is_visible_in_the_reading(pulser):
    await pulser.upload_sequence(rabi(), ANALOG)
    await pulser.pulser_on()
    assert (await pulser.read())["running"] is True
    await pulser.pulser_off()
    assert (await pulser.read())["running"] is False


# --- The gated counter ----------------------------------------------------


async def test_configure_returns_what_was_actually_set(counter):
    """The caller uses the return value, not its own request — qudi's
    rule, and the reason a silently ignored bin width is not possible."""
    config = await counter.configure_gates(1.4e-9, 3e-6, 40)
    assert config.bin_width_s == pytest.approx(1e-9)
    assert config.gates == 40
    assert not config.exact
    assert BIN_WIDTH in config.report()


async def test_the_bin_count_is_derived_not_stored(counter):
    config = await counter.configure_gates(1e-9, 3e-6, 10)
    assert config.bins == 3000
    assert config.shape == (10, 3000)


async def test_counting_without_configuring_says_so(counter):
    with pytest.raises(RuntimeError, match="configure_gates"):
        await counter.start_counting()


async def test_stop_counting_is_safe_when_nothing_is_running(counter):
    await counter.stop_counting()
    assert (await counter.counter_status())["running"] is False


async def test_the_trace_carries_its_own_axes(pulser, counter):
    """A `Dataset`, not a bare array plus an info dict — so the run lands
    in HDF5 with coordinates nobody had to re-derive."""
    report = await pulser.upload_sequence(rabi(points=12), ANALOG)
    await pulser.pulser_on()
    config = await counter.configure_gates(1e-9, 2e-6, report.readouts)
    await counter.start_counting()
    await asyncio.sleep(0.05)

    array = (await counter.get_trace()).primary()
    assert array.name == "counts"
    assert array.values.shape == config.shape
    assert [axis.name for axis in array.axes] == ["readout", "time"]
    assert array.axes[1].unit == "s"
    assert array.axes[1].values[1] == pytest.approx(config.bin_width_s)


async def test_the_readout_window_decays_the_way_a_real_one_does(pulser, counter):
    """The signal lives in the leading edge and the tail is a per-shot
    reference. A flat rectangle would let an extraction algorithm pass a
    test it should fail."""
    await pulser.upload_sequence(rabi(points=4), ANALOG)
    await counter.configure_gates(1e-9, 2e-6, 4)
    await counter.start_counting()
    await asyncio.sleep(0.05)

    counts = (await counter.get_trace()).primary().values
    head = counts[:, :200].mean()
    tail = counts[:, -200:].mean()
    assert head > tail * 1.5


async def test_the_counter_shows_the_injected_rabi_oscillation(pulser, counter):
    """The point of a physical mock: a fit can recover what was put in.

    A 200 ns Rabi period stepped 20 ns per point puts the pi pulse — the
    darkest readout — at the fifth point.
    """
    await counter.set_rabi_period(200e-9)
    await counter.set_coherence_time(10e-6)
    await counter.set_contrast(0.3)
    sequence = build("rabi", RigProfile(rabi_period=200e-9), points=20)
    report = await pulser.upload_sequence(sequence, ANALOG)
    await pulser.pulser_on()
    await counter.configure_gates(1e-9, 2e-6, report.readouts)
    await counter.start_counting()
    await asyncio.sleep(0.1)

    per_readout = (await counter.get_trace()).primary().values.sum(axis=1)
    # tau = 20, 40, ... ns, so tau = 100 ns (the pi pulse) is index 4.
    assert int(np.argmin(per_readout[:10])) == 4


async def test_t1_shows_a_decay_with_no_oscillation(pulser, counter):
    """Log-spaced, so a short tau_stop still spans the decay — and keeps
    the sequence fast enough to accumulate real statistics in a test."""
    await counter.set_experiment("t1")
    await counter.set_coherence_time(20e-6)
    sequence = build("t1", RigProfile(), tau_start=1e-6, tau_stop=100e-6, points=8)
    report = await pulser.upload_sequence(sequence, ANALOG)
    await counter.configure_gates(1e-9, 2e-6, report.readouts)
    await counter.start_counting()
    await asyncio.sleep(0.2)

    per_readout = (await counter.get_trace()).primary().values.sum(axis=1).astype(float)
    assert per_readout[0] > per_readout[-1]  # relaxes toward a mixture
    # Monotone within Poisson noise, and no oscillation: a Rabi at these
    # taus would cross back up.
    assert per_readout[-1] < per_readout[0] * 0.95


async def test_sweeps_accumulate_while_counting(pulser, counter):
    """Paced by what the sequence's own duration implies, the same rule
    `mock/hardware_scan.py` uses — not an artificial per-point delay."""
    await pulser.upload_sequence(rabi(points=5), ANALOG)
    await counter.configure_gates(1e-9, 1e-6, 5)
    await counter.start_counting()
    await asyncio.sleep(0.05)
    first = (await counter.counter_status())["sweeps"]
    await asyncio.sleep(0.05)
    assert (await counter.counter_status())["sweeps"] > first


# --- The contracts refuse to be half-implemented --------------------------


def test_an_unimplemented_pulser_method_raises_rather_than_returning_none():
    """A mixin whose stubs returned None would let a driver look complete
    and produce empty data."""

    class Half(PulserMixin):
        pass

    for method in ("pulser_constraints",):
        with pytest.raises(NotImplementedError):
            getattr(Half(), method)()


def test_an_unimplemented_counter_method_raises():
    class Half(GatedCounterMixin):
        pass

    with pytest.raises(NotImplementedError):
        Half().counter_constraints()


# --- Sampling is still available to the drivers that need it --------------


def test_a_pulser_that_holds_samples_can_still_use_the_sampling_helper():
    """Sampling is a library an adapter may use, not a step imposed on
    everything upstream — a Tektronix AWG would call this."""
    from labpilot.instruments.pulser_mixin import pulser_constraints

    awg = pulser_constraints(
        sample_rate=(1.25e9,), analog_channels=("a_ch1",),
        digital_channels=("d_ch1", "d_ch2"), granularity=64, min_samples=4800,
    )
    sampled = sample(rabi(points=5), 1.25e9, awg.scalars)
    assert sampled.length % 64 == 0
    assert set(sampled.digital) == {"laser", "gate"}
