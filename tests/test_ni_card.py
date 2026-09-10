"""One NI card adapter: the model table, the wiring, and what follows.

The thing worth pinning here is that **none of it needs a driver**. NI
ships no DAQmx for macOS, so if configuring a card required one, an NI rig
could not be laid out, validated or even looked at on most of the machines
people write workflows on. Every test below runs with no nidaqmx, no
pylablib and no card — which is the same claim the tests make about the
pulse sequence editor, for the same reason.

The second claim is that the table is not authoritative. It is checked for
internal consistency (a model that says it has four counters must generate
`ctr0..ctr3`), never for agreement with hardware — `reconcile()` and
`scripts/ni_probe.py` are what settle that, on a machine with the card.
"""

from __future__ import annotations

import asyncio
import re
import tomllib
from pathlib import Path

import pytest

from labpilot.core.device.capabilities import HARDWARE_SCAN
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.connections import CONNECTION_METHODS
from labpilot.instruments.mock.ni_card import MockNICard
from labpilot.instruments.NI.card import NICardAdapter
from labpilot.instruments.NI.channels import Channel, parse_channels, validate_channels
from labpilot.instruments.NI.models import (
    AI,
    AO,
    CTR,
    DIO,
    PFI,
    NICardModel,
    find_model,
    load_models,
    normalise_number,
)

pytestmark = pytest.mark.anyio

PACKAGED = Path("src/labpilot/instruments/NI/models.toml")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def wired(**kwargs) -> MockNICard:
    kwargs.setdefault("channels", "x=ao0, y=ao1, apd=ctr0/pfi8")
    return MockNICard(**kwargs)


# --- The model table ---------------------------------------------------------


def test_the_table_covers_the_families_a_lab_actually_has():
    """X Series for anything current, M Series for anything not, the
    low-cost USB boxes, and the counter-only cards a photon-counting rig
    is built on."""
    models = load_models()
    for number in ("6363", "6323", "6229", "6251", "6008", "6602", "6612"):
        assert number in models, number
    assert len(models) > 40


def test_a_model_is_found_by_any_of_its_product_names():
    """`PCIe-6363`, `USB-6363` and `6363` are one card on three buses, and
    DAQmx reports whichever one you have."""
    for spelling in ("PCIe-6363", "USB-6363", "pxie-6363", "6363", "NI 6363"):
        assert find_model(spelling).number == "6363"


def test_a_bus_the_table_does_not_list_is_still_accepted():
    """Being wrong about which buses NI shipped is far more likely than
    the card in front of someone not existing, so the bus is never a
    reason to refuse one."""
    assert "PCI" not in find_model("6363").buses
    assert find_model("PCI-6363").number == "6363"


def test_an_unknown_model_says_where_to_add_it():
    with pytest.raises(KeyError, match=re.escape("ni_models.toml")):
        find_model("PCIe-9999")


def test_counts_generate_the_terminals_daqmx_names():
    card = find_model("6363")
    assert card.terminals(AI)[:2] == ("ai0", "ai1")
    assert card.terminals(AI)[-1] == "ai31"
    assert card.terminals(AO) == ("ao0", "ao1", "ao2", "ao3")
    assert card.terminals(CTR) == ("ctr0", "ctr1", "ctr2", "ctr3")
    assert card.terminals(PFI)[-1] == "pfi15"


def test_digital_lines_follow_nis_own_port_layout():
    """Not a straight division into eights: a 48-line X or M Series card
    puts 32 of them on port 0, the hardware-timed one."""
    assert find_model("6363").dio_ports == (32, 8, 8)
    assert find_model("6361").dio_ports == (8, 8, 8)
    assert find_model("6363").terminals(DIO)[:2] == ("port0/line0", "port0/line1")
    assert len(find_model("6363").terminals(DIO)) == 48


def test_an_unstated_field_is_not_a_zero():
    """`pfi = 0` would reject every PFI terminal on a card whose count
    nobody entered; absent means unvalidated instead."""
    unstated = NICardModel(number="9999", counters=2)
    assert unstated.pfi is None
    assert unstated.knows(PFI) is False
    assert unstated.knows(CTR) is True


def test_software_timed_outputs_are_not_timed_outputs():
    """A USB-6008's analog outputs update when written and cannot follow a
    clock, which is the difference between a card that can scan and one
    that cannot."""
    assert find_model("6008").ao == 2
    assert find_model("6008").timed_output is False
    assert find_model("6363").timed_output is True


def test_every_entry_generates_the_terminals_it_claims():
    """The one invariant a hand-entered table can actually be held to."""
    for number, card in load_models().items():
        assert len(card.terminals(AI)) == card.ai, number
        assert len(card.terminals(AO)) == card.ao, number
        assert len(card.terminals(CTR)) == card.counters, number
        assert sum(card.dio_ports) == card.dio, number


def test_family_defaults_are_inherited_but_never_win():
    """Stating the timebase once per series is shorter and much harder to
    get inconsistently wrong — but an entry's own value must still win."""
    assert find_model("6363").timebase == 100e6  # from [family.X]
    assert find_model("6602").timebase == 80e6  # stated on the entry
    assert find_model("6289").ai_bits == 18  # overrides the family's 16


def test_a_user_file_adds_a_model_without_losing_the_packaged_ones(tmp_path):
    """The same override rule the block config uses, for the same reason:
    a replacement file silently loses every model a later release adds."""
    user = tmp_path / "ni_models.toml"
    user.write_text('[[card]]\nnumber = "6399"\nfamily = "X"\nai = 4\nao = 1\n')

    models = load_models(user=user, refresh=True)
    assert "6399" in models
    assert "6363" in models
    assert models["6399"].counters == 4  # the X family default still applies


def test_a_user_file_can_correct_one_field_of_a_packaged_model(tmp_path):
    user = tmp_path / "ni_models.toml"
    user.write_text('[[card]]\nnumber = "6363"\nai = 64\n')

    corrected = load_models(user=user, refresh=True)["6363"]
    assert corrected.ai == 64
    assert corrected.ao == 4  # everything else survives


def test_nothing_is_written_to_the_users_config(tmp_path):
    """The packaged table is complete on its own; a file that exists only
    to be overridden should not appear until someone means to use it."""
    load_models(user=tmp_path / "ni_models.toml", refresh=True)
    assert not (tmp_path / "ni_models.toml").exists()


def test_the_packaged_file_states_a_number_for_every_entry():
    with open(PACKAGED, "rb") as f:
        table = tomllib.load(f)
    numbers = [entry.get("number") for entry in table["card"]]
    assert all(numbers)
    assert len(numbers) == len(set(numbers)), "a model number appears twice"


# --- The wiring --------------------------------------------------------------


def test_a_one_line_spec_is_the_same_as_a_table_of_records():
    """The string form exists so a whole wiring fits in the connect
    form's single field; it must mean exactly what the long form means."""
    short = parse_channels("x=ao0, apd=ctr0/pfi8")
    long = parse_channels([
        {"name": "x", "kind": "ao", "terminal": "ao0"},
        {"name": "apd", "kind": "ci", "terminal": "ctr0", "source": "pfi8"},
    ])
    assert short == long


def test_the_kind_follows_from_the_terminal():
    channels = {c.name: c for c in parse_channels("pd=ai0, x=ao0, apd=ctr0/pfi8")}
    assert channels["pd"].kind == "ai"
    assert channels["x"].kind == "ao"
    assert channels["apd"].kind == "ci"
    assert channels["apd"].source == "pfi8"


def test_a_digital_line_must_say_which_way_it_points():
    """The one terminal whose direction cannot be inferred, and the one
    where guessing wrong means a shutter that silently never opens."""
    with pytest.raises(ValueError, match="never opens"):
        parse_channels("shutter=port0/line0")

    assert parse_channels("shutter=do:port0/line0")[0].kind == "do"
    assert parse_channels("flag=di:port0/line0")[0].kind == "di"


def test_terminal_spelling_is_canonicalised_like_daqmx_does():
    """DAQmx is case-insensitive and tolerates a leading device name, so
    two spellings of one terminal must not read as two terminals."""
    assert parse_channels("a=AI0")[0].terminal == "ai0"
    assert parse_channels("a=Dev1/ai0")[0].terminal == "ai0"
    assert parse_channels("c=CTR0/PFI8")[0].source == "pfi8"


def test_the_old_name_to_terminal_mapping_still_parses():
    """`{"x": "ao0"}` is what the adapter this replaces took, and a saved
    config written against it should keep working."""
    assert parse_channels({"x": "ao0", "y": "ao1"}) == parse_channels("x=ao0, y=ao1")


def test_a_terminal_the_card_lacks_is_refused_by_name():
    """With the terminals it *does* have in the message — the reader
    mistyped `ai32` on a 32-channel card and needs to be told it counts
    from zero, not handed a DAQmx status code when the run starts."""
    with pytest.raises(ValueError, match=r"ai0\.\.ai31"):
        validate_channels(parse_channels("pd=ai32"), find_model("6363"))


def test_a_counter_must_say_what_it_counts():
    with pytest.raises(ValueError, match="which terminal"):
        validate_channels(parse_channels("apd=ctr0"), find_model("6363"))


def test_a_card_without_analog_output_refuses_an_output_channel():
    with pytest.raises(ValueError, match="6602 has none"):
        validate_channels(parse_channels("x=ao0"), find_model("6602"))


def test_two_channels_cannot_share_a_name_or_a_terminal():
    with pytest.raises(ValueError, match="both named"):
        validate_channels(parse_channels("x=ao0, x=ao1"), find_model("6363"))
    with pytest.raises(ValueError, match="used by both"):
        validate_channels(parse_channels("x=ao0, y=ao0"), find_model("6363"))


def test_a_range_wider_than_the_card_is_refused():
    channel = Channel("x", "ao", "ao0", minimum=-50.0, maximum=50.0)
    with pytest.raises(ValueError, match=re.escape("±10")):
        validate_channels([channel], find_model("6363"))


def test_an_unstated_inventory_is_taken_on_trust():
    """A model whose PFI count nobody entered must not reject a PFI line;
    the alternative is a table entry that blocks a working rig."""
    model = NICardModel(number="9999", counters=2)
    assert validate_channels(parse_channels("apd=ctr0/pfi8"), model)


# --- What a configured card presents -----------------------------------------


def test_the_schema_uses_the_rigs_names_not_the_cards():
    """The indirection is the point: a workflow binds to `apd`, and moving
    the APD to another PFI line is one character in a config file."""
    schema = wired().schema
    assert "apd" in schema.readable
    assert "x" in schema.settable
    assert "ctr0" not in schema.readable


def test_a_counter_reads_in_counts_per_second_and_an_output_in_volts():
    schema = wired(channels="x=ao0, apd=ctr0/pfi8, pd=ai0").schema
    assert schema.units["apd"] == "counts/s"
    assert schema.units["x"] == "V"
    assert schema.units["pd"] == "V"


def test_hardware_scan_is_claimed_only_when_the_wiring_supports_it():
    """Three conditions, each of which really does prevent a scan: a
    position output, something to read back, and outputs that can follow a
    clock."""
    assert HARDWARE_SCAN in wired().schema.capabilities
    assert HARDWARE_SCAN not in wired(channels="apd=ctr0/pfi8").schema.capabilities
    assert HARDWARE_SCAN not in wired(channels="x=ao0").schema.capabilities
    assert HARDWARE_SCAN not in MockNICard(
        model="USB-6008", channels="x=ao0, pd=ai0"
    ).schema.capabilities


def test_a_counter_output_becomes_an_action_with_arguments():
    schema = wired(channels="clock=co:ctr1/pfi12").schema
    actions = {a.name: a for a in schema.actions}
    assert set(actions) == {"pulse_on", "pulse_off"}
    assert [p.name for p in actions["pulse_on"].params] == [
        "channel", "frequency", "duty"
    ]
    assert actions["pulse_on"].params[0].choices == ("clock",)


def test_the_real_adapter_describes_itself_with_no_driver_installed():
    """The claim the whole design rests on: NI ships no DAQmx for macOS,
    and this still has to be configurable there."""
    schema = NICardAdapter.describe()
    assert schema is not None
    assert "NI-DAQmx" in schema.tags


def test_connecting_without_the_driver_says_what_to_install():
    """The message has to name the packages *and* say that configuring a
    card needs none of them — otherwise it reads as "this feature is
    unavailable here", which is exactly wrong."""
    try:
        import pylablib.devices.NI  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("pylablib's NI backend is installed on this machine")

    with pytest.raises(ImportError, match="NI-DAQmx"):
        NICardAdapter(model="PCIe-6363", channels="x=ao0")._open()


def test_the_model_and_the_device_name_are_readable():
    """Which card this is, and what NI-MAX calls it, on every reading —
    so a saved run says which hardware produced it."""
    card = wired(model="USB-6323", device="Dev3")
    reading = card._read_sync()
    assert reading["model"] == "USB-6323"
    assert reading["device"] == "Dev3"


# --- The simulated card ------------------------------------------------------


async def test_the_mock_is_the_same_configuration_with_a_simulated_back_end():
    """Same model numbers, same terminal strings, same schema — the whole
    value of choosing `PCIe-6363` on a mock is that the configuration you
    arrive at is the one the real card will accept."""
    real = NICardAdapter(model="PCIe-6363", channels="x=ao0, apd=ctr0/pfi8")
    mock = MockNICard(model="PCIe-6363", channels="x=ao0, apd=ctr0/pfi8")
    assert real.schema.readable == mock.schema.readable
    assert real.schema.settable == mock.schema.settable
    assert real.schema.capabilities == mock.schema.capabilities


async def test_the_counter_reads_a_signal_that_depends_on_the_outputs():
    """Not wall-clock noise: an optimizer run against this converges on a
    real maximum, which is what the shared `_SimulatedSample` is for."""
    card = wired(sample="ni_card_test")
    await card.connect()

    await card.write({"x": 0.0, "y": 0.0})
    near = (await card.read()).as_dict()["apd"]
    await card.write({"x": 9.0, "y": 9.0})
    far = (await card.read()).as_dict()["apd"]

    assert near > far * 5


async def test_writing_to_a_terminal_that_is_not_wired_is_refused():
    card = wired()
    await card.connect()
    with pytest.raises(Exception, match="z"):
        await card.write({"z": 1.0})


async def test_a_scan_fills_its_frame_and_leaves_the_outputs_where_it_ended():
    card = wired(sample="ni_card_scan")
    await card.connect()
    await card.configure_scan(
        ["x", "y"], {"x": (-2.0, 2.0), "y": (-2.0, 2.0)}, {"x": 4, "y": 4}, 5000.0
    )
    await card.start_scan()

    for _ in range(200):
        frame = await card.get_scan_data()
        if frame["done"]:
            break
        await asyncio.sleep(0.005)

    assert frame["done"] is True
    assert frame["completed"] == frame["total"] == 16
    assert all(value is not None for value in frame["data"])


async def test_a_scan_needs_an_axis_the_card_actually_drives():
    card = wired()
    await card.connect()
    with pytest.raises(NotImplementedError, match="No analog output wired"):
        await card.configure_scan(["z"], {"z": (0.0, 1.0)}, {"z": 4}, 100.0)


# --- Registration ------------------------------------------------------------


def test_both_cards_are_registered_and_catalogued():
    for key in ("ni_card", "mock_ni_card"):
        assert key in adapter_registry.list()
        assert any(entry.adapter_key == key for entry in INSTRUMENT_CATALOG), key


def test_the_two_adapters_this_replaces_are_gone():
    """One physical card used to appear as two instruments, each opening
    its own DAQmx session against the same device."""
    assert "ni_daq" not in adapter_registry.list()
    assert "ni_daq_scanner" not in adapter_registry.list()
    assert not any(e.adapter_key.startswith("ni_daq") for e in INSTRUMENT_CATALOG)


def test_the_connect_form_asks_for_the_model_and_the_wiring():
    """An NI card is not reached by an address — DAQmx already knows it by
    name. What has to be said is which card it is and what is plugged in
    where."""
    fields = {f.name for f in CONNECTION_METHODS["ni_daqmx"].fields}
    assert fields == {"device", "model", "channels"}

    entry = next(e for e in INSTRUMENT_CATALOG if e.adapter_key == "ni_card")
    assert entry.connection_types == ["ni_daqmx"]


def test_the_connect_forms_default_wiring_is_a_valid_one():
    """It is the example everyone starts from, so it had better parse and
    validate against the model the form also defaults to."""
    fields = {f.name: f.default for f in CONNECTION_METHODS["ni_daqmx"].fields}
    model = find_model(str(fields["model"]))
    assert validate_channels(parse_channels(str(fields["channels"])), model)


def test_normalising_a_product_name_keeps_what_was_typed_when_it_has_no_number():
    """So the error message can quote what was actually asked for."""
    assert normalise_number("  PCIe-6363 ") == "6363"
    assert normalise_number("nonsense") == "nonsense"
