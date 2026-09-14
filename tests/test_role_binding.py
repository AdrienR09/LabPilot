"""Which instruments may fill which workflow role.

A workflow says `{"detector": {"kind": "detector", "dimensionality": "0D"}}`
and the server used to refuse any instrument whose `kind` said otherwise.
That is right for a mis-click — a motor bound to a detector role — and
wrong for the devices this framework most wants to support.

An NI DAQ card is an actuator, a detector, a counter and a hardware-timed
scanner at once, decided by which terminal a workflow reaches for. It is
`kind="generic"` because it is not one thing, and the old check therefore
kept it out of every role in every workflow: the card that could do the
job was simply missing from the list, with no error until someone
wondered why.

So `generic` fits everything, and what a device can actually do is settled
by its schema when a script asks it for a parameter — a check that is
exact and names the parameter, rather than a taxonomy guessing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.core.workflow.instrument_roles import role_refusal
from labpilot.instruments.mock.ni_card import MockNICard

DETECTOR = {"kind": "detector", "dimensionality": "0D"}
MOTOR = {"kind": "motor", "dimensionality": "ND"}


def refusal(requirement, kind, dimensionality="0D", role="detector"):
    return role_refusal(role, requirement, "instrument_1", kind, dimensionality)


# --- Generic fits everything -------------------------------------------------


def test_a_generic_instrument_fits_any_role():
    """The whole point: a device that is not one thing must not be
    excluded from every role for being several."""
    for requirement in (DETECTOR, MOTOR, {"kind": "source"}, {"kind": "counter"}):
        assert refusal(requirement, "generic") is None


def test_a_generic_instrument_ignores_the_dimensionality_too():
    """"Which dimensionality is an NI card?" has no answer — it depends
    on which terminal you ask about."""
    assert refusal(DETECTOR, "generic", dimensionality="ND") is None
    assert refusal({"dimensionality": "2D"}, "generic", dimensionality="") is None


def test_the_ni_card_is_the_case_this_exists_for():
    """Wired as it usually is, it genuinely is all four things at once."""
    card = MockNICard(model="PCIe-6363", channels="x=ao0, y=ao1, apd=ctr0/pfi8, pd=ai0")
    assert card.schema.kind == "generic"
    assert {"x", "y"} <= set(card.schema.settable)  # an actuator
    assert {"apd", "pd"} <= set(card.schema.readable)  # a detector and a counter

    for requirement in (DETECTOR, MOTOR):
        assert role_refusal("role", requirement, "ni_card_1", card.schema.kind, "ND") is None


# --- And the check still catches a mis-click ---------------------------------


def test_a_motor_is_still_refused_for_a_detector_role():
    """Cheaper than the failed run it would otherwise cause, and this is
    nearly always someone picking the wrong row of a list."""
    message = refusal(DETECTOR, "motor")
    assert message is not None
    assert "kind='detector'" in message
    assert "instrument_1" in message


def test_the_dimensionality_is_still_checked_for_a_typed_instrument():
    message = refusal(DETECTOR, "detector", dimensionality="2D")
    assert message is not None
    assert "dimensionality='0D'" in message


def test_a_requirement_that_names_nothing_accepts_anything():
    """A role with no stated kind is a role that does not care, which is
    how an optional or loosely-typed role is written today."""
    assert refusal({}, "motor") is None
    assert refusal({"optional": True}, "source") is None


def test_a_matching_instrument_is_accepted():
    assert refusal(DETECTOR, "detector") is None
    assert refusal(MOTOR, "motor", dimensionality="ND", role="stage") is None


@pytest.mark.parametrize("kind", ["detector", "motor", "source", "counter"])
def test_every_typed_kind_still_has_to_match(kind):
    other = "motor" if kind != "motor" else "detector"
    assert refusal({"kind": kind}, other) is not None


# --- A capability decides; a kind only guesses -------------------------------

GATED = {"capability": "gated_counter"}


def test_a_zero_d_detector_fills_the_pulsed_counter_role():
    """The case this rule exists for. A photon counter *is* a 0D
    detector, and the pulsed measurement's counter role used to demand
    `kind="counter"` — so an APD whose adapter spells itself `detector`
    could not be bound to the one role it was built for."""
    assert role_refusal(
        "counter", GATED, "apd_1", "detector", "0D", {"gated_counter"},
    ) is None


@pytest.mark.parametrize("kind", ["detector", "counter", "generic"])
def test_the_spelling_of_the_kind_does_not_matter(kind):
    """Four devices satisfy this contract and spell their kind three
    ways: the mock rig's counter, a Time Tagger at 1D, an R-Series FPGA
    card as `generic`. Any kind requirement refuses two of them to refuse
    nothing that could not do the job."""
    assert role_refusal(
        "counter", GATED, "x", kind, "1D", ["gated_counter", "pulser"],
    ) is None


def test_a_detector_without_the_capability_is_refused():
    """`configure_gates` is an AttributeError waiting for the run to
    reach it; refusing at bind time names the missing contract instead."""
    message = role_refusal("counter", GATED, "apd_1", "detector", "0D", ())
    assert message is not None
    assert "gated_counter" in message
    assert "apd_1" in message


def test_generic_does_not_excuse_a_missing_capability():
    """The escape hatch exists because `kind` cannot know what a card
    does. A capability is exactly that knowledge, so it still applies —
    an NI card with no counters configured is not a gated counter."""
    message = role_refusal("counter", GATED, "ni_card_1", "generic", "ND", ())
    assert message is not None
    assert "gated_counter" in message


def test_the_capability_is_checked_before_the_kind():
    """Both wrong reports the capability, because that is the one the
    person cannot fix by picking a different row of the same list."""
    message = role_refusal(
        "counter", {"kind": "counter", "capability": "gated_counter"},
        "stage_1", "motor", "1D", (),
    )
    assert message is not None
    assert "gated_counter" in message


def test_a_role_naming_no_capability_ignores_the_ones_a_device_has():
    assert refusal(DETECTOR, "detector") is None
    assert role_refusal(
        "detector", DETECTOR, "x", "detector", "0D", {"pulser"},
    ) is None


def test_the_pulsed_measurement_roles_bind_the_shipped_rig():
    """End to end on the declaration itself: every role the template
    declares, against the adapters it is meant to be run with."""
    import labpilot.core.workflow_templates as templates
    from labpilot.core.device.capabilities import capabilities_of
    from labpilot.core.workflow.instrument_roles import (
        read_required_instruments_from_file,
    )
    from labpilot.instruments.mock.pulse_rig import MockGatedCounter, MockPulser

    # Read, never imported: a template is a plain script whose top level
    # binds instruments and runs the measurement.
    path = Path(templates.__file__).parent / "pulsed_measurement.py"
    required = read_required_instruments_from_file(path)

    for role, adapter in (("pulser", MockPulser()), ("counter", MockGatedCounter())):
        assert role_refusal(
            role, required[role], "rig_1", adapter.schema.kind, "0D",
            capabilities_of(adapter),
        ) is None
