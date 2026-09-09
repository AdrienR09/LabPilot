"""Saved sequences as files.

The authoring/execution split turns on this: the editor's whole output is
one of these files, and the measurement workflow's whole input is a name
that resolves to one. So what is pinned here is that a sequence survives
the round trip intact, that an unplayable one never becomes a file, and
that one bad file does not make the library unopenable.
"""

from __future__ import annotations

import json

import pytest

from labpilot.core.pulse import (
    PulseBlock,
    PulseElement,
    PulseSequence,
    SequenceError,
    delete_sequence,
    linear_sweep,
    list_sequences,
    load_sequence,
    save_sequence,
)
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.store import slug


@pytest.fixture
def sequences(tmp_path):
    return tmp_path / "sequences"


def rabi(name: str = "rabi") -> PulseSequence:
    block = PulseBlock(
        "rabi",
        (
            PulseElement(20e-9, {"mw": True, "laser": False}, increment=20e-9, name="mw"),
            PulseElement(3e-6, {"laser": True, "gate": True}, name="readout"),
            PulseElement(1e-6, {"laser": False}, name="wait"),
        ),
        repetitions=10,
    )
    return PulseSequence(
        name, (block,), sweep=linear_sweep("tau", 20e-9, 20e-9, 10),
        description="A short one",
    )


# --- Round trip ------------------------------------------------------------


def test_a_saved_sequence_comes_back_identical(sequences):
    save_sequence(rabi(), sequences)
    revived = load_sequence("rabi", sequences)
    assert revived.to_dict() == rabi().to_dict()


def test_the_file_is_json_a_person_can_read_and_diff(sequences):
    path = save_sequence(rabi(), sequences)
    assert path.name == "rabi.json"
    text = path.read_text()
    assert json.loads(text)["name"] == "rabi"
    assert "\n  " in text  # indented, so a diff is line-by-line


def test_saving_creates_the_directory(sequences):
    assert not sequences.exists()
    save_sequence(rabi(), sequences)
    assert sequences.is_dir()


def test_saving_again_overwrites_rather_than_accumulating(sequences):
    save_sequence(rabi(), sequences)
    save_sequence(rabi().evolve(description="edited"), sequences)
    assert len(list(sequences.glob("*.json"))) == 1
    assert load_sequence("rabi", sequences).description == "edited"


@pytest.mark.parametrize("name", ["rabi", "ramsey", "hahn_echo", "t1"])
def test_every_generated_sequence_survives_a_save_and_load(name, sequences):
    original = build(name, RigProfile())
    save_sequence(original, sequences)
    revived = load_sequence(name, sequences)
    revived.validate()
    assert revived.points == original.points
    assert revived.readouts() == original.readouts()
    assert revived.duration == pytest.approx(original.duration)


# --- Names -----------------------------------------------------------------


def test_a_display_name_becomes_a_filename_but_stays_the_display_name(sequences):
    """"Hahn echo, sample B" is a physicist's name, not a filename."""
    save_sequence(rabi("Hahn echo, sample B"), sequences)
    assert (sequences / "hahn_echo_sample_b.json").exists()
    assert load_sequence("Hahn echo, sample B", sequences).name == "Hahn echo, sample B"


def test_a_name_can_never_escape_the_sequence_directory():
    assert "/" not in slug("../../etc/passwd")
    assert slug("../../etc/passwd") == "etc_passwd"


def test_a_name_with_nothing_usable_is_refused():
    with pytest.raises(SequenceError, match="filename"):
        slug("///")


def test_loading_by_slug_or_by_display_name_both_work(sequences):
    save_sequence(rabi("Hahn echo"), sequences)
    assert load_sequence("hahn_echo", sequences).name == "Hahn echo"
    assert load_sequence("Hahn Echo", sequences).name == "Hahn echo"


# --- Refusals --------------------------------------------------------------


def test_an_unplayable_sequence_never_becomes_a_file(sequences):
    """Otherwise someone loads it a month later and blames the hardware."""
    block = PulseBlock("b", (PulseElement(1e-6, {"laser": False}),))
    with pytest.raises(SequenceError, match="no readout"):
        save_sequence(PulseSequence("broken", (block,)), sequences)
    assert not sequences.exists() or not list(sequences.glob("*.json"))


def test_loading_something_that_is_not_there_lists_what_is(sequences):
    save_sequence(rabi(), sequences)
    with pytest.raises(SequenceError, match="rabi"):
        load_sequence("ramsey", sequences)


def test_deleting_something_that_is_not_there_says_so(sequences):
    with pytest.raises(SequenceError, match="ramsey"):
        delete_sequence("ramsey", sequences)


# --- The library view ------------------------------------------------------


def test_listing_summarises_without_the_caller_parsing_blocks(sequences):
    save_sequence(rabi(), sequences)
    entry = list_sequences(sequences)[0]
    assert entry.name == "rabi"
    assert entry.slug == "rabi"
    assert entry.points == 10
    assert entry.readouts == 10
    assert entry.channels == ("gate", "laser", "mw")
    assert entry.description == "A short one"
    assert entry.valid


def test_an_empty_or_missing_library_is_empty_not_an_error(sequences):
    assert list_sequences(sequences) == []
    sequences.mkdir(parents=True)
    assert list_sequences(sequences) == []


def test_listing_is_sorted_by_name(sequences):
    for name in ("zeeman", "alpha", "rabi"):
        save_sequence(rabi(name), sequences)
    assert [e.name for e in list_sequences(sequences)] == ["alpha", "rabi", "zeeman"]


def test_a_broken_file_is_listed_and_marked_rather_than_hidden(sequences):
    """A typo must not make a file vanish and send the user to the shell
    to find out where it went."""
    save_sequence(rabi(), sequences)
    (sequences / "mangled.json").write_text("{ not json")
    entries = {entry.slug: entry for entry in list_sequences(sequences)}

    assert set(entries) == {"rabi", "mangled"}
    assert entries["rabi"].valid
    assert not entries["mangled"].valid
    assert entries["mangled"].problem


def test_a_file_that_parses_but_cannot_play_says_why(sequences):
    """A sequence may predate a rule; loading it must still work so it can
    be opened and fixed."""
    data = rabi().to_dict()
    data["sweep"]["values"] = [1e-9, 2e-9]  # now disagrees with 10 repetitions
    (sequences / "stale.json").parent.mkdir(parents=True, exist_ok=True)
    (sequences / "stale.json").write_text(json.dumps(data))

    entry = next(e for e in list_sequences(sequences) if e.slug == "stale")
    assert not entry.valid
    assert "disagree" in entry.problem
    load_sequence("stale", sequences)  # still openable, so it can be repaired


def test_deleting_removes_it_from_the_library(sequences):
    save_sequence(rabi(), sequences)
    delete_sequence("rabi", sequences)
    assert list_sequences(sequences) == []


def test_the_default_directory_is_the_user_state_directory(tmp_path, monkeypatch):
    """Not the installed package — that was the mistake workflow scripts
    made, and it breaks outright on a non-editable install."""
    monkeypatch.setenv("LABPILOT_HOME", str(tmp_path))
    save_sequence(rabi())
    assert (tmp_path / "sequences" / "rabi.json").exists()
    assert load_sequence("rabi").name == "rabi"
