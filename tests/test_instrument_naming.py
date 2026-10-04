"""The name you type is the name you address the instrument by.

The Devices dialog requires a name and sends it as `name`. The id — the
string `lp[...]`, a workflow binding and every REST path use — was
invented from a counter, so calling a detector `my_APD` produced
`mock_basic_detector_0d_3` and the name was stored, displayed and ignored
by everything that mattered. These tests pin the derivation and the two
things it has to get right: collisions, and names that are not already
valid ids.
"""

from __future__ import annotations

import pytest

from labpilot.core.api.dashboard import DashboardManager
from labpilot.core.config.instrument_sets import InstrumentSetPersistence
from labpilot.core.lab import Lab, slug, unique_id
from labpilot.core.lab.naming import MAX_ID_LENGTH
from labpilot.core.session import Session

DETECTOR = "mock_basic_detector_0d"


# --- The derivation on its own --------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("my_APD", "my_APD"),
        ("Sample stage", "Sample_stage"),
        ("APD #1", "APD_1"),
        ("  spaced  out  ", "spaced_out"),
        ("Keithley 2400 (gate)", "Keithley_2400_gate"),
        ("532 laser", "532_laser"),
        ("---", ""),
        ("", ""),
    ],
)
def test_a_name_becomes_an_id(name, expected):
    assert slug(name) == expected


def test_case_is_preserved():
    """`my_APD` means `my_APD`. Lower-casing would be tidier and wrong:
    it is also what makes `lp.my_APD` possible rather than `lp.my_apd`."""
    assert slug("my_APD") == "my_APD"


def test_an_id_is_never_longer_than_a_url_wants():
    assert len(slug("x" * 500)) == MAX_ID_LENGTH


def test_the_first_of_a_name_is_unnumbered():
    """`APD`, not `APD_1` — the numbering should appear only once there is
    something to distinguish it from."""
    assert unique_id("APD", set()) == "APD"


def test_a_repeated_name_is_suffixed_from_two():
    taken = {"APD"}
    assert unique_id("APD", taken) == "APD_2"
    assert unique_id("APD", taken | {"APD_2"}) == "APD_3"


def test_a_name_with_nothing_usable_falls_back():
    assert unique_id("???", set(), fallback=DETECTOR) == DETECTOR


def test_a_suffix_cannot_push_an_id_over_the_limit():
    long = "y" * MAX_ID_LENGTH
    assert len(unique_id(long, {long})) <= MAX_ID_LENGTH


# --- Through the manager, which is what the UI calls -----------------------


@pytest.fixture
def manager(tmp_path):
    manager = DashboardManager()
    manager.lab = Lab(store=InstrumentSetPersistence(tmp_path), session=Session())
    manager.lab.active_config = "test"
    return manager


def _create(manager, name=None, instrument_id=None, adapter_key=DETECTOR):
    return manager.create_instrument(adapter_key, instrument_id, name, {})


def test_the_id_comes_from_the_name_the_user_typed(manager):
    status = _create(manager, name="my_APD")
    assert status.id == "my_APD"
    assert status.name == "my_APD"
    assert "my_APD" in manager.lab


def test_two_instruments_with_the_same_name_both_exist(manager):
    first = _create(manager, name="APD")
    second = _create(manager, name="APD")
    assert (first.id, second.id) == ("APD", "APD_2")
    # The *name* is a label and may legitimately repeat; only the id is
    # forced to differ.
    assert first.name == second.name == "APD"


def test_an_unnamed_instrument_falls_back_to_its_adapter_key(manager):
    assert _create(manager).id == DETECTOR


def test_an_explicit_id_still_wins(manager):
    """Scripts and saved configs set the id directly; the name must not
    override that."""
    status = _create(manager, name="my_APD", instrument_id="apd0")
    assert status.id == "apd0"
    assert status.name == "my_APD"


def test_an_explicit_id_that_already_exists_is_an_error(manager):
    _create(manager, instrument_id="apd0")
    with pytest.raises(ValueError, match="already exists"):
        _create(manager, instrument_id="apd0")


async def test_a_delete_does_not_make_the_next_create_collide(manager):
    """The counter this replaced was `len(lab) + 1`: with three
    instruments, deleting one made the next create ask for an id a
    survivor already held, and fail with "already exists"."""
    ids = [_create(manager, name="APD").id for _ in range(3)]
    assert ids == ["APD", "APD_2", "APD_3"]

    await manager.lab.remove("APD_2")
    assert _create(manager, name="APD").id == "APD_2"
    assert _create(manager, name="APD").id == "APD_4"
