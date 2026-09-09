"""Turning a sequence into what a device can hold.

Two paths, deliberately: `expand()` for a digital sequencer, which emits
`(level, duration)` and never builds an array, and `sample()` for a device
whose memory genuinely holds samples.

The arithmetic pinned here is the part that silently produces plausible
but wrong data: cumulative rounding, rotating-frame phase, padding that
must round up rather than to the nearest, and the difference between an
adjustment (report it) and a violation (refuse it).
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from labpilot.core.device.constraints import ScalarConstraint, scalars_from
from labpilot.core.pulse import (
    ChannelMap,
    PulseBlock,
    PulseElement,
    PulseSequence,
    Sin,
    check_activation,
    expand,
    linear_sweep,
    sample,
)
from labpilot.core.pulse.sampling import (
    ELEMENT_LENGTH,
    SAMPLE_RATE,
    WAVEFORM_LENGTH,
    SamplingError,
)

MW = Sin(amplitude=0.5, frequency=1e6)


def rabi(points: int = 4) -> PulseSequence:
    block = PulseBlock(
        "rabi",
        (
            PulseElement(100e-9, {"mw": MW, "laser": False}, increment=100e-9, name="mw"),
            PulseElement(300e-9, {"laser": True, "gate": True}, name="readout"),
            PulseElement(200e-9, {"laser": False}, name="wait"),
        ),
        repetitions=points,
    )
    return PulseSequence(
        "rabi", (block,), sweep=linear_sweep("tau", 100e-9, 100e-9, points)
    )


# --- expand(): the path a digital sequencer takes --------------------------


def test_expand_applies_the_increment_once_per_repetition():
    driven = [i for i in expand(rabi()) if i.name == "mw"]
    assert [i.duration for i in driven] == [
        pytest.approx(100e-9), pytest.approx(200e-9),
        pytest.approx(300e-9), pytest.approx(400e-9),
    ]


def test_expand_lays_intervals_end_to_end_in_absolute_time():
    intervals = list(expand(rabi()))
    for previous, following in pairwise(intervals):
        assert following.start == pytest.approx(previous.end)
    assert intervals[-1].end == pytest.approx(rabi().duration)


def test_an_interval_reports_digital_level_and_analog_shape_separately():
    first = next(expand(rabi()))
    assert first.shape("mw") is MW
    assert first.level("laser") is False
    assert first.shape("laser") is None


def test_an_interval_names_where_it_came_from():
    """So an error about a 4 ns element says which play of which block."""
    intervals = list(expand(rabi()))
    assert intervals[3].block == "rabi"
    assert intervals[3].repetition == 1
    assert "rabi[1]" in intervals[3].describe()


def test_expand_never_samples_anything():
    """A 5 ms idle must cost one interval, not five million booleans —
    the whole reason upload_sequence takes the abstract sequence."""
    block = PulseBlock("b", (
        PulseElement(5e-3, {"laser": False}, name="idle"),
        PulseElement(1e-6, {"laser": True, "gate": True}, name="readout"),
    ))
    assert len(list(expand(PulseSequence("s", (block,))))) == 2


# --- sample(): the path an AWG takes ---------------------------------------


def test_sampling_produces_one_array_per_channel_at_the_right_length():
    sampled = sample(rabi(), 1e9)
    assert sampled.length == round(rabi().duration * 1e9)
    assert set(sampled.analog) == {"mw"}
    assert set(sampled.digital) == {"laser", "gate"}
    assert sampled.digital["laser"].dtype == bool


def test_a_digital_channel_is_high_exactly_where_its_element_is():
    sampled = sample(rabi(points=1), 1e9)
    # 100 ns drive, 300 ns readout, 200 ns wait.
    assert not sampled.digital["laser"][:100].any()
    assert sampled.digital["laser"][100:400].all()
    assert not sampled.digital["laser"][400:].any()


def test_bin_edges_come_from_cumulative_time_not_accumulated_rounding():
    """Rounding each element and adding them drifts: a 2.5-sample element
    rounds to 3 every time, and after a thousand of them the sequence's
    last point is a microsecond late."""
    block = PulseBlock("b", (
        PulseElement(2.5e-9, {"laser": False}),
        PulseElement(2.5e-9, {"laser": True, "gate": True}),
    ), repetitions=1000)
    sequence = PulseSequence("drift", (block,))
    sampled = sample(sequence, 1e9)
    assert sampled.length == 5000  # not 6000
    assert sampled.duration == pytest.approx(sequence.duration)


def test_a_rotating_frame_keeps_phase_continuous_across_elements():
    """Ramsey and Hahn echo measure a phase difference; they are wrong
    without this."""
    block = PulseBlock("b", (
        PulseElement(1e-6, {"mw": MW}, name="first"),
        PulseElement(1e-6, {"laser": True, "gate": True}, name="readout"),
        PulseElement(1e-6, {"mw": MW}, name="second"),
    ))
    sequence = PulseSequence("s", (block,), rotating_frame=True)
    sampled = sample(sequence, 1e9)
    # MW is 1 MHz and the elements are 1 us, so a whole number of periods
    # separates the two pulses: coherent means they are identical.
    assert np.allclose(sampled.analog["mw"][:1000], sampled.analog["mw"][2000:3000])


def test_without_a_rotating_frame_each_element_restarts_at_zero():
    block = PulseBlock("b", (
        PulseElement(500e-9, {"mw": MW}),
        PulseElement(1e-6, {"laser": True, "gate": True}),
        PulseElement(500e-9, {"mw": Sin(0.5, 1e6, 0.0)}),
    ))
    sampled = sample(PulseSequence("s", (block,), rotating_frame=False), 1e9)
    assert sampled.analog["mw"][0] == pytest.approx(0.0, abs=1e-12)
    assert sampled.analog["mw"][1500] == pytest.approx(0.0, abs=1e-12)


def test_analog_samples_are_volts():
    """Not a normalised +/-1: dividing by a channel's Vpp is the driver's
    job, because only the driver knows its own Vpp."""
    block = PulseBlock("b", (
        PulseElement(1e-6, {"mw": MW}, name="drive"),
        PulseElement(1e-6, {"laser": True, "gate": True}, name="readout"),
    ))
    sampled = sample(PulseSequence("s", (block,)), 1e9)
    assert np.max(np.abs(sampled.analog["mw"])) == pytest.approx(0.5, rel=1e-3)


def test_readout_windows_are_reported_in_sample_indices():
    """What the gated counter's gates are, in the sampled sequence's own
    coordinates — so the mock counter and the sequence cannot disagree."""
    sampled = sample(rabi(points=3), 1e9)
    assert len(sampled.readouts) == 3
    start, stop = sampled.readouts[0]
    assert (start, stop) == (100, 400)


def test_an_ungated_sequence_reports_its_laser_windows_instead():
    block = PulseBlock("b", (
        PulseElement(100e-9, {"laser": False}),
        PulseElement(200e-9, {"laser": True}),
    ), repetitions=2)
    sampled = sample(PulseSequence("s", (block,), gate_channel=None), 1e9)
    assert sampled.readouts == ((100, 300), (400, 600))


def test_an_invalid_sequence_is_never_sampled():
    block = PulseBlock("b", (PulseElement(1e-6, {"laser": False}),))
    with pytest.raises(Exception, match="no readout"):
        sample(PulseSequence("s", (block,)), 1e9)


# --- Constraints: adjust what can be adjusted, refuse what cannot ----------


def test_the_sample_rate_is_quantised_before_anything_is_placed():
    """Every bin edge depends on it, so fixing it up afterwards would put
    every element in the wrong place."""
    constraints = scalars_from([
        ScalarConstraint(SAMPLE_RATE, allowed=(1e9, 1.25e9), unit="Hz"),
    ])
    sampled = sample(rabi(points=1), 1.1e9, constraints)
    assert sampled.sample_rate == pytest.approx(1e9)
    assert not sampled.quantised.exact
    assert "sample_rate" in sampled.report()


def test_a_waveform_is_padded_up_to_the_memory_granularity():
    constraints = scalars_from([
        ScalarConstraint(WAVEFORM_LENGTH, bounds=(1, None), step=64),
    ])
    sampled = sample(rabi(points=1), 1e9, constraints)
    assert sampled.length == 640  # 600 samples padded to a multiple of 64
    assert sampled.padding == 40
    assert "granularity" in sampled.report()


def test_padding_rounds_up_so_the_last_element_is_never_truncated():
    """Snapping to the nearest would shorten the waveform, and a sequence
    whose final readout is half a window long fails in a way that looks
    like a physics result."""
    constraints = scalars_from([
        ScalarConstraint(WAVEFORM_LENGTH, bounds=(1, None), step=512),
    ])
    sampled = sample(rabi(points=1), 1e9, constraints)
    assert sampled.length == 1024
    assert sampled.digital["laser"][100:400].all()


def test_padding_is_idle():
    constraints = scalars_from([
        ScalarConstraint(WAVEFORM_LENGTH, bounds=(1, None), step=64),
    ])
    sampled = sample(rabi(points=1), 1e9, constraints)
    assert not sampled.digital["laser"][600:].any()
    assert np.all(sampled.analog["mw"][600:] == 0.0)


def test_a_short_waveform_is_padded_up_to_the_minimum_length():
    block = PulseBlock("b", (PulseElement(100e-9, {"laser": True, "gate": True}),))
    constraints = scalars_from([
        ScalarConstraint(WAVEFORM_LENGTH, bounds=(4096, None)),
    ])
    assert sample(PulseSequence("s", (block,)), 1e9, constraints).length == 4096


def test_a_sequence_too_long_for_the_memory_is_refused():
    constraints = scalars_from([
        ScalarConstraint(WAVEFORM_LENGTH, bounds=(1, 128)),
    ])
    with pytest.raises(SamplingError, match="holds 128"):
        sample(rabi(points=1), 1e9, constraints)


def test_an_element_below_the_minimum_length_is_refused_not_rounded():
    """A granularity mismatch is negotiable; an element the hardware
    cannot express is not."""
    block = PulseBlock("b", (
        PulseElement(4e-9, {"mw": MW}, name="tip"),
        PulseElement(1e-6, {"laser": True, "gate": True}, name="readout"),
    ))
    constraints = scalars_from([
        ScalarConstraint(ELEMENT_LENGTH, bounds=(8e-9, None), unit="s"),
    ])
    with pytest.raises(SamplingError, match="minimum"):
        sample(PulseSequence("s", (block,)), 1e9, constraints)


def test_the_offending_element_is_named():
    block = PulseBlock("b", (
        PulseElement(4e-9, {"mw": MW}, name="tip"),
        PulseElement(1e-6, {"laser": True, "gate": True}),
    ), repetitions=2)
    constraints = scalars_from([ScalarConstraint(ELEMENT_LENGTH, bounds=(8e-9, None))])
    with pytest.raises(SamplingError, match="tip"):
        sample(PulseSequence("s", (block,)), 1e9, constraints)


def test_an_element_shorter_than_one_sample_is_refused():
    block = PulseBlock("b", (
        PulseElement(0.4e-9, {"mw": MW}, name="tip"),
        PulseElement(1e-6, {"laser": True, "gate": True}),
    ))
    with pytest.raises(SamplingError, match="shorter than one sample"):
        sample(PulseSequence("s", (block,)), 1e9)


def test_a_zero_length_element_is_allowed_and_occupies_nothing():
    """Generators emit these — a Ramsey at tau=0 has a zero-length idle,
    and refusing it would make the first point of every sweep special."""
    block = PulseBlock("b", (
        PulseElement(0.0, {"mw": MW}, increment=100e-9, name="tau"),
        PulseElement(1e-6, {"laser": True, "gate": True}),
    ), repetitions=2)
    sampled = sample(PulseSequence("s", (block,)), 1e9)
    assert sampled.length == 2100


def test_no_constraints_means_no_adjustments():
    assert sample(rabi(), 1e9).quantised.exact


# --- Activation configs ----------------------------------------------------


def test_a_sequence_that_fits_an_activation_config_selects_it():
    """Which channels may be enabled together is real hardware — a mock
    never punishes you for omitting it and a PulseBlaster will."""
    mapping = ChannelMap({"mw": "a_ch1", "laser": "d_ch1", "gate": "d_ch2"})
    config = check_activation(
        rabi(), mapping,
        [{"d_ch1", "d_ch2", "d_ch3"}, {"a_ch1", "d_ch1", "d_ch2"}],
    )
    assert config == frozenset({"a_ch1", "d_ch1", "d_ch2"})


def test_a_sequence_that_fits_no_config_is_refused_with_what_is_offered():
    mapping = ChannelMap({"mw": "a_ch1", "laser": "d_ch1", "gate": "d_ch2"})
    with pytest.raises(SamplingError, match="a_ch1"):
        check_activation(rabi(), mapping, [{"d_ch1", "d_ch2", "d_ch3"}])


def test_an_unmapped_channel_is_caught_before_the_activation_check():
    with pytest.raises(Exception, match="gate"):
        check_activation(rabi(), ChannelMap({"mw": "a_ch1", "laser": "d_ch1"}), [set()])
