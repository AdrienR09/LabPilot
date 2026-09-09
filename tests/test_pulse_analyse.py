"""Reducing extracted readouts to one number per swept point.

The conventions matter more than the arithmetic here, and two of them are
the kind that produce a plausible curve of nothing:

- **one value per swept point**, not per readout, so an alternating
  sequence's 80 readouts become 40 points here rather than somewhere
  downstream that has to guess which convention was used;
- **`mean_reference` refuses non-alternating data** instead of pairing
  unrelated readouts.

Built on synthetic readouts whose answer is arithmetic, so a failure
points at the reduction rather than at a fit.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.pulse.analyse import (
    ANALYSES,
    AnalysisError,
    analyse,
    analysis_parameters,
    analysis_units,
    default_analysis,
)

BIN = 1e-9
SIGNAL = 300  # bins the signal window covers, at BIN
TAIL = 3000  # bins in a whole readout


def readouts(brightness, *, tail: float = 100.0, bins: int = TAIL) -> np.ndarray:
    """One row per readout: a flat signal region at `brightness`, then a
    flat tail at `tail` that every readout shares.

    Flat rather than decaying, because these tests are about which bins
    are averaged and what is divided by what — a transient would make
    every expected value an integral.
    """
    rows = []
    for value in brightness:
        row = np.full(bins, float(tail))
        row[:SIGNAL] = float(value)
        rows.append(row)
    return np.asarray(rows)


# --- One value per swept point ----------------------------------------------


def test_a_plain_sequence_gives_one_value_per_readout():
    result = analyse(readouts([10, 20, 30, 40]), BIN, "mean")
    assert result.points == 4
    assert result.values == pytest.approx([10, 20, 30, 40])


def test_an_alternating_sequence_halves_its_readouts_into_points():
    """80 readouts of a Ramsey are 40 points. Returning 80 values would
    leave every consumer guessing which convention was used."""
    result = analyse(
        readouts([10, 5, 20, 5, 30, 5, 40, 5]), BIN, "mean", alternating=True
    )
    assert result.points == 4
    assert result.values == pytest.approx([10, 20, 30, 40])


def test_an_odd_number_of_readouts_drops_the_unpaired_one():
    """A run polled mid-sweep. Pairing the last readout with nothing
    would put a spurious final point on the curve."""
    result = analyse(readouts([10, 5, 20, 5, 30]), BIN, "mean_reference", alternating=True)
    assert result.points == 2


def test_fewer_than_two_readouts_says_so_rather_than_returning_nothing():
    with pytest.raises(AnalysisError, match="pair"):
        analyse(readouts([10]), BIN, "mean_reference", alternating=True)


# --- What each method actually computes -------------------------------------


def test_mean_is_counts_per_bin_in_the_signal_window():
    result = analyse(readouts([12, 24]), BIN, "mean", signal_length=SIGNAL * BIN)
    assert result.values == pytest.approx([12, 24])
    assert result.unit == "counts/bin"


def test_mean_averages_over_exactly_the_window_asked_for():
    """Half the window is signal and half is tail, so the answer is
    their mean — which is what makes an over-long window cost contrast
    rather than merely counts."""
    result = analyse(
        readouts([100], tail=0.0), BIN, "mean", signal_length=2 * SIGNAL * BIN
    )
    assert result.values == pytest.approx([50.0])


def test_mean_norm_divides_each_readout_by_its_own_tail():
    """Per-shot normalisation: laser power drift divides out because the
    numerator and the denominator come from the same shot."""
    rows = readouts([100, 50], tail=200.0)
    rows[1] *= 2  # This shot saw twice the laser power, signal and tail.

    result = analyse(
        rows, BIN, "mean_norm",
        signal_length=SIGNAL * BIN, norm_start=SIGNAL * BIN, norm_length=SIGNAL * BIN,
    )
    assert result.values == pytest.approx([0.5, 0.25])
    assert result.unit == ""


def test_mean_reference_divides_the_signal_readout_by_the_one_beside_it():
    result = analyse(
        readouts([120, 100, 80, 100]), BIN, "mean_reference",
        alternating=True, signal_length=SIGNAL * BIN,
    )
    assert result.values == pytest.approx([1.2, 0.8])


def test_mean_reference_refuses_a_sequence_that_has_no_reference():
    """Pairing unrelated readouts would produce a plausible curve of
    nothing, which is worse than an error."""
    with pytest.raises(AnalysisError, match="alternating"):
        analyse(readouts([1, 2, 3, 4]), BIN, "mean_reference", alternating=False)


def test_mean_on_alternating_data_uses_the_signal_arm():
    """Documented rather than silent: it discards the reference
    readouts, which is why `auto` never picks it for such a sequence."""
    result = analyse(readouts([9, 1, 8, 1]), BIN, "mean", alternating=True)
    assert result.values == pytest.approx([9, 8])


# --- Errors are Poisson -----------------------------------------------------


def test_the_error_on_a_mean_comes_from_the_total_not_from_the_mean():
    """`sqrt(N)/n`, so averaging over more bins genuinely reduces the
    uncertainty. Taking `sqrt(mean)` instead would claim a 300-bin window
    is no better than one bin."""
    result = analyse(readouts([100]), BIN, "mean", signal_length=SIGNAL * BIN)
    total = 100 * SIGNAL
    assert result.errors == pytest.approx([np.sqrt(total) / SIGNAL])


def test_more_counts_means_a_smaller_relative_error():
    few = analyse(readouts([4]), BIN, "mean")
    many = analyse(readouts([400]), BIN, "mean")
    assert few.errors[0] / few.values[0] == pytest.approx(
        10 * many.errors[0] / many.values[0], rel=1e-9
    )


def test_a_ratio_propagates_both_uncertainties():
    result = analyse(
        readouts([100, 100]), BIN, "mean_reference",
        alternating=True, signal_length=SIGNAL * BIN,
    )
    # Two independent terms of equal size: sqrt(2) times either alone.
    single = np.sqrt(100 * SIGNAL) / (100 * SIGNAL)
    assert result.errors == pytest.approx([np.sqrt(2) * single], rel=1e-6)


def test_a_zero_denominator_is_a_gap_not_an_exception():
    """The first poll of a run has counted nothing anywhere, and a run
    that refused to report its own first frame would be worse than one
    that reports a gap."""
    result = analyse(np.zeros((4, TAIL)), BIN, "mean_reference", alternating=True)
    assert np.isnan(result.values).all()


# --- Choosing a method ------------------------------------------------------


def test_auto_uses_the_reference_readouts_when_there_are_any():
    assert default_analysis(alternating=True) == "mean_reference"
    assert analyse(
        readouts([120, 100]), BIN, "auto", alternating=True
    ).method == "mean_reference"


def test_auto_falls_back_to_per_readout_normalisation_when_there_are_not():
    """A Rabi has one readout per point, so there is no reference arm to
    divide by — but there is still a tail."""
    assert default_analysis(alternating=False) == "mean_norm"
    assert analyse(readouts([100, 50]), BIN, "auto").method == "mean_norm"


def test_every_method_declares_what_it_produces_before_it_runs():
    """What lets `describe()` state a run's value name and unit up front,
    with no readout yet in existence to analyse."""
    for name in ANALYSES:
        label, unit = analysis_units(name)
        assert label
        assert isinstance(unit, str)


def test_the_declared_unit_is_the_one_the_result_carries():
    for name in ANALYSES:
        label, unit = analysis_units(name)
        result = analyse(
            readouts([120, 100]), BIN, name, alternating=name == "mean_reference"
        )
        assert (result.label, result.unit) == (label, unit)


# --- Parameters are per method ----------------------------------------------


def test_each_method_declares_only_the_windows_it_uses():
    assert [p.name for p in analysis_parameters("mean")] == [
        "signal_start", "signal_length",
    ]
    assert "norm_start" in {p.name for p in analysis_parameters("mean_norm")}
    assert "norm_start" not in {p.name for p in analysis_parameters("mean_reference")}


def test_a_parameter_a_method_does_not_take_is_refused():
    with pytest.raises(AnalysisError, match="norm_start"):
        analyse(readouts([1, 2]), BIN, "mean", norm_start=1e-6)


def test_an_unknown_method_lists_the_real_ones():
    with pytest.raises(AnalysisError, match="mean_reference"):
        analyse(readouts([1, 2]), BIN, "median_of_medians")


def test_a_window_outside_the_readout_names_both_numbers():
    """A silent clamp is how a normalisation window quietly becomes one
    bin wide, and how a T2 comes out 40% short."""
    with pytest.raises(AnalysisError, match="normalisation window"):
        analyse(readouts([1, 2]), BIN, "mean_norm", norm_start=9e-6, norm_length=1e-6)


def test_an_extraction_can_be_handed_straight_over():
    """The two halves compose without the caller unwrapping anything."""
    from labpilot.core.pulse.extract import extract

    counts = readouts([100, 50], tail=10.0)
    found = extract(counts, BIN, "threshold")
    assert analyse(found, BIN, "mean").points == 2


def test_a_zero_bin_width_is_refused():
    with pytest.raises(AnalysisError, match="positive"):
        analyse(readouts([1, 2]), 0.0, "mean")
