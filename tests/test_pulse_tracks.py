"""The pulse editor's model — a timeline of tracks, and what it compiles to.

Editing is horizontal and the model is vertical, and this is the module
that reconciles them. A person draws a laser pulse on one lane and a
microwave pulse on another, neither knowing about the other's edges; a
pulser plays a run of time slices each of which names every channel.

One rule does the whole conversion: **every edge on every track is an
element boundary**. What these pin is that rule, and the three things
around it that are easy to get wrong and expensive to find later —
trailing silence, a sweep that appears more than once per pass, and a
region cut in half by another track.
"""

from __future__ import annotations

import pytest

from labpilot.core.pulse import SequenceError, Sin
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.tracks import (
    FREQUENCY,
    LINEAR,
    LOG,
    TIME,
    Pulse,
    Region,
    SweepAxis,
    Timeline,
    Track,
    blank_pulse,
    ordered_channels,
    timeline_from_sequence,
)

US = 1e-6
NS = 1e-9
CHANNELS = ("laser", "mw", "gate")


def simple(sweep: SweepAxis | None = None, duration: float = 5 * US) -> Timeline:
    """A Rabi drawn by hand: drive, then read out, then wait."""
    return Timeline(
        tracks=[
            Track("laser", [Pulse(20 * NS, 3020 * NS, name="readout")]),
            Track("mw", [Pulse(0.0, 20 * NS, Sin(), "drive")]),
            Track("gate", [Pulse(20 * NS, 3020 * NS)]),
        ],
        duration=duration,
        sweep=sweep,
    )


def tau(start: float, stop: float, **kwargs) -> SweepAxis:
    return SweepAxis(regions=(Region(start, stop),), **kwargs)


# --- Every edge is an element boundary --------------------------------------


def test_the_slices_come_from_every_track_s_edges():
    """Three lanes with edges at 0, 20 ns and 3020 ns, plus the
    timeline's own end, make four boundaries and three elements."""
    sequence = simple().to_sequence("rabi", validate=False)
    lengths = [e.duration for e in sequence.blocks[0].elements]
    assert lengths == pytest.approx([20 * NS, 3000 * NS, 5 * US - 3020 * NS])


def test_each_slice_names_every_channel():
    """What makes it playable: a pulser needs a level for every channel
    at every instant, not only for the one whose pulse started here."""
    element = simple().to_sequence("rabi", validate=False).blocks[0].elements[0]
    assert set(element.channels) == set(CHANNELS)
    assert element.channels["laser"] is False
    assert isinstance(element.channels["mw"], Sin)


def test_a_gap_between_pulses_is_a_slice_with_everything_low():
    line = Timeline(
        tracks=[Track("laser", [Pulse(0.0, US), Pulse(2 * US, 3 * US)])],
        duration=3 * US,
    )
    elements = line.to_sequence("gapped", validate=False).blocks[0].elements
    assert [e.channels["laser"] for e in elements] == [True, False, True]


def test_an_element_takes_its_name_from_the_pulse_that_spans_it():
    """Names are what make a saved sequence readable a month later."""
    names = [e.name for e in simple().to_sequence("rabi", validate=False).blocks[0].elements]
    assert names[0] == "drive"
    assert names[1] == "readout"


# --- Trailing silence is load-bearing ---------------------------------------


def test_the_timeline_has_a_length_of_its_own():
    """The repolarisation wait is silence, and silence has no edges. A
    timeline that stopped at its last drawn pulse would drop it — and a
    sequence that repolarises for 0 ns instead of 1 us still runs, still
    produces a curve, and produces the wrong one."""
    short = simple(duration=3020 * NS).to_sequence("rabi", validate=False)
    long = simple(duration=5 * US).to_sequence("rabi", validate=False)
    assert long.duration - short.duration == pytest.approx(5 * US - 3020 * NS)


def test_a_declared_length_shorter_than_the_pulses_does_not_truncate_them():
    """Dragging a pulse past the end lengthens the timeline rather than
    silently cutting the pulse in half."""
    line = simple(duration=1 * US)
    assert line.end == pytest.approx(3020 * NS)


def test_no_pulses_anywhere_is_refused_rather_than_played():
    with pytest.raises(SequenceError, match="nothing drawn"):
        Timeline(tracks=[Track("laser")]).to_sequence("empty", validate=False)


def test_no_tracks_at_all_says_so():
    with pytest.raises(SequenceError, match="no tracks"):
        Timeline().to_sequence("empty", validate=False)


# --- One channel, one level at a time ---------------------------------------


def test_two_pulses_overlapping_on_one_track_is_refused():
    """Not a sequence a pulser could play, and left alone it would give
    an element whose value depends on which pulse was checked first."""
    line = Timeline(
        tracks=[Track("laser", [Pulse(0.0, 2 * US, name="a"), Pulse(US, 3 * US, name="b")])],
        duration=3 * US,
    )
    with pytest.raises(SequenceError, match="one level at a time"):
        line.to_sequence("clash", validate=False)


def test_pulses_that_merely_touch_are_fine():
    line = Timeline(
        tracks=[Track("laser", [Pulse(0.0, US), Pulse(US, 2 * US)])], duration=2 * US
    )
    assert len(line.to_sequence("abutting", validate=False).blocks[0].elements) == 2


def test_a_pulse_that_ends_before_it_starts_is_refused_at_construction():
    with pytest.raises(SequenceError, match="ends before it starts"):
        Pulse(2 * US, US)


def test_a_pulse_cannot_start_before_zero():
    with pytest.raises(SequenceError, match="before zero"):
        Pulse(-US, US)


# --- The sweep is a set of regions ------------------------------------------


def test_a_region_becomes_an_increment_and_a_repetition_count():
    """The model's own sweep primitive: one block, played `points` times,
    one element growing by `step` each pass."""
    sequence = simple(tau(0.0, 20 * NS, points=50, step=20 * NS)).to_sequence("rabi")
    block = sequence.blocks[0]
    assert block.repetitions == 50
    assert [e.increment for e in block.elements] == pytest.approx([20 * NS, 0.0, 0.0])
    assert sequence.points == 50


def test_the_region_may_be_a_gap_rather_than_a_pulse():
    """Ramsey's tau is idle time between two pulses. A gap is not a drawn
    object, so a per-pulse increment could not express it at all."""
    line = Timeline(
        tracks=[
            Track("mw", [Pulse(0.0, 50 * NS, Sin()), Pulse(100 * NS, 150 * NS, Sin())]),
            Track("gate", [Pulse(150 * NS, 3150 * NS)]),
            Track("laser", [Pulse(150 * NS, 3150 * NS)]),
        ],
        duration=4 * US,
        sweep=tau(50 * NS, 100 * NS, points=20, step=50 * NS),
    )
    sequence = line.to_sequence("ramsey")
    swept = [e for e in sequence.blocks[0].elements if e.increment]
    assert len(swept) == 1
    assert swept[0].channels["mw"] is False  # it is the gap, not the pulse
    assert sequence.sweep.values[:3] == pytest.approx([50 * NS, 100 * NS, 150 * NS])


def test_several_regions_grow_together_under_one_axis():
    """A Ramsey's tau appears once per alternating arm and a Hahn echo's
    twice. They are the same tau, so they are regions of one axis rather
    than two sweeps that have to be kept in step by hand."""
    line = simple(
        SweepAxis(
            regions=(Region(0.0, 20 * NS), Region(3020 * NS, 3040 * NS)),
            points=10, step=20 * NS,
        ),
        duration=5 * US,
    )
    swept = [e for e in line.to_sequence("two", validate=False).blocks[0].elements if e.increment]
    assert len(swept) == 2
    assert all(e.increment == pytest.approx(20 * NS) for e in swept)


def test_regions_of_different_lengths_are_refused():
    """They take the same value each point, so starting different lengths
    means the axis is sweeping two different things under one name."""
    with pytest.raises(SequenceError, match="different lengths"):
        SweepAxis(regions=(Region(0.0, 20 * NS), Region(1 * US, 1.1 * US)))


def test_an_empty_region_says_to_drag_its_edges_apart():
    with pytest.raises(SequenceError, match="empty"):
        Region(US, US)


def test_a_sweep_with_no_region_is_refused():
    with pytest.raises(SequenceError, match="at least one"):
        SweepAxis(regions=())


def test_a_region_past_the_end_of_the_timeline_says_where_to_move_it():
    """Marking a sweep out past everything drawn is a slip, and silently
    extending the sequence to reach it would produce a run whose tau
    measures dead air."""
    with pytest.raises(SequenceError, match="past the end"):
        simple(tau(8 * US, 9 * US), duration=5 * US).to_sequence("lost", validate=False)


def test_a_region_cut_in_half_grows_only_its_second_part():
    """Another track's edge inside the region splits it. The edge has to
    stay where it was drawn, so the part after it is what grows — and the
    region as a whole still measures the sweep's value."""
    line = Timeline(
        tracks=[
            Track("mw", [Pulse(0.0, 100 * NS, Sin())]),
            Track("trigger", [Pulse(40 * NS, 60 * NS)]),  # cuts the region
            Track("gate", [Pulse(100 * NS, 3100 * NS)]),
            Track("laser", [Pulse(100 * NS, 3100 * NS)]),
        ],
        duration=4 * US,
        sweep=tau(0.0, 100 * NS, points=5, step=100 * NS),
    )
    block = line.to_sequence("split", validate=False).blocks[0]
    swept = [e for e in block.elements if e.increment]
    assert len(swept) == 1
    # First pass: the region still measures 100 ns in total.
    within = [e.duration for e in block.elements[:3]]
    assert sum(within) == pytest.approx(100 * NS)


# --- Log spacing ------------------------------------------------------------


def test_log_spacing_becomes_one_block_per_point():
    """A geometric series has no constant increment, so the per-repetition
    primitive cannot express it and there is nothing else it could be."""
    line = Timeline(
        tracks=[
            Track("laser", [Pulse(0.0, 3 * US), Pulse(5 * US, 8 * US)]),
            Track("gate", [Pulse(5 * US, 8 * US)]),
        ],
        duration=9 * US,
        sweep=SweepAxis(
            regions=(Region(3 * US, 5 * US),), points=6,
            stop_value=100 * US, spacing=LOG,
        ),
    )
    sequence = line.to_sequence("t1")
    assert len(sequence.blocks) == 6
    assert all(block.repetitions == 1 for block in sequence.blocks)
    assert sequence.points == 6
    assert sequence.sweep.values[0] == pytest.approx(2 * US)
    assert sequence.sweep.values[-1] == pytest.approx(100 * US)


def test_both_spacings_produce_the_same_kind_of_sweep():
    """So nothing downstream has to know which was used."""
    line = simple(tau(0.0, 20 * NS, points=5, step=20 * NS))
    linear = line.to_sequence("a")
    line.sweep = tau(0.0, 20 * NS, points=5, stop_value=200 * NS, spacing=LOG)
    logarithmic = line.to_sequence("b")

    assert linear.sweep.name == logarithmic.sweep.name == "tau"
    assert len(linear.sweep) == len(logarithmic.sweep) == 5
    assert linear.points == logarithmic.points


def test_an_unknown_spacing_lists_the_real_ones():
    with pytest.raises(SequenceError, match="linear"):
        tau(0.0, 20 * NS, spacing="fibonacci")


# --- Back to tracks ---------------------------------------------------------


def test_adjacent_slices_merge_back_into_the_pulse_that_was_drawn():
    """A laser pulse cut into three by other tracks' edges is one drawn
    object again, not three."""
    sequence = build("hahn_echo", RigProfile(), points=4)
    line = timeline_from_sequence(sequence, CHANNELS)
    assert len(line.track("laser").pulses) == 2  # signal and reference readouts


def test_a_shape_is_compared_by_its_parameters_not_its_identity():
    """Two Sins of equal amplitude, frequency and phase in consecutive
    elements are one microwave pulse another track's edge cut in half."""
    line = Timeline(
        tracks=[
            Track("mw", [Pulse(0.0, 100 * NS, Sin())]),
            Track("gate", [Pulse(50 * NS, 60 * NS)]),
        ],
        duration=200 * NS,
    )
    revived = timeline_from_sequence(line.to_sequence("cut", validate=False), CHANNELS)
    assert len(revived.track("mw").pulses) == 1


def test_a_declared_channel_gets_a_lane_before_anything_uses_it():
    """So a loaded sequence still has somewhere to put the laser."""
    line = timeline_from_sequence(build("t1", RigProfile(), points=4), CHANNELS)
    assert line.channels[:3] == ["laser", "mw", "gate"]
    assert line.track("mw").pulses == []


def test_lane_order_is_stable_and_readable():
    """Not dict insertion order: laser, microwave and gate read in that
    order on every bench, and an edit must not reshuffle the lanes."""
    assert ordered_channels(("gate", "aux", "mw", "laser")) == [
        "laser", "mw", "gate", "aux"
    ]


@pytest.mark.parametrize("name", ["rabi", "ramsey", "hahn_echo", "t1"])
def test_a_generated_sequence_round_trips_through_the_timeline(name):
    """What makes "start from Rabi, then edit" one gesture rather than
    two authoring paths that cannot meet."""
    original = build(name, RigProfile(), points=6)
    line = timeline_from_sequence(original, CHANNELS)
    revived = line.to_sequence(
        name, alternating=original.alternating, gate_channel=original.gate_channel
    )

    assert revived.points == original.points
    assert revived.readouts() == original.readouts()
    assert revived.duration == pytest.approx(original.duration)
    assert revived.channels == original.channels
    assert revived.sweep.array == pytest.approx(original.sweep.array)


@pytest.mark.parametrize("name", ["rabi", "ramsey", "hahn_echo"])
def test_the_recovered_sweep_marks_every_place_tau_appears(name):
    """A Ramsey has one region per alternating arm and a Hahn echo two,
    and losing any of them would sweep half the sequence."""
    sequence = build(name, RigProfile(), points=6)
    axis = timeline_from_sequence(sequence, CHANNELS).sweep
    expected = {"rabi": 1, "ramsey": 2, "hahn_echo": 4}[name]
    assert len(axis.regions) == expected
    assert axis.spacing == LINEAR


def test_a_log_sweep_comes_back_as_a_log_sweep():
    axis = timeline_from_sequence(build("t1", RigProfile(), points=6), CHANNELS).sweep
    assert axis.spacing == LOG
    assert axis.stop_value > axis.length


def test_a_sequence_with_no_sweep_has_no_region():
    line = simple()
    revived = timeline_from_sequence(line.to_sequence("flat", validate=False), CHANNELS)
    assert revived.sweep is None


# --- Storage ----------------------------------------------------------------


def test_a_timeline_stores_as_plain_data():
    """It is a workflow parameter, so it has to survive JSON — no pulse
    objects, no pickle."""
    import json

    line = simple(tau(0.0, 20 * NS, points=8, step=20 * NS))
    revived = Timeline.from_dict(json.loads(json.dumps(line.to_dict())))

    assert revived.duration == pytest.approx(line.duration)
    assert revived.channels == line.channels
    assert isinstance(revived.track("mw").pulses[0].value, Sin)
    assert revived.sweep.points == 8
    assert len(revived.sweep.regions) == 1


def test_an_analog_pulse_keeps_its_shape_parameters_through_storage():
    line = Timeline(
        tracks=[Track("mw", [Pulse(0.0, 20 * NS, Sin(amplitude=0.4, frequency=2.8e9))])],
        duration=US,
    )
    drive = Timeline.from_dict(line.to_dict()).track("mw").pulses[0]
    assert drive.value.amplitude == pytest.approx(0.4)
    assert drive.value.frequency == pytest.approx(2.8e9)


def test_a_new_pulse_is_digital_unless_a_shape_is_named():
    assert blank_pulse(0.0, 100 * NS).value is True
    assert isinstance(blank_pulse(0.0, 100 * NS, "Sin").value, Sin)


def test_a_new_pulse_with_an_unknown_shape_lists_the_real_ones():
    with pytest.raises(SequenceError, match="Sin"):
        blank_pulse(0.0, 100 * NS, "Squircle")


def test_asking_for_a_track_that_is_not_there_lists_the_ones_that_are():
    with pytest.raises(KeyError, match="laser"):
        simple().track("nonexistent")


# --- What the editor produces is what the pulser plays ----------------------


def test_a_hand_drawn_timeline_becomes_a_playable_sequence():
    sequence = simple(tau(0.0, 20 * NS, points=10, step=20 * NS)).to_sequence("hand")
    assert sequence.readouts() == 10
    assert sequence.readout_window() == pytest.approx(3 * US)


def test_a_timeline_that_never_illuminates_the_sample_is_refused():
    """Microwave drawn, laser lane empty. It would upload and play and
    count nothing at all."""
    line = Timeline(
        tracks=[Track("laser"), Track("mw", [Pulse(0.0, 20 * NS, Sin())])],
        duration=US,
    )
    with pytest.raises(SequenceError, match="laser channel"):
        line.to_sequence("broken")


def test_an_empty_gate_lane_falls_back_to_the_laser_pulses():
    """An ungated rig is a real rig: with nothing on the APD lane, the
    laser pulses are the readouts, which is the model's own rule rather
    than something the editor decides."""
    line = Timeline(
        tracks=[Track("laser", [Pulse(20 * NS, 3020 * NS)]), Track("gate")],
        duration=5 * US,
    )
    assert line.to_sequence("ungated").readouts() == 1


def test_an_empty_lane_is_not_a_channel_the_sequence_claims():
    """A rig with a microwave source and a T1 that does not use it: the
    saved sequence must not claim `mw`, or a pulser has to have that
    channel free to play it."""
    line = Timeline(
        tracks=[
            Track("laser", [Pulse(0.0, 3 * US)]),
            Track("mw"),
            Track("gate", [Pulse(0.0, 3 * US)]),
        ],
        duration=4 * US,
    )
    assert line.to_sequence("t1ish").channels == frozenset({"laser", "gate"})


def test_a_half_drawn_timeline_can_still_be_rendered():
    """Mid-edit there is no readout yet, and refusing to draw it would
    make the editor unusable."""
    line = Timeline(tracks=[Track("mw", [Pulse(0.0, 20 * NS, Sin())])], duration=US)
    assert len(line.to_sequence("wip", validate=False).blocks[0].elements) == 2


# --- A sweep the pulser does not play ---------------------------------------
#
# Time and frequency are the same editor, one field apart, and these pin
# the seam. A frequency sweep marks nothing on the timeline because there
# is nothing to mark: the drawn pattern plays unchanged and something else
# moves between passes.


def frequency_axis(**fields) -> SweepAxis:
    return SweepAxis(**{
        "quantity": FREQUENCY, "start_value": 2.82e9,
        "stop_value": 2.92e9, "points": 11, **fields,
    })


def test_a_frequency_sweep_needs_no_region():
    """The rule a time sweep depends on — at least one marked region —
    would refuse every pulsed ODMR, because a carrier frequency is not an
    interval of the timeline."""
    axis = frequency_axis()
    assert axis.regions == ()
    assert axis.stepped
    assert axis.length == 0.0


def test_a_time_sweep_still_needs_one():
    with pytest.raises(SequenceError, match="at least one marked region"):
        SweepAxis(points=10)


def test_a_frequency_sweep_is_named_and_labelled_in_hertz():
    """Carried over from a time sweep, the defaults would label a 2.87 GHz
    axis "tau" in seconds."""
    axis = frequency_axis()
    assert axis.name == "frequency"
    assert axis.unit == "Hz"
    assert axis.sweep().unit == "Hz"


def test_a_name_someone_chose_survives_the_switch():
    assert frequency_axis(name="detuning").name == "detuning"


def test_endpoints_are_required_for_a_frequency_sweep():
    with pytest.raises(SequenceError, match="positive start and stop"):
        SweepAxis(quantity=FREQUENCY, points=10)


def test_the_sequence_carries_who_steps_it():
    """`parameter` is the whole mechanism: it is what tells the run to
    write each value to an instrument rather than expect the pulser to
    have played them."""
    line = simple(frequency_axis())
    sequence = line.to_sequence("odmr")
    assert sequence.sweep.parameter == "frequency"
    assert sequence.sweep.stepped
    assert len(sequence.sweep) == 11


def test_the_drawn_pattern_is_untouched_by_a_frequency_sweep():
    """One block, played once, with no increment anywhere — a time sweep's
    whole mechanism is absent because there is nothing to vary."""
    sequence = simple(frequency_axis()).to_sequence("odmr")
    assert len(sequence.blocks) == 1
    assert sequence.blocks[0].repetitions == 1
    assert all(e.increment == 0.0 for e in sequence.blocks[0].elements)
    assert sequence.readouts() == 1


def test_a_stepped_sweep_survives_a_round_trip_through_the_editor():
    """Load a saved pulsed ODMR back into the canvas and the axis comes
    back — from the sweep's own values, since the elements hold no trace
    of it."""
    original = simple(frequency_axis(points=7)).to_sequence("odmr")
    line = timeline_from_sequence(original, CHANNELS)

    assert line.sweep is not None
    assert line.sweep.quantity == FREQUENCY
    assert line.sweep.points == 7
    assert line.sweep.start_value == pytest.approx(2.82e9)
    assert line.sweep.stop_value == pytest.approx(2.92e9)
    assert line.to_sequence("odmr").sweep.values == original.sweep.values


def test_switching_quantity_keeps_every_drawn_pulse_where_it_was():
    """The editor's gesture: a Rabi drawing becomes a pulsed ODMR by
    changing one field, and nothing on the canvas moves."""
    line = simple(SweepAxis(regions=(Region(0.0, 20 * NS),), points=10))
    before = [(p.start, p.stop) for t in line.tracks for p in t.sorted()]
    line.sweep = frequency_axis()
    assert [(p.start, p.stop) for t in line.tracks for p in t.sorted()] == before


def test_an_unknown_quantity_is_refused_by_name():
    with pytest.raises(SequenceError, match="Unknown sweep quantity"):
        SweepAxis(regions=(Region(0.0, 20 * NS),), quantity="voltage")


def test_time_is_still_the_default():
    axis = SweepAxis(regions=(Region(0.0, 20 * NS),), points=5)
    assert axis.quantity == TIME
    assert not axis.stepped
    assert not axis.sweep().stepped
