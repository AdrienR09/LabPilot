"""The four standard NV pulsed experiments, as generators.

Qudi discovers generators by an `generate_*` name prefix and takes their
schema from `inspect.signature` defaults — which forces its GUI to guess
each parameter's unit from substrings of its name (`'amp' in name` means
volts, `'tau' in name` means seconds). Here parameters are declared as
`Parameter` objects, so units are stated.

The physics is pinned here rather than left to be discovered against
hardware: a Rabi is not alternating and a Ramsey is, T1 is log-spaced,
and an initialisation laser pulse is not a readout.
"""

from __future__ import annotations

import pytest

from labpilot.core.pulse.library import (
    GENERATORS,
    RigProfile,
    build,
    centre_to_centre,
    generator_parameters,
)
from labpilot.core.pulse.sequence import SequenceError
from labpilot.core.pulse.shapes import Sin

PROFILE = RigProfile()


# --- The rig profile ------------------------------------------------------


def test_pulse_lengths_derive_from_the_rabi_period():
    """One calibration drives everything else, which is why a Rabi is run
    first."""
    profile = RigProfile(rabi_period=200e-9)
    assert profile.pi == pytest.approx(100e-9)
    assert profile.pi_half == pytest.approx(50e-9)


def test_an_analog_rig_drives_the_microwave_with_a_shape():
    element = PROFILE.drive(PROFILE.pi)
    assert isinstance(element.channels["mw"], Sin)
    assert element.channels["mw"].frequency == pytest.approx(2.87e9)


def test_a_digital_rig_gates_an_external_source_instead():
    """A PulseBlaster has no analog output and switches a separate
    microwave generator; the sequences are otherwise identical."""
    element = RigProfile(analog_mw=False).drive(100e-9)
    assert element.channels["mw"] is True


def test_centre_to_centre_subtracts_the_pulse_between():
    """The ambiguity that quietly costs 100 ns on every point."""
    assert centre_to_centre(1e-6, PROFILE) == pytest.approx(1e-6 - PROFILE.pi)
    assert centre_to_centre(10e-9, PROFILE) == 0.0


# --- Each experiment ------------------------------------------------------


def test_every_generator_is_registered_and_builds():
    assert set(GENERATORS) == {
        "rabi", "ramsey", "hahn_echo", "t1", "pulsed_odmr",
    }
    for name in GENERATORS:
        build(name, PROFILE).validate()


def test_pulsed_odmr_sweeps_a_setting_rather_than_a_pulse():
    """The one experiment here the pulser does not play point by point: a
    carrier frequency is not a duration, so the pattern is fixed and the
    source steps between passes."""
    sequence = build("pulsed_odmr", PROFILE, start=2.85e9, stop=2.89e9, points=41)

    assert sequence.points == 41
    assert sequence.sweep.stepped
    assert sequence.sweep.parameter == "frequency"
    assert sequence.sweep.unit == "Hz"
    assert sequence.sweep.values[0] == pytest.approx(2.85e9)
    assert sequence.sweep.values[-1] == pytest.approx(2.89e9)
    # One readout per pass — 41 points and 41 readouts would mean the
    # sequence contained the sweep, which it cannot.
    assert sequence.readouts() == 1
    assert all(element.increment == 0.0 for element in sequence.blocks[0].elements)


def test_a_pulsed_odmr_drives_for_exactly_a_pi_pulse():
    """Fixed-length, unlike every other experiment here — the pulse is the
    thing held constant while the frequency moves."""
    elements = build("pulsed_odmr", PROFILE).blocks[0].elements
    driving = [e for e in elements if isinstance(e.channels.get("mw"), Sin)]
    assert len(driving) == 1
    assert driving[0].duration == pytest.approx(PROFILE.pi)


def test_rabi_sweeps_the_drive_and_reads_out_once_per_point():
    sequence = build("rabi", PROFILE, points=50)
    assert sequence.points == 50
    assert sequence.readouts() == 50
    assert not sequence.alternating
    driven = sequence.blocks[0].elements[0]
    assert driven.increment > 0


def test_ramsey_is_alternating_and_pairs_its_readouts():
    """The signal is the difference between the two final-pulse phases;
    a single-phase Ramsey rides on a drifting readout level."""
    sequence = build("ramsey", PROFILE, points=50)
    assert sequence.alternating
    assert sequence.points == 50
    assert sequence.readouts() == 100


def test_ramsey_closes_with_opposite_phases():
    elements = build("ramsey", PROFILE).blocks[0].elements
    phases = [e.channels["mw"].phase for e in elements if isinstance(e.channels.get("mw"), Sin)]
    assert 0.0 in phases and 180.0 in phases


def test_hahn_echo_refocuses_with_a_pi_pulse_between_two_idles():
    sequence = build("hahn_echo", PROFILE, points=40)
    assert sequence.alternating
    assert sequence.points == 40
    lengths = [e.duration for e in sequence.blocks[0].elements if "mw" in e.channels]
    # pi/2, pi, pi/2 per arm — the middle one is twice the others.
    assert lengths[:3] == [
        pytest.approx(PROFILE.pi_half),
        pytest.approx(PROFILE.pi),
        pytest.approx(PROFILE.pi_half),
    ]


def test_hahn_echo_sweeps_both_halves_of_the_evolution():
    """Total free evolution is twice tau, which is the axis to plot
    against for a decay constant that matches the literature."""
    idles = [
        e for e in build("hahn_echo", PROFILE).blocks[0].elements
        if e.name == "tau"
    ]
    assert len(idles) == 4  # two per arm, two arms
    assert all(e.increment > 0 for e in idles)


def test_t1_is_logarithmically_spaced():
    """The decay spans decades; linear spacing spends almost every point
    after the signal has gone."""
    sequence = build("t1", PROFILE, tau_start=1e-6, tau_stop=5e-3, points=20)
    values = sequence.sweep.values
    assert values[0] == pytest.approx(1e-6)
    assert values[-1] == pytest.approx(5e-3)
    ratios = [values[i + 1] / values[i] for i in range(len(values) - 1)]
    assert max(ratios) - min(ratios) < 1e-6  # constant ratio == log spacing


def test_t1_needs_one_block_per_point():
    """An increment cannot express a log sweep, which is exactly why the
    sequencer's repetition counts earn their keep here."""
    sequence = build("t1", PROFILE, points=20)
    assert len(sequence.blocks) == 20


def test_t1_initialisation_is_not_counted_as_a_readout():
    """T1 polarises with the laser, waits, then reads out. Counting laser
    edges would score two readouts per point and silently halve the
    sweep — so a readout is where the counter gate opens."""
    sequence = build("t1", PROFILE, points=20)
    assert sequence.readouts() == 20
    assert sequence.points == 20


def test_an_ungated_rig_falls_back_to_counting_laser_pulses():
    sequence = build("rabi", RigProfile(gate_channel=None), points=10)
    assert sequence.readout_channel == "laser"
    assert sequence.readouts() == 10


# --- Declared parameters --------------------------------------------------


def test_a_generator_states_its_units_rather_than_implying_them():
    params = {p.name: p for p in generator_parameters("rabi")}
    assert params["tau_start"].unit == "s"
    assert params["points"].dtype == "i8"
    assert params["points"].limits == (1, None)


def test_asking_for_an_unknown_generator_lists_the_real_ones():
    with pytest.raises(SequenceError, match="rabi"):
        generator_parameters("rabbi")


def test_building_an_unknown_generator_lists_the_real_ones():
    with pytest.raises(SequenceError, match="hahn_echo"):
        build("hahnecho", PROFILE)


def test_a_misspelled_parameter_is_refused_with_the_real_names():
    with pytest.raises(SequenceError, match="tau_start"):
        build("rabi", PROFILE, taustart=1e-9)


def test_a_parameter_outside_its_limits_is_refused():
    from labpilot.core.errors import LimitError

    with pytest.raises(LimitError):
        build("rabi", PROFILE, points=0)


def test_build_validates_so_a_bad_sequence_is_never_returned():
    """The one entry point the editor and a script share."""
    sequence = build("ramsey", PROFILE, points=3)
    sequence.validate()  # would already have raised inside build()
    assert sequence.readouts() == 6


# --- Serialisation --------------------------------------------------------


@pytest.mark.parametrize("name", ["rabi", "ramsey", "hahn_echo", "t1"])
def test_every_generated_sequence_round_trips_as_data(name):
    import json

    from labpilot.core.pulse.sequence import PulseSequence

    original = build(name, PROFILE)
    revived = PulseSequence.from_dict(json.loads(json.dumps(original.to_dict())))
    revived.validate()
    assert revived.points == original.points
    assert revived.readouts() == original.readouts()
    assert revived.duration == pytest.approx(original.duration)
