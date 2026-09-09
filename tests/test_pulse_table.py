"""The block editor's model — dynamic columns and cell editing.

This is the part of Qudi's PulseEditor worth taking whole: the columns are
not fixed. They come from the channels in play, and an analog channel
contributes a shape column plus one column per that shape's parameters, so
the table grows a Frequency column the moment a `Sin` appears in it.

Kept Qt-free and tested here because the column rule and the
cell-to-channel mapping are the fiddly parts, and `tests/` cannot import
the Qt stack.
"""

from __future__ import annotations

import pytest

from labpilot.core.pulse import SequenceError, Sin
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.table import (
    ANALOG,
    DIGITAL,
    INCREMENT,
    LENGTH,
    SHAPE,
    blank_element,
    cell,
    columns,
    sequence_from_table,
    set_cell,
    table_from_sequence,
)

CHANNELS = ("laser", "mw", "gate")


def ramsey_rows() -> list[dict]:
    return table_from_sequence(build("ramsey", RigProfile(), points=5))[0]["elements"]


def by_key(cols) -> dict:
    return {column.key: column for column in cols}


# --- Columns come from what is in the table -------------------------------


def test_a_digital_channel_is_one_column():
    cols = by_key(columns([blank_element(CHANNELS)], CHANNELS))
    assert cols["laser"].kind == DIGITAL
    assert cols["gate"].kind == DIGITAL


def test_an_analog_channel_grows_a_shape_column_and_its_parameters():
    """The dynamic-column behaviour: a Sin on the microwave channel gives
    the table Amplitude, Frequency and Phase columns it did not have."""
    cols = by_key(columns(ramsey_rows(), CHANNELS))

    assert cols["mw.shape"].kind == SHAPE
    assert [key for key in cols if key.startswith("mw.")] == [
        "mw.shape", "mw.amplitude", "mw.frequency", "mw.phase",
    ]
    assert cols["mw.frequency"].unit == "Hz"
    assert cols["mw.phase"].unit == "deg"


def test_changing_the_shape_changes_the_columns():
    """What forces a rebuild rather than an in-place cell update — a Chirp
    declares four parameters where a Sin declares three, and two of them
    are different."""
    rows = ramsey_rows()
    shape_column = by_key(columns(rows, CHANNELS))["mw.shape"]
    rows[0] = set_cell(rows[0], shape_column, "Chirp")

    keys = [key for key in by_key(columns(rows, CHANNELS)) if key.startswith("mw.")]
    assert "mw.start_frequency" in keys
    assert "mw.stop_frequency" in keys


def test_mixed_shapes_on_one_channel_produce_the_union():
    """Legal, and the reason a Gauss row and a Sin row do not have to
    agree: each cell that does not apply is blank rather than defaulted."""
    rows = ramsey_rows()
    shape_column = by_key(columns(rows, CHANNELS))["mw.shape"]
    rows[0] = set_cell(rows[0], shape_column, "Gauss")

    cols = by_key(columns(rows, CHANNELS))
    assert "mw.sigma_fraction" in cols  # Gauss only
    assert "mw.phase" in cols  # both

    # The Sin row has no sigma_fraction, so that cell does not apply.
    sin_row = next(
        r for r in rows
        if isinstance(r["channels"].get("mw"), dict)
        and r["channels"]["mw"].get("shape") == "Sin"
    )
    assert cell(sin_row, cols["mw.sigma_fraction"]) is None
    assert cell(rows[0], cols["mw.sigma_fraction"]) is not None


def test_a_declared_channel_gets_a_column_before_anything_uses_it():
    """So a new sequence starts with somewhere to put the laser."""
    cols = by_key(columns([], ("laser", "mw", "gate")))
    assert {"laser", "mw", "gate"} <= set(cols)


def test_column_order_is_stable_and_readable():
    """Not dict insertion order: laser, microwave and gate read in that
    order on every bench, and an edit must not reshuffle the table."""
    cols = [c.key for c in columns([], ("gate", "mw", "laser", "aux"))]
    assert cols[:3] == ["name", "length", "increment"]
    assert cols[3:] == ["laser", "mw", "gate", "aux"]


def test_the_columns_come_from_the_rig_not_from_a_pulser():
    """A renamed channel is a renamed column. Qudi takes its columns from
    the connected pulser's activation_config, which an offline editor has
    no access to and which would tie a saved sequence to one rig."""
    cols = by_key(columns([], ("green", "microwave", "apd_gate")))
    assert set(cols) >= {"green", "microwave", "apd_gate"}
    assert "laser" not in cols


# --- Reading and writing cells --------------------------------------------


def test_reading_a_row_gives_every_cell_it_has():
    rows = ramsey_rows()
    cols = columns(rows, CHANNELS)
    values = {c.key: cell(rows[0], c) for c in cols}

    assert values["name"] == "pi/2"
    assert values["length"] == pytest.approx(50e-9)
    assert values["laser"] is False
    assert values["mw.shape"] == "Sin"
    assert values["mw.frequency"] == pytest.approx(2.87e9)


def test_editing_a_cell_never_mutates_the_row_in_place():
    """Rows are handed around between the table, the preview and the
    stored parameter; an in-place edit would change all three at once."""
    rows = ramsey_rows()
    length = by_key(columns(rows, CHANNELS))["length"]
    edited = set_cell(rows[0], length, 80e-9)

    assert edited["duration"] == pytest.approx(80e-9)
    assert rows[0]["duration"] == pytest.approx(50e-9)


def test_toggling_a_digital_channel():
    rows = [blank_element(CHANNELS)]
    laser = by_key(columns(rows, CHANNELS))["laser"]
    assert cell(set_cell(rows[0], laser, True), laser) is True


def test_an_increment_may_be_negative():
    """A sweep can shorten an element as well as lengthen it."""
    rows = [blank_element(CHANNELS)]
    increment = by_key(columns(rows, CHANNELS))["increment"]
    assert set_cell(rows[0], increment, -10e-9)["increment"] == pytest.approx(-10e-9)


def test_a_negative_duration_is_clamped_rather_than_saved():
    """The model refuses one at construction, so the table must not be
    able to type its way into an unbuildable row."""
    rows = [blank_element(CHANNELS)]
    length = by_key(columns(rows, CHANNELS))["length"]
    assert set_cell(rows[0], length, -1e-9)["duration"] == 0.0


def test_choosing_a_shape_brings_that_shape_s_defaults():
    # A blank row's mw is low, so `columns` gives it a checkbox — the
    # shape column is what the UI offers to turn it analog.
    from labpilot.core.pulse.table import Column

    rows = [blank_element(CHANNELS)]
    shape = Column("mw.shape", "mw shape", SHAPE, channel="mw")
    edited = set_cell(rows[0], shape, "Sin")
    assert edited["channels"]["mw"] == {
        "shape": "Sin", "amplitude": 0.0, "frequency": 2.87e9, "phase": 0.0,
    }


def test_switching_shape_does_not_carry_the_old_parameters_across():
    """A Gauss that inherited a Chirp's start_frequency would be a silent
    wrong answer — a shape's parameters belong to the shape."""
    rows = ramsey_rows()
    shape = by_key(columns(rows, CHANNELS))["mw.shape"]
    chirped = set_cell(rows[0], shape, "Chirp")
    gaussed = set_cell(chirped, shape, "Gauss")

    assert "start_frequency" not in gaussed["channels"]["mw"]
    assert gaussed["channels"]["mw"]["shape"] == "Gauss"


def test_turning_a_shape_off_makes_the_channel_digital_and_low():
    rows = ramsey_rows()
    shape = by_key(columns(rows, CHANNELS))["mw.shape"]
    assert set_cell(rows[0], shape, "off")["channels"]["mw"] is False


def test_an_unknown_shape_lists_the_real_ones():
    rows = ramsey_rows()
    shape = by_key(columns(rows, CHANNELS))["mw.shape"]
    with pytest.raises(SequenceError, match="Sin"):
        set_cell(rows[0], shape, "Squircle")


def test_editing_one_analog_parameter_keeps_the_others():
    rows = ramsey_rows()
    frequency = by_key(columns(rows, CHANNELS))["mw.frequency"]
    edited = set_cell(rows[0], frequency, 2.8e9)

    assert edited["channels"]["mw"]["frequency"] == pytest.approx(2.8e9)
    assert edited["channels"]["mw"]["phase"] == rows[0]["channels"]["mw"]["phase"]


def test_a_blank_row_shows_every_channel_as_off_rather_than_absent():
    """An element that names no channel is legal in the model and
    unreadable in a table."""
    assert blank_element(CHANNELS)["channels"] == {
        "laser": False, "mw": False, "gate": False
    }


# --- The table form is the file form --------------------------------------


@pytest.mark.parametrize("name", ["rabi", "ramsey", "hahn_echo", "t1"])
def test_a_generated_sequence_round_trips_through_the_table(name):
    """What makes "generate a Rabi, then hand-edit it" one gesture: the
    generator's output is already in the table's own form, so nothing is
    converted and nothing is lost."""
    original = build(name, RigProfile(), points=6)
    revived = sequence_from_table(
        table_from_sequence(original),
        original.name,
        sweep=original.to_dict()["sweep"],
        alternating=original.alternating,
        gate_channel=original.gate_channel,
    )
    assert revived.points == original.points
    assert revived.readouts() == original.readouts()
    assert revived.duration == pytest.approx(original.duration)
    assert revived.channels == original.channels


def test_a_hand_edited_table_becomes_a_playable_sequence():
    rows = [
        {"name": "mw", "duration": 20e-9, "increment": 20e-9,
         "channels": {"mw": True, "laser": False}},
        {"name": "readout", "duration": 3e-6, "increment": 0.0,
         "channels": {"laser": True, "gate": True}},
        {"name": "wait", "duration": 1e-6, "increment": 0.0,
         "channels": {"laser": False}},
    ]
    sequence = sequence_from_table(
        [{"name": "rabi", "repetitions": 10, "elements": rows}], "hand_rabi"
    )
    assert sequence.readouts() == 10
    assert sequence.duration > 0


def test_analog_shapes_survive_the_table_as_shapes():
    rows = table_from_sequence(build("ramsey", RigProfile(), points=4))
    sequence = sequence_from_table(rows, "edited", alternating=True)
    drive = sequence.blocks[0].elements[0].channels["mw"]
    assert isinstance(drive, Sin)


def test_a_table_that_cannot_play_is_refused_at_save_time():
    rows = [{"name": "mw", "duration": 20e-9, "increment": 0.0,
             "channels": {"mw": True, "laser": False}}]
    with pytest.raises(SequenceError, match="no readout"):
        sequence_from_table([{"name": "b", "repetitions": 1, "elements": rows}], "broken")


def test_a_half_built_table_can_still_be_rendered():
    """Mid-edit a block has no readout yet, and refusing to draw it would
    make the editor unusable."""
    rows = [{"name": "mw", "duration": 20e-9, "increment": 0.0,
             "channels": {"mw": True}}]
    sequence = sequence_from_table(
        [{"name": "b", "repetitions": 1, "elements": rows}], "wip", validate=False
    )
    assert len(sequence.blocks[0].elements) == 1


def test_an_empty_table_says_so():
    with pytest.raises(SequenceError, match="no blocks"):
        sequence_from_table([], "empty")


def test_blocks_are_named_when_the_table_does_not_name_them():
    sequence = sequence_from_table(
        [{"repetitions": 1, "elements": [
            {"duration": 1e-6, "channels": {"laser": True, "gate": True}},
        ]}],
        "unnamed",
    )
    assert sequence.blocks[0].name == "block_0"


def test_the_column_kinds_tell_the_widget_what_to_build():
    """The table needs a checkbox, a spin box and a combobox in the right
    places, and it should not be inferring that from a name."""
    kinds = {c.key: c.kind for c in columns(ramsey_rows(), CHANNELS)}
    assert kinds["length"] == LENGTH
    assert kinds["increment"] == INCREMENT
    assert kinds["laser"] == DIGITAL
    assert kinds["mw.shape"] == SHAPE
    assert kinds["mw.amplitude"] == ANALOG
