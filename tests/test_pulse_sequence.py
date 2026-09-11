"""The pulse sequence object model.

A sequence describes what happens when, on named channels, with one
quantity swept. It knows nothing about sample rates, granularity or
wiring, because the person authoring one has no hardware in front of
them — compiling to a device's format is the pulser adapter's job.

These pin the four places this deliberately differs from Qudi's model:
symbolic channels, a sequence that knows its own sweep, `repetitions`
meaning what it says, and serialisation as data rather than pickle.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from labpilot.core.pulse import (
    DC,
    ChannelMap,
    Chirp,
    Gauss,
    Idle,
    PulseBlock,
    PulseElement,
    PulseSequence,
    SequenceError,
    Shape,
    Sin,
    linear_sweep,
    log_sweep,
    shape_from_dict,
    shape_to_dict,
)
from labpilot.core.pulse.library import RigProfile, build

MW = Sin(amplitude=0.25, frequency=2.87e9)


def readout(name: str = "readout") -> PulseElement:
    return PulseElement(3e-6, {"laser": True, "gate": True}, name=name)


def rabi(points: int = 50, alternating: bool = False) -> PulseSequence:
    """One block, swept by an increment on the microwave element — the
    canonical shape every pulsed experiment here takes."""
    block = PulseBlock(
        "rabi",
        (
            PulseElement(20e-9, {"mw": MW, "laser": False}, increment=40e-9, name="mw"),
            readout(),
            PulseElement(700e-9, {"laser": False}, name="delay"),
            PulseElement(1e-6, {"laser": False}, name="wait"),
        ),
        repetitions=points,
    )
    return PulseSequence(
        "rabi", (block,),
        sweep=linear_sweep("tau", 20e-9, 40e-9, points),
        alternating=alternating,
    )


# --- The sweep primitive ---------------------------------------------------


def test_an_increment_lengthens_the_element_once_per_repetition():
    """Qudi's primitive, and the reason one block is a whole experiment."""
    element = PulseElement(20e-9, {"mw": MW}, increment=40e-9)
    assert element.duration_at(0) == pytest.approx(20e-9)
    assert element.duration_at(49) == pytest.approx(20e-9 + 49 * 40e-9)


def test_repetitions_means_what_it_says():
    """Qudi's `repetitions` means *extra* plays, so 3 runs four times —
    a documented trip-hazard in its own generators."""
    block = PulseBlock("b", (PulseElement(1e-6, {"laser": True}),), repetitions=3)
    assert block.duration == pytest.approx(3e-6)


def test_a_block_that_never_plays_is_refused():
    with pytest.raises(SequenceError, match="never plays"):
        PulseBlock("b", (PulseElement(1e-6),), repetitions=0)


def test_a_linear_sweep_matches_what_the_increment_produces():
    sweep = linear_sweep("tau", 20e-9, 40e-9, 50)
    element = PulseElement(20e-9, {"mw": MW}, increment=40e-9)
    assert sweep.values[-1] == pytest.approx(element.duration_at(49))


def test_a_log_sweep_spans_decades():
    """How T1 is measured — linear spacing wastes almost every point."""
    sweep = log_sweep("tau", 1e-6, 5e-3, 20)
    assert sweep.values[0] == pytest.approx(1e-6)
    assert sweep.values[-1] == pytest.approx(5e-3)
    assert len(sweep) == 20


@pytest.mark.parametrize("factory", [linear_sweep, log_sweep])
def test_a_sweep_needs_at_least_one_point(factory):
    with pytest.raises(SequenceError, match="at least one point"):
        factory("tau", 1e-9, 2e-9, 0)


# --- Counting readouts -----------------------------------------------------


def test_readouts_are_counted_as_gate_rising_edges():
    """Counted the way the gated counter will see them, so the counter's
    gate count and the sequence cannot silently disagree."""
    assert rabi(points=50).readouts() == 50


def test_a_laser_held_high_across_elements_is_one_readout_not_two():
    block = PulseBlock("b", (
        PulseElement(1e-6, {"laser": True}),
        PulseElement(1e-6, {"laser": True}),
        PulseElement(1e-6, {"laser": False}),
    ))
    sequence = PulseSequence("s", (block,))
    assert sequence.readouts() == 1


def test_alternating_halves_the_points():
    block = PulseBlock("b", (
        PulseElement(1e-6, {"mw": MW, "laser": False}),
        readout("signal"),
        PulseElement(1e-6, {"laser": False}),
        readout("reference"),
        PulseElement(1e-6, {"laser": False}),
    ), repetitions=10)
    sequence = PulseSequence("s", (block,), alternating=True)
    assert sequence.readouts() == 20
    assert sequence.points == 10


# --- Validation ------------------------------------------------------------


def test_a_well_formed_sequence_validates():
    rabi().validate()


def test_a_sequence_with_no_readout_is_refused():
    """It would run and produce nothing, which is the worst failure mode."""
    block = PulseBlock("b", (PulseElement(1e-6, {"laser": False, "mw": MW}),))
    with pytest.raises(SequenceError, match="no readout"):
        PulseSequence("s", (block,)).validate()


def test_a_laser_channel_no_element_uses_is_refused():
    block = PulseBlock("b", (PulseElement(1e-6, {"green": True}),))
    with pytest.raises(SequenceError, match="laser channel"):
        PulseSequence("s", (block,), laser_channel="laser").validate()


def test_an_empty_sequence_is_refused():
    with pytest.raises(SequenceError, match="no blocks"):
        PulseSequence("s").validate()


def test_a_sweep_that_disagrees_with_the_repetitions_is_refused():
    """The mistake that silently misaligns every point of a measurement."""
    sequence = rabi(points=50).evolve(sweep=linear_sweep("tau", 20e-9, 40e-9, 40))
    with pytest.raises(SequenceError, match="disagree"):
        sequence.validate()


def test_an_alternating_sequence_with_an_odd_readout_count_is_refused():
    with pytest.raises(SequenceError, match="pair up"):
        rabi(points=5, alternating=True).evolve(sweep=None).validate()


def test_ignoring_a_readout_that_does_not_exist_is_refused():
    with pytest.raises(SequenceError, match="only 50"):
        rabi().evolve(ignore_lasers=(99,)).validate()


def test_a_negative_duration_is_refused_at_construction():
    with pytest.raises(SequenceError, match="negative duration"):
        PulseElement(-1e-9, {"laser": True})


def test_a_channel_that_is_neither_bool_nor_shape_is_refused():
    with pytest.raises(SequenceError, match="must be a bool"):
        PulseElement(1e-6, {"mw": 0.5})


# --- Symbolic channels -----------------------------------------------------


def test_channels_are_symbolic_not_physical():
    """Qudi bakes d_ch1 into its generation parameters, tying a saved
    sequence to one rig's wiring."""
    assert rabi().channels == {"mw", "laser", "gate"}


def test_a_channel_map_resolves_every_used_channel():
    mapping = ChannelMap({"mw": "a_ch1", "laser": "d_ch1", "gate": "d_ch2"})
    mapping.resolve(rabi())
    assert mapping["laser"] == "d_ch1"


def test_an_unmapped_channel_is_reported_before_upload():
    mapping = ChannelMap({"mw": "a_ch1"})
    with pytest.raises(SequenceError, match=r"gate"):
        mapping.resolve(rabi())


def test_asking_for_an_unbound_channel_says_what_is_bound():
    mapping = ChannelMap({"mw": "a_ch1"})
    with pytest.raises(SequenceError, match="mw"):
        mapping["laser"]


# --- Shapes ----------------------------------------------------------------


def test_a_shape_declares_its_parameters_as_parameter_objects():
    """Which is what lets the existing settings-tree widgets render a
    shape editor with nothing new written."""
    names = [p.name for p in Sin.params]
    assert names == ["amplitude", "frequency", "phase"]
    assert Sin.params[0].limits == (0.0, None)
    assert Sin.params[1].unit == "Hz"


def test_idle_samples_to_zero():
    assert np.all(Idle().sample(np.linspace(0, 1e-6, 16), 1e-6) == 0)


def test_dc_samples_to_a_constant_in_volts():
    """Volts, not a normalised +/-1 — normalising is the driver's job,
    since only the driver knows its own Vpp."""
    assert np.allclose(DC(voltage=0.4).sample(np.zeros(4), 1e-6), 0.4)


def test_a_sine_uses_absolute_time_so_phase_stays_coherent():
    """Ramsey and Hahn measure a phase difference; they are simply wrong
    without this."""
    shape = Sin(amplitude=1.0, frequency=1e6, phase=0.0)
    period = 1e-6
    early = shape.sample(np.array([0.0]), period)
    later = shape.sample(np.array([3 * period]), period)
    assert early[0] == pytest.approx(later[0], abs=1e-9)


def test_phase_shifts_the_sine():
    t = np.array([0.25e-6])
    assert Sin(1.0, 1e6, 0.0).sample(t, 1e-6)[0] == pytest.approx(1.0, abs=1e-9)
    assert Sin(1.0, 1e6, 180.0).sample(t, 1e-6)[0] == pytest.approx(-1.0, abs=1e-9)


def test_a_gaussian_peaks_in_the_middle_of_its_element():
    t = np.linspace(0, 1e-6, 201)
    envelope = np.abs(Gauss(1.0, 5e6, 90.0).sample(t, 1e-6))
    assert envelope.argmax() == pytest.approx(100, abs=6)


def test_a_chirp_sweeps_frequency_across_the_element():
    """Zero crossings bunch up as the instantaneous frequency rises."""
    t = np.linspace(0, 1e-5, 4001)
    values = Chirp(1.0, 1e5, 2e6).sample(t, 1e-5)
    crossings = np.diff(np.signbit(values)).nonzero()[0]
    first_gap = crossings[1] - crossings[0]
    last_gap = crossings[-1] - crossings[-2]
    assert last_gap < first_gap


def test_every_shape_satisfies_the_protocol():
    for shape in (Idle(), DC(), Sin(), Gauss(), Chirp()):
        assert isinstance(shape, Shape)


def test_a_shape_round_trips_through_its_dict_form():
    shape = Sin(amplitude=0.3, frequency=2.87e9, phase=90.0)
    assert shape_from_dict(shape_to_dict(shape)) == shape


def test_an_unknown_shape_name_lists_the_known_ones():
    with pytest.raises(ValueError, match="Sin"):
        shape_from_dict({"shape": "Squircle"})


def test_an_undeclared_shape_parameter_is_refused():
    with pytest.raises(ValueError, match="amplitude"):
        shape_from_dict({"shape": "Sin", "amplitude": 1.0, "freq": 2.87e9})


# --- Serialisation ---------------------------------------------------------


def test_a_sequence_survives_a_json_round_trip():
    """Data, never pickle — Qudi pays ~300 lines of loader for pickling
    its objects, including a FIXME repairing one pickle destroyed."""
    original = rabi()
    revived = PulseSequence.from_dict(json.loads(json.dumps(original.to_dict())))

    revived.validate()
    assert revived.name == original.name
    assert revived.points == original.points
    assert revived.duration == pytest.approx(original.duration)
    assert revived.channels == original.channels


def test_shapes_survive_the_round_trip_as_shapes():
    revived = PulseSequence.from_dict(json.loads(json.dumps(rabi().to_dict())))
    mw = revived.blocks[0].elements[0].channels["mw"]
    assert isinstance(mw, Sin)
    assert mw.frequency == pytest.approx(2.87e9)


def test_digital_levels_survive_as_booleans_not_shapes():
    revived = PulseSequence.from_dict(json.loads(json.dumps(rabi().to_dict())))
    assert revived.blocks[0].elements[1].channels["laser"] is True


def test_the_sweep_survives_the_round_trip():
    revived = PulseSequence.from_dict(json.loads(json.dumps(rabi().to_dict())))
    assert revived.sweep.name == "tau"
    assert revived.sweep.unit == "s"
    assert len(revived.sweep) == 50


def test_a_sequence_file_is_small_enough_to_read_and_diff():
    """It is meant to be versioned and shared, so a 50-point Rabi must not
    serialise its expansion."""
    assert len(json.dumps(rabi().to_dict())) < 4000


# --- Sweeps something else steps --------------------------------------------


def stepped(points: int = 20, **fields) -> PulseSequence:
    """One fixed pattern with a frequency axis — a pulsed ODMR."""
    return build("pulsed_odmr", RigProfile(), points=points).evolve(**fields)


def test_a_stepped_sweep_says_who_owns_its_axis():
    sequence = stepped()
    assert sequence.sweep.stepped
    assert sequence.sweep.parameter == "frequency"
    assert not rabi().sweep.stepped


def test_many_points_and_one_readout_is_valid_when_something_else_steps():
    """The rule that makes a played sweep safe — points must equal
    readouts — is exactly wrong here: the points are not in the sequence,
    so one pass is one point and checking against `len(sweep)` would
    refuse every pulsed ODMR."""
    sequence = stepped(points=101)
    assert sequence.points == 101
    assert sequence.readouts() == 1
    sequence.validate()


def test_a_stepped_sequence_that_reads_out_twice_is_still_refused():
    """The rule is not dropped, only restated: one pass is one point, so
    two readouts per pass means two points per setting and a curve that
    pairs the wrong numbers with the wrong frequencies."""
    doubled = stepped().evolve(
        blocks=(stepped().blocks[0], stepped().blocks[0]),
    )
    with pytest.raises(SequenceError, match="one readout"):
        doubled.validate()


def test_an_alternating_stepped_sequence_wants_exactly_two_readouts():
    with pytest.raises(SequenceError, match="signal and reference"):
        stepped().evolve(alternating=True).validate()


def test_who_steps_the_sweep_survives_the_round_trip():
    """A saved pulsed ODMR that came back as a played sweep would be
    refused on load, and the reason would be a missing JSON key."""
    revived = PulseSequence.from_dict(json.loads(json.dumps(stepped().to_dict())))
    assert revived.sweep.parameter == "frequency"
    assert revived.sweep.unit == "Hz"
    revived.validate()
