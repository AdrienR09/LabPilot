"""Configuring hardware is a negotiation, not an assignment.

`Parameter.validate` answers "is this a legal request?" and raises. That is
right for a setpoint: asking a stage to travel past its end stop is a
mistake. Configuring is a different question — a counter's bin width comes
from a discrete list its clock can divide down to, a pulser's waveform
length must be a multiple of its memory granularity. Asking for 1.4 ns is
not illegal; it is simply going to become 1 ns.

So `quantise` never raises. It clips, snaps, and reports every adjustment,
because a silently ignored request is how someone spends an afternoon
wondering why a 50 ns pi-pulse behaves like 48 ns.
"""

from __future__ import annotations

import pytest

from labpilot.core.device.constraints import (
    Constraints,
    ScalarConstraint,
    scalars_from,
)

# A counter whose clock divides down to these bin widths and no others.
BIN_WIDTH = ScalarConstraint(
    "bin_width_s", allowed=(1e-9, 2e-9, 4e-9, 8e-9), unit="s",
)
# A pulser with 8 ns memory granularity.
DURATION = ScalarConstraint(
    "duration_ns", bounds=(8.0, 1e6), step=8.0, unit="ns",
)
GATES = ScalarConstraint("gates", bounds=(1, 4096), enforce_int=True)


# --- A discrete set -------------------------------------------------------


def test_a_supported_value_is_left_alone():
    actual, reasons = BIN_WIDTH.quantise(2e-9)
    assert actual == 2e-9
    assert reasons == []


def test_an_unsupported_value_snaps_to_the_nearest_supported_one():
    """The concept qudi's own constraints cannot express: their
    ScalarConstraint has only min/max/step, so a fixed bin-width table is
    faked with min == max and step == 0."""
    actual, reasons = BIN_WIDTH.quantise(1.4e-9)
    assert actual == 1e-9
    assert reasons and "supported value" in reasons[0]


def test_snapping_picks_the_nearest_not_the_lower():
    assert BIN_WIDTH.quantise(3.6e-9)[0] == 4e-9


def test_a_constraint_must_allow_something():
    with pytest.raises(ValueError, match="allows no values"):
        ScalarConstraint("x", allowed=())


# --- Granularity ----------------------------------------------------------


def test_a_value_on_the_grid_is_left_alone():
    actual, reasons = DURATION.quantise(64.0)
    assert actual == 64.0
    assert reasons == []


def test_a_value_off_the_grid_snaps_to_a_multiple():
    actual, reasons = DURATION.quantise(100.0)
    assert actual == 104.0
    assert reasons and "multiple of 8.0" in reasons[0]


def test_a_value_below_the_minimum_is_clipped_and_reported():
    actual, reasons = DURATION.quantise(2.0)
    assert actual == 8.0
    assert any("minimum" in r for r in reasons)


def test_a_value_above_the_maximum_is_clipped_and_reported():
    actual, reasons = DURATION.quantise(2e6)
    assert actual <= 1e6
    assert any("maximum" in r for r in reasons)


def test_snapping_never_leaves_the_bounds():
    """Rounding up at the top of the range would hand the driver a value
    it just said it could not take."""
    tight = ScalarConstraint("x", bounds=(0.0, 10.0), step=4.0)
    assert tight.quantise(10.0)[0] <= 10.0
    assert tight.quantise(0.5)[0] >= 0.0


def test_a_grid_is_measured_from_the_lower_bound():
    offset = ScalarConstraint("x", bounds=(5.0, 100.0), step=10.0)
    assert offset.quantise(15.0)[0] == 15.0
    assert offset.quantise(16.0)[0] == 15.0


def test_a_non_positive_step_is_refused_at_declaration():
    with pytest.raises(ValueError, match="non-positive step"):
        ScalarConstraint("x", step=0.0)


def test_inverted_bounds_are_refused_at_declaration():
    with pytest.raises(ValueError, match="inverted bounds"):
        ScalarConstraint("x", bounds=(10.0, 1.0))


# --- Integers -------------------------------------------------------------


def test_an_integer_setting_comes_back_an_int():
    actual, reasons = GATES.quantise(50)
    assert actual == 50 and isinstance(actual, int)
    assert reasons == []


def test_a_fractional_count_is_rounded_and_reported():
    actual, reasons = GATES.quantise(50.6)
    assert actual == 51
    assert any("whole number" in r for r in reasons)


# --- The whole request ----------------------------------------------------


@pytest.fixture
def counter():
    return scalars_from([BIN_WIDTH, GATES])


def test_an_exact_request_reports_nothing(counter):
    result = counter.quantise({"bin_width_s": 2e-9, "gates": 50})
    assert result.exact
    assert result.values == {"bin_width_s": 2e-9, "gates": 50}
    assert result.report() == ""


def test_every_adjustment_is_reported_not_just_the_first(counter):
    result = counter.quantise({"bin_width_s": 1.4e-9, "gates": 50.6})
    assert not result.exact
    assert result["bin_width_s"] == 1e-9
    assert result["gates"] == 51
    assert {a.parameter for a in result.adjustments} == {"bin_width_s", "gates"}


def test_an_adjustment_says_what_was_asked_and_what_happened(counter):
    (adjustment,) = counter.quantise({"bin_width_s": 1.4e-9}).adjustments
    assert adjustment.requested == 1.4e-9
    assert adjustment.actual == 1e-9
    assert "asked" in str(adjustment) and "got" in str(adjustment)


def test_an_unconstrained_name_passes_through_untouched(counter):
    """This reports what it knows about; it does not pretend to police
    the rest of the request."""
    result = counter.quantise({"gates": 8, "label": "rabi"})
    assert result.values["label"] == "rabi"
    assert result.exact


def test_quantising_never_raises_however_absurd_the_request(counter):
    """The whole point: a configure call negotiates. Rejection is
    `Parameter.validate`'s job, and it has already run."""
    result = counter.quantise({"bin_width_s": -5.0, "gates": 10**9})
    assert result.values["bin_width_s"] in BIN_WIDTH.allowed
    assert result.values["gates"] == 4096


def test_constraining_one_name_twice_is_refused():
    with pytest.raises(ValueError, match="twice"):
        Constraints(scalars=(GATES, GATES))


def test_a_constraint_can_be_looked_up_by_name(counter):
    assert counter.get("gates") is GATES
    assert counter.get("nope") is None
    assert counter.names() == ("bin_width_s", "gates")


def test_extras_carry_what_no_range_can_express():
    """A pulser's activation configs — which channel sets may be on at
    once — is a real constraint and not a number."""
    constraints = Constraints(
        scalars=(DURATION,),
        extra={"activation_configs": {"all": frozenset({"d_ch1", "d_ch2"})}},
    )
    assert "all" in constraints.extra["activation_configs"]


def test_repeated_quantising_is_stable():
    """Feeding a quantised value back in must not drift it — otherwise a
    settings dock that reads back what it wrote walks the value."""
    once = DURATION.quantise(100.0)[0]
    assert DURATION.quantise(once) == (once, [])
