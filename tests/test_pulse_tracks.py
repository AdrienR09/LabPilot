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

from dataclasses import replace

import pytest

from labpilot.core.pulse import SequenceError, Sin
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.tracks import (
    DURATION,
    FREQUENCY,
    LINEAR,
    LOG,
    Pulse,
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


def swept(line: Timeline, *spans: tuple[float, float], **axis) -> Timeline:
    """Mark the pulses covering `spans` as swept, and set the axis.

    The sweep is per-pulse now, so a test marks the pulse rather than
    dragging a region over it — and a span with no pulse under it becomes
    a timing block, which is how a *gap* is swept.
    """
    for start, stop in spans:
        for track in line.tracks:
            for index, pulse in enumerate(track.pulses):
                if abs(pulse.start - start) < 1e-15 and abs(pulse.stop - stop) < 1e-15:
                    track.pulses[index] = replace(pulse, sweep=DURATION)
                    break
            else:
                continue
            break
        else:
            line.tracks[-1].pulses.append(
                Pulse(start, stop, True, "tau", sweep=DURATION, drives=False)
            )
    line.sweep = SweepAxis(**axis)
    return line


# --- Every edge is an element boundary --------------------------------------


def test_the_slices_come_from_every_track_s_edges():
    """Three lanes with edges at 0, 20 ns and 3020 ns, plus the
    timeline's own end, make four boundaries and three elements."""
    sequence = simple().to_sequence("rabi", validate=False)
    lengths = [e.duration for e in sequence.blocks[0].elements]
    assert lengths == pytest.approx([20 * NS, 3000 * NS, 5 * US - 3020 * NS])


def test_each_slice_names_only_the_channels_it_asserts():
    """A channel absent from an element is low by definition, so spelling
    out a `false` per idle lane says nothing — and on a six-channel rig
    the nothings are most of the file."""
    element = simple().to_sequence("rabi", validate=False).blocks[0].elements[0]
    assert set(element.channels) == {"mw"}
    assert isinstance(element.channels["mw"], Sin)
    # Which is the same statement, read the other way.
    assert element.is_high("laser") is False


def test_a_gap_between_pulses_is_a_slice_that_names_nothing():
    line = Timeline(
        tracks=[Track("laser", [Pulse(0.0, US), Pulse(2 * US, 3 * US)])],
        duration=3 * US,
    )
    elements = line.to_sequence("gapped", validate=False).blocks[0].elements
    assert [e.is_high("laser") for e in elements] == [True, False, True]
    assert elements[1].channels == {}


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


# --- The sweep belongs to a pulse -------------------------------------------


def test_a_swept_pulse_becomes_an_increment_and_a_repetition_count():
    """The model's own sweep primitive: one block, played `points` times,
    one element growing each pass."""
    line = swept(simple(), (0.0, 20 * NS), points=50, stop=1000 * NS)
    sequence = line.to_sequence("rabi")
    block = sequence.blocks[0]
    assert block.repetitions == 50
    assert [e.increment for e in block.elements] == pytest.approx([20 * NS, 0.0, 0.0])
    assert sequence.points == 50


def test_the_swept_pulse_may_be_a_gap_that_drives_nothing():
    """Ramsey's tau is idle time between two pulses. Drawing it as a
    timing block is what makes it an object you can click and mark — the
    whole reason the sweep stopped being a free-floating region."""
    line = Timeline(
        tracks=[
            Track("mw", [Pulse(0.0, 50 * NS, Sin()), Pulse(100 * NS, 150 * NS, Sin())]),
            Track("gate", [
                Pulse(150 * NS, 3150 * NS),
                Pulse(50 * NS, 100 * NS, True, "tau", sweep=DURATION, drives=False),
            ]),
            Track("laser", [Pulse(150 * NS, 3150 * NS)]),
        ],
        duration=4 * US,
        sweep=SweepAxis(points=20, stop=1000 * NS),
    )
    sequence = line.to_sequence("ramsey")
    marked = [e for e in sequence.blocks[0].elements if e.increment]
    assert len(marked) == 1
    # The timing block drives nothing, so the gate is low across it — it
    # is the gap, not a readout, and it names no channel at all.
    assert marked[0].channels == {}
    assert marked[0].is_high("gate") is False
    assert sequence.sweep.values[:3] == pytest.approx([50 * NS, 100 * NS, 150 * NS])


def test_a_timing_block_on_the_readout_lane_is_not_a_readout():
    """The same flag, read the way the readout lane makes it mean: a
    driving pulse there opens the counter gate and a non-driving one is a
    delay between readouts."""
    line = Timeline(
        tracks=[
            Track("laser", [Pulse(0.0, 3 * US)]),
            Track("gate", [
                Pulse(0.0, 3 * US, name="readout"),
                Pulse(4 * US, 5 * US, True, "wait", drives=False),
            ]),
        ],
        duration=6 * US,
    )
    sequence = line.to_sequence("one")
    assert sequence.readouts() == 1
    # It still holds its time, which is the point of drawing it.
    assert sequence.duration == pytest.approx(6 * US)


def test_a_lane_holding_only_timing_blocks_is_not_a_channel():
    """Writing it into every element as `False` would make the sequence
    claim a channel the pulser then has to have free."""
    line = Timeline(
        tracks=[
            Track("laser", [Pulse(0.0, 3 * US)]),
            Track("gate", [Pulse(0.0, 3 * US)]),
            Track("mw", [Pulse(4 * US, 5 * US, True, "tau", drives=False)]),
        ],
        duration=6 * US,
    )
    assert line.to_sequence("t1ish").channels == frozenset({"laser", "gate"})


def test_several_marked_pulses_grow_together_under_one_axis():
    """A Ramsey's tau appears once per alternating arm and a Hahn echo's
    twice. Marking each of them is what says they are one axis rather than
    two sweeps kept in step by hand."""
    line = swept(
        simple(), (0.0, 20 * NS), (3020 * NS, 3040 * NS),
        points=10, stop=200 * NS,
    )
    block = line.to_sequence("two", validate=False).blocks[0]
    marked = [e for e in block.elements if e.increment]
    assert len(marked) == 2
    assert all(e.increment == pytest.approx(20 * NS) for e in marked)


def test_marked_pulses_of_different_lengths_are_refused():
    """They take the same value at each point, so starting different
    lengths means the axis sweeps two different things under one name."""
    line = simple()
    line.tracks[1].pulses[0] = replace(line.tracks[1].pulses[0], sweep=DURATION)
    line.tracks[2].pulses[0] = replace(line.tracks[2].pulses[0], sweep=DURATION)
    line.sweep = SweepAxis(points=5, stop=US)
    with pytest.raises(SequenceError, match="different lengths"):
        line.to_sequence("mismatched", validate=False)


def test_a_pulse_cannot_sweep_two_things_at_once():
    line = simple()
    line.tracks[1].pulses[0] = replace(line.tracks[1].pulses[0], sweep=DURATION)
    line.tracks[2].pulses[0] = replace(line.tracks[2].pulses[0], sweep=FREQUENCY)
    with pytest.raises(SequenceError, match="one x-axis"):
        line.to_sequence("confused", validate=False)


def test_an_unknown_sweep_on_a_pulse_is_refused_by_name():
    with pytest.raises(SequenceError, match="use 'duration'"):
        Pulse(0.0, US, sweep="voltage")


def test_a_marked_pulse_with_no_length_says_to_drag_its_edges_apart():
    line = simple()
    line.tracks[1].pulses[0] = Pulse(US, US, True, "flat", sweep=DURATION)
    line.sweep = SweepAxis(points=5, stop=2 * US)
    with pytest.raises(SequenceError, match="no length to grow"):
        line.to_sequence("flat", validate=False)


def test_a_marked_pulse_cut_in_half_grows_only_its_second_part():
    """Another track's edge inside the pulse splits it. The edge has to
    stay where it was drawn, so the part after it is what grows — and the
    pulse as a whole still measures the sweep's value."""
    line = Timeline(
        tracks=[
            Track("mw", [Pulse(0.0, 100 * NS, Sin(), sweep=DURATION)]),
            Track("trigger", [Pulse(40 * NS, 60 * NS)]),  # cuts the pulse
            Track("gate", [Pulse(100 * NS, 3100 * NS)]),
            Track("laser", [Pulse(100 * NS, 3100 * NS)]),
        ],
        duration=4 * US,
        sweep=SweepAxis(points=5, stop=500 * NS),
    )
    block = line.to_sequence("split", validate=False).blocks[0]
    marked = [e for e in block.elements if e.increment]
    assert len(marked) == 1
    # First pass: the pulse still measures 100 ns in total.
    assert sum(e.duration for e in block.elements[:3]) == pytest.approx(100 * NS)


def test_the_first_value_is_the_length_that_was_drawn():
    """One source of truth. A start typed separately could disagree with
    the canvas, and then the drawing would be lying about point one."""
    line = swept(simple(), (0.0, 20 * NS), points=5, stop=100 * NS)
    assert line.sweep_values().values[0] == pytest.approx(20 * NS)


def test_a_stated_start_wins_over_the_drawing():
    line = swept(simple(), (0.0, 20 * NS), points=5, start=US, stop=5 * US)
    assert line.sweep_values().values[0] == pytest.approx(US)


# --- Log spacing ------------------------------------------------------------


def test_log_spacing_becomes_one_block_per_point():
    """A geometric series has no constant increment, so the per-repetition
    primitive cannot express it and there is nothing else it could be."""
    line = Timeline(
        tracks=[
            Track("laser", [Pulse(0.0, 3 * US), Pulse(5 * US, 8 * US)]),
            Track("gate", [
                Pulse(5 * US, 8 * US),
                Pulse(3 * US, 5 * US, True, "tau", sweep=DURATION, drives=False),
            ]),
        ],
        duration=9 * US,
        sweep=SweepAxis(points=6, stop=100 * US, spacing=LOG),
    )
    sequence = line.to_sequence("t1")
    assert len(sequence.blocks) == 6
    assert all(block.repetitions == 1 for block in sequence.blocks)
    assert sequence.points == 6
    assert sequence.sweep.values[0] == pytest.approx(2 * US)
    assert sequence.sweep.values[-1] == pytest.approx(100 * US)


def test_both_spacings_produce_the_same_kind_of_sweep():
    """So nothing downstream has to know which was used."""
    line = swept(simple(), (0.0, 20 * NS), points=5, stop=200 * NS)
    linear = line.to_sequence("a")
    line.sweep = SweepAxis(points=5, stop=200 * NS, spacing=LOG)
    logarithmic = line.to_sequence("b")

    assert linear.sweep.name == logarithmic.sweep.name == "tau"
    assert len(linear.sweep) == len(logarithmic.sweep) == 5
    assert linear.points == logarithmic.points


def test_an_unknown_spacing_lists_the_real_ones():
    with pytest.raises(SequenceError, match="linear"):
        SweepAxis(spacing="fibonacci")


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
def test_the_recovered_sweep_marks_every_pulse_tau_appears_on(name):
    """A Ramsey's tau appears once per alternating arm and a Hahn echo's
    twice; losing any of them would sweep half the sequence."""
    line = timeline_from_sequence(build(name, RigProfile(), points=6), CHANNELS)
    expected = {"rabi": 1, "ramsey": 2, "hahn_echo": 4}[name]
    assert len(line.swept) == expected
    assert line.sweep_quantity == DURATION
    assert line.sweep.spacing == LINEAR


@pytest.mark.parametrize("name", ["ramsey", "hahn_echo", "t1"])
def test_a_swept_gap_comes_back_as_a_timing_block(name):
    """Round-tripping a saved sequence has to give back a drawing whose
    every swept interval is an object you can click — otherwise "start
    from a Ramsey, then edit it" stops halfway."""
    line = timeline_from_sequence(build(name, RigProfile(), points=6), CHANNELS)
    gaps = [pulse for pulse in line.swept if not pulse.drives]
    assert gaps, f"{name}: its tau is a gap and came back as nothing"
    assert all(pulse.name == "tau" for pulse in gaps)
    # On the readout lane, where a delay belongs and where it counts as no
    # readout at all.
    assert all(
        pulse in line.track("gate").pulses for pulse in gaps
    )


def test_a_rabi_marks_the_drive_itself_rather_than_inventing_a_gap():
    """Its tau *is* a drawn pulse, so there is nothing to invent."""
    line = timeline_from_sequence(build("rabi", RigProfile(), points=6), CHANNELS)
    assert [pulse.drives for pulse in line.swept] == [True]
    assert line.swept[0] in line.track("mw").pulses


def test_a_log_sweep_comes_back_as_a_log_sweep():
    line = timeline_from_sequence(build("t1", RigProfile(), points=6), CHANNELS)
    assert line.sweep.spacing == LOG
    assert line.sweep.stop > line.sweep.start


def test_a_sequence_with_no_sweep_marks_nothing():
    line = simple()
    revived = timeline_from_sequence(line.to_sequence("flat", validate=False), CHANNELS)
    assert revived.swept == []
    assert revived.sweep_quantity == ""
    assert revived.sweep_values() is None


# --- Storage ----------------------------------------------------------------


def test_a_timeline_stores_as_plain_data():
    """It is a workflow parameter, so it has to survive JSON — no pulse
    objects, no pickle."""
    import json

    line = swept(simple(), (0.0, 20 * NS), points=8, stop=200 * NS)
    revived = Timeline.from_dict(json.loads(json.dumps(line.to_dict())))

    assert revived.duration == pytest.approx(line.duration)
    assert revived.channels == line.channels
    assert isinstance(revived.track("mw").pulses[0].value, Sin)
    assert revived.sweep.points == 8
    # Which pulse is swept is stored on the pulse, so it survives too.
    assert len(revived.swept) == 1
    assert revived.swept[0].sweep == DURATION


def test_a_timing_block_survives_storage_as_one():
    """A gap that came back driving its channel would turn a Ramsey into
    a sequence that gates the counter through its free evolution."""
    line = Timeline(
        tracks=[Track("gate", [Pulse(0.0, US, True, "tau", drives=False)])],
        duration=2 * US,
    )
    revived = Timeline.from_dict(line.to_dict())
    assert revived.track("gate").pulses[0].drives is False
    assert revived.track("gate").driving == []


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
    sequence = swept(
        simple(), (0.0, 20 * NS), points=10, stop=200 * NS
    ).to_sequence("hand")
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
# A duration and a frequency are the same editor, one field apart, and
# these pin the seam. A frequency sweep changes no element at all: the
# drawn pattern plays unchanged and the source moves between passes.
#
# Which pulse can carry which is not symmetric, and that asymmetry is the
# physics: a length is a property of any drawn interval, so a gate, a gap
# or a drive can all be swept in time; a *carrier* is a property of a
# drive alone, so only a microwave pulse can be swept in frequency.


def odmr(**axis) -> Timeline:
    """The simple drawing, with its microwave pulse swept in frequency."""
    line = simple()
    line.tracks[1].pulses[0] = replace(line.tracks[1].pulses[0], sweep=FREQUENCY)
    line.sweep = SweepAxis(**{"start": 2.82e9, "stop": 2.92e9, "points": 11, **axis})
    return line


def test_a_frequency_sweep_marks_a_pulse_but_stretches_nothing():
    line = odmr()
    assert line.sweep_quantity == FREQUENCY
    assert line.swept[0] is line.track("mw").pulses[0]


def test_a_frequency_axis_is_named_and_labelled_in_hertz():
    """Carried over from a duration sweep, the defaults would label a
    2.87 GHz axis "tau" in seconds."""
    values = odmr().sweep_values()
    assert values.name == "frequency"
    assert values.unit == "Hz"
    assert values.values[0] == pytest.approx(2.82e9)
    assert values.values[-1] == pytest.approx(2.92e9)


def test_a_duration_axis_is_named_and_labelled_in_seconds():
    values = swept(simple(), (0.0, 20 * NS), points=5, stop=100 * NS).sweep_values()
    assert values.name == "tau"
    assert values.unit == "s"
    assert not values.stepped


def test_a_name_someone_chose_survives_either_quantity():
    assert odmr(name="detuning").sweep_values().name == "detuning"


def test_the_sequence_carries_who_steps_it():
    """`parameter` is the whole mechanism: it is what tells the run to
    write each value to an instrument rather than expect the pulser to
    have played them."""
    sequence = odmr().to_sequence("odmr")
    assert sequence.sweep.parameter == "frequency"
    assert sequence.sweep.stepped
    assert len(sequence.sweep) == 11


def test_the_drawn_pattern_is_untouched_by_a_frequency_sweep():
    """One block, played once, with no increment anywhere — a duration
    sweep's whole mechanism is absent because there is nothing to vary."""
    sequence = odmr().to_sequence("odmr")
    assert len(sequence.blocks) == 1
    assert sequence.blocks[0].repetitions == 1
    assert all(e.increment == 0.0 for e in sequence.blocks[0].elements)
    assert sequence.readouts() == 1


def test_only_a_drive_can_carry_a_frequency_sweep():
    """A laser pulse and a counter gate are on/off lines with no carrier
    to move, so marking one would name a setting no source has."""
    line = simple()
    line.tracks[2].pulses[0] = replace(line.tracks[2].pulses[0], sweep=FREQUENCY)
    with pytest.raises(SequenceError, match="readout gate"):
        line.to_sequence("wrong", validate=False)

    line = simple()
    line.tracks[0].pulses[0] = replace(line.tracks[0].pulses[0], sweep=FREQUENCY)
    with pytest.raises(SequenceError, match="the laser"):
        line.to_sequence("wrong", validate=False)


def test_the_gate_can_still_be_swept_in_length():
    """The other half of that rule: a length is a property of any drawn
    interval, so a gate, a gap and a drive can all take one."""
    line = simple()
    line.tracks[2].pulses[0] = replace(line.tracks[2].pulses[0], sweep=DURATION)
    line.sweep = SweepAxis(points=5, stop=6 * US)
    sequence = line.to_sequence("longer_gate", validate=False)
    assert sequence.sweep.unit == "s"
    assert len([e for e in sequence.blocks[0].elements if e.increment]) == 1


def test_only_one_pulse_can_carry_the_frequency():
    line = odmr()
    line.tracks[1].pulses.append(
        Pulse(4 * US, 4.1 * US, Sin(), "second", sweep=FREQUENCY)
    )
    with pytest.raises(SequenceError, match="two frequencies at once"):
        line.to_sequence("two", validate=False)


def test_a_stepped_sweep_survives_a_round_trip_through_the_editor():
    """Load a saved pulsed ODMR back into the canvas and both the axis and
    the pulse carrying it come back — from the sweep's own values, since
    the elements hold no trace of it."""
    original = odmr(points=7).to_sequence("odmr")
    line = timeline_from_sequence(original, CHANNELS)

    assert line.sweep_quantity == FREQUENCY
    assert line.swept[0] in line.track("mw").pulses
    assert line.sweep.points == 7
    assert line.sweep.start == pytest.approx(2.82e9)
    assert line.sweep.stop == pytest.approx(2.92e9)
    assert line.to_sequence("odmr").sweep.values == original.sweep.values


def test_switching_quantity_keeps_every_drawn_pulse_where_it_was():
    """The editor's gesture: a Rabi drawing becomes a pulsed ODMR by
    changing one field on one pulse, and nothing on the canvas moves."""
    line = swept(simple(), (0.0, 20 * NS), points=10, stop=200 * NS)
    before = [(p.start, p.stop) for t in line.tracks for p in t.sorted()]
    line.tracks[1].pulses[0] = replace(line.tracks[1].pulses[0], sweep=FREQUENCY)
    line.sweep = SweepAxis(start=2.82e9, stop=2.92e9, points=10)
    assert line.sweep_quantity == FREQUENCY
    assert [(p.start, p.stop) for t in line.tracks for p in t.sorted()] == before


def test_duration_is_what_an_unmarked_drawing_has_none_of():
    line = simple()
    assert line.sweep_quantity == ""
    assert line.sweep_values() is None
    assert line.to_sequence("flat").sweep is None
