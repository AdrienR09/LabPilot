"""Finding the laser pulse inside a raw gated record.

Extraction is the step where a pulsed measurement goes wrong quietly. A
window that starts fifty nanoseconds early mixes in dark counts and costs
contrast; one that starts fifty late throws away the photons that carry
the spin state. Neither raises anything — the curve simply comes out
flatter, and the T2 comes out short.

So these are written against traces whose answer is known by
construction, and the assertions are on the *bins*, not on how the curve
that follows happens to look.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.pulse.extract import (
    EXTRACTORS,
    ExtractionError,
    extract,
    extractor_parameters,
)

BIN = 1e-9
DELAY = 300  # bins of dark before the laser arrives
LENGTH = 3000  # bins the laser is on for
RECORD = 4500


def trace(
    readouts: int = 8,
    *,
    delay: int = DELAY,
    length: int = LENGTH,
    record: int = RECORD,
    bright: float = 200.0,
    background: float = 2.0,
    decay: float = 300.0,
    seed: int | None = None,
) -> np.ndarray:
    """A record shaped like a real one: dark, then a decaying transient,
    then dark again. Noiseless unless `seed` is given, so a window
    assertion is about the algorithm rather than about a draw."""
    bins = np.arange(record, dtype=float)
    lit = (bins >= delay) & (bins < delay + length)
    profile = background + np.where(
        lit, bright * (0.35 + 0.65 * np.exp(-(bins - delay) / decay)), 0.0
    )
    counts = np.tile(profile, (readouts, 1))
    if seed is not None:
        counts = np.random.default_rng(seed).poisson(counts).astype(float)
    return counts


# --- Both methods find the pulse -------------------------------------------


@pytest.mark.parametrize("method", sorted(EXTRACTORS))
def test_every_method_finds_a_clean_pulse(method):
    found = extract(trace(), BIN, method)
    assert found.found
    assert found.window[0] == pytest.approx(DELAY, abs=30)
    assert found.window[1] == pytest.approx(DELAY + LENGTH, abs=30)


@pytest.mark.parametrize("method", sorted(EXTRACTORS))
def test_the_window_survives_shot_noise(method):
    """Twenty readouts of real Poisson counts, which is what the first
    seconds of a run actually look like."""
    found = extract(trace(20, bright=20.0, seed=7), BIN, method)
    assert found.window[0] == pytest.approx(DELAY, abs=60)
    assert found.window[1] == pytest.approx(DELAY + LENGTH, abs=60)


def test_conv_deriv_finds_an_edge_where_threshold_finds_a_level():
    """The reason both exist. Half the readouts sit on a raised
    background — a second laser leaking, or the room lights — which moves
    the level a threshold measures from without moving either edge.
    """
    counts = trace(8)
    counts[4:] += 60.0

    edges = extract(counts, BIN, "conv_deriv")
    assert edges.window[0] == pytest.approx(DELAY, abs=30)
    assert edges.window[1] == pytest.approx(DELAY + LENGTH, abs=30)


def test_a_single_noisy_bin_cannot_claim_the_window():
    """`threshold` takes the longest run above the level, not the first,
    so one hot bin early in the record is not mistaken for the pulse."""
    counts = trace(8)
    counts[:, 20] += 1000.0

    assert extract(counts, BIN, "threshold").window[0] == pytest.approx(DELAY, abs=30)


# --- What the extraction hands on -------------------------------------------


def test_the_extracted_pulses_are_the_window_and_nothing_else():
    found = extract(trace(6), BIN)
    assert found.pulses.shape == (6, found.window[1] - found.window[0])
    assert found.bins == found.pulses.shape[1]
    assert found.duration == pytest.approx(found.bins * BIN)


def test_bin_zero_of_a_pulse_is_the_start_of_the_laser_not_of_the_record():
    """What lets an analysis window be stated as "the first 300 ns"
    without knowing the rig's cable lengths."""
    early = extract(trace(4, delay=100), BIN)
    late = extract(trace(4, delay=900), BIN)

    assert early.window[0] != late.window[0]
    assert early.bins == pytest.approx(late.bins, abs=20)
    # The brightest bin is the first one of the laser pulse, in both.
    assert int(np.argmax(early.pulses.sum(axis=0))) < 20
    assert int(np.argmax(late.pulses.sum(axis=0))) < 20


def test_the_profile_is_summed_over_every_readout():
    """One window for all of them, because every gate is raised by the
    same pulser edge — and because a single readout in the first seconds
    of a run holds a handful of photons."""
    found = extract(trace(10), BIN)
    assert found.profile.shape == (RECORD,)
    assert found.profile.sum() == pytest.approx(trace(10).sum())


def test_a_gated_counter_s_dataset_can_be_handed_over_whole():
    """The console passes on whatever the counter returned; unwrapping it
    first is not the caller's job."""
    from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta

    counts = trace(5)
    dataset = Dataset(
        (
            DataArray(
                "counts", counts, unit="counts",
                axes=(
                    Axis("readout", np.arange(5), kind="index"),
                    Axis("time", np.arange(RECORD) * BIN, unit="s", kind="time"),
                ),
            ),
        ),
        RunMeta(device="counter"),
    )
    assert extract(dataset, BIN).window == extract(counts, BIN).window


# --- Saying so rather than guessing -----------------------------------------


def test_an_empty_trace_says_it_found_nothing():
    """The first poll of every run: nothing has been counted anywhere.
    Reporting an edge found in an all-zero record would be an invented
    answer, and refusing to return one would break the first frame."""
    found = extract(np.zeros((8, RECORD)), BIN)
    assert not found.found
    assert found.window == (0, RECORD)


def test_a_flat_record_is_treated_the_same_way():
    found = extract(np.full((4, 100), 7.0), BIN)
    assert not found.found
    assert found.window == (0, 100)


def test_an_unknown_method_lists_the_real_ones():
    with pytest.raises(ExtractionError, match="conv_deriv"):
        extract(trace(), BIN, "eyeball")


def test_an_undeclared_parameter_is_refused_rather_than_ignored():
    """A typo'd keyword that silently did nothing would leave someone
    tuning a parameter that was never read."""
    with pytest.raises(ExtractionError, match="smoothing"):
        extract(trace(), BIN, "conv_deriv", smoothness=5e-9)


def test_a_parameter_is_validated_against_its_own_declaration():
    with pytest.raises(Exception, match="level"):
        extract(trace(), BIN, "threshold", level=4.0)


def test_a_zero_bin_width_is_refused():
    with pytest.raises(ExtractionError, match="positive"):
        extract(trace(), 0.0)


def test_a_1_d_trace_is_read_as_one_readout():
    """A single-shot record is a legitimate thing to look at while
    setting a rig up."""
    assert extract(trace(1)[0], BIN).pulses.shape[0] == 1


def test_a_3_d_trace_says_what_shape_was_expected():
    with pytest.raises(ExtractionError, match="2-D"):
        extract(np.zeros((2, 3, 4)), BIN)


# --- Parameters are per method ----------------------------------------------


def test_each_method_declares_only_its_own_parameters():
    """The divergence from Qudi that this registry exists for: its
    extraction parameters are one flat dict shared by every method, which
    forces the documented rule that no two methods may share a keyword of
    different type."""
    assert [p.name for p in extractor_parameters("conv_deriv")] == ["smoothing"]
    assert [p.name for p in extractor_parameters("threshold")] == ["level"]


def test_a_declared_parameter_carries_its_unit():
    smoothing = extractor_parameters("conv_deriv")[0]
    assert smoothing.unit == "s"
    assert smoothing.description


def test_parameters_for_an_unknown_method_list_the_real_ones():
    with pytest.raises(ExtractionError, match="threshold"):
        extractor_parameters("eyeball")


def test_smoothing_wider_than_the_pulse_is_an_error_not_a_wrong_answer():
    """Deliberately over-smoothed: the pulse is 3 us and the kernel is
    30 us, so there is no edge left to find. The message has to name the
    cause, because the symptom (a flat curve) points nowhere."""
    with pytest.raises(ExtractionError, match="smoothing"):
        extract(trace(4, record=400, length=200, delay=100), BIN, smoothing=30e-6)
