"""The NI R-Series FPGA adapter: bitfiles, instructions and counting.

Driven against a fake `nifpga` session rather than a parallel mock
adapter, the same choice `test_ni_card.py` makes for `FakeNIDAQ`: the
code that has never met hardware is the code worth exercising, and a
second implementation that behaves itself proves nothing about the first.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path  # noqa: TC003  (a fixture annotation)
from typing import ClassVar

import pytest

from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.sequence import ChannelMap
from labpilot.instruments.NI.bitfiles import (
    BitfileEntry,
    BitfileError,
    Gateware,
    find_bitfile,
    find_model,
    load_bitfiles,
    load_models,
    normalise_number,
    read_bitfile,
)
from labpilot.instruments.NI.fpga import (
    MAX_TICKS,
    NIRSeriesAdapter,
    compile_instructions,
)

TICK = 1e-8  # 100 MHz


# --- A bitfile, as a file on disk -------------------------------------------


def _lvbitx(*registers: str, fifos: tuple[str, ...] = ("Instructions",)) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<Bitfile>\n'
        "  <BitfileName>pulser8</BitfileName>\n"
        "  <SignatureRegister>ABCD1234</SignatureRegister>\n  <Registers>\n"
        + "".join(
            f"    <Register><Name>{name}</Name><Hidden>false</Hidden></Register>\n"
            for name in registers
        )
        + "    <Register><Name>ViSignature</Name><Hidden>true</Hidden></Register>\n"
        "  </Registers>\n  <DMAChannelAllocationList>\n"
        + "".join(f'    <Channel name="{name}"/>\n' for name in fifos)
        + "  </DMAChannelAllocationList>\n</Bitfile>\n"
    )


#: An image that both plays a sequence and counts its readouts — the
#: R-Series case, since one card doing both is the reason to use one.
LVBITX = _lvbitx(
    "Run", "Loop", "Instruction Count",
    "Bin Ticks", "Gates", "Bins", "Sweeps", "Count",
    fifos=("Instructions", "Counts"),
)

#: One that only plays.
LVBITX_PULSER_ONLY = _lvbitx("Run", "Loop", "Instruction Count")


@pytest.fixture
def bitfile(tmp_path: Path) -> Path:
    path = tmp_path / "pulser8.lvbitx"
    path.write_text(LVBITX)
    return path


@pytest.fixture
def pulser_only(tmp_path: Path) -> Path:
    path = tmp_path / "pulser_only.lvbitx"
    path.write_text(LVBITX_PULSER_ONLY)
    return path


def test_a_bitfile_describes_itself_with_no_card_present(bitfile):
    """The whole reason the offline half works: a .lvbitx is XML, and its
    register and FIFO names are in it."""
    info = read_bitfile(bitfile)
    assert info.parsed
    assert info.signature == "ABCD1234"
    assert "Run" in info.registers
    assert "Instructions" in info.fifos


def test_hidden_registers_are_not_part_of_the_interface(bitfile):
    """`nifpga` does not key them either."""
    assert "ViSignature" not in read_bitfile(bitfile).registers


def test_an_unreadable_bitfile_degrades_rather_than_raising(tmp_path):
    """NI has changed the .lvbitx schema between LabVIEW versions, and an
    image this cannot parse is still one the driver may well load — so a
    failed parse costs the offline checks and nothing else."""
    path = tmp_path / "odd.lvbitx"
    path.write_text("<Bitfile><Something/></Bitfile>")
    info = read_bitfile(path)

    assert not info.parsed
    assert "Register" in info.note
    # Nothing known means nothing refused; the session checks instead.
    assert info.has("Run", "Instructions")
    assert info.missing("Run") == ()


def test_a_missing_bitfile_says_both_ways_out(tmp_path):
    with pytest.raises(BitfileError) as error:
        read_bitfile(tmp_path / "absent.lvbitx")
    assert "bitfile" in str(error.value)
    assert "ni_rseries.toml" in str(error.value)


# --- The card table ---------------------------------------------------------


def test_a_model_is_found_however_it_is_spelled():
    """Every R-Series number is four digits and an R, so the digits are
    the key and neither the bus prefix nor the suffix can miss a card."""
    assert normalise_number("PXIe-7856R") == normalise_number("7856") == "7856"
    assert find_model("PCIe-7852R").number == "7852"


def test_the_table_states_what_it_is_sure_of_and_no_more():
    """An absent field is 'unknown, do not validate' — the same rule the
    DAQmx model table follows."""
    card = find_model("7852")
    assert card.base_clock == 40e6
    assert card.ai == 8 and card.ao == 8
    # The 785x DIO count varies by connector configuration, so it is left
    # out rather than guessed.
    assert find_model("7856").dio == 0


def test_generic_is_the_escape_hatch_for_an_unlisted_card():
    assert find_model("generic").stated is False


def test_an_unknown_model_names_both_ways_out():
    with pytest.raises(BitfileError) as error:
        find_model("9999")
    assert "generic" in str(error.value)
    assert "ni_rseries.toml" in str(error.value)


# --- The library ------------------------------------------------------------


def _library() -> dict[str, BitfileEntry]:
    return {
        "small": BitfileEntry(
            name="small", path="/tmp/small.lvbitx", tick_rate=1 / TICK,
            channels=("DIO0", "DIO1"),
        ),
        "eight": BitfileEntry(
            name="eight", path="/tmp/eight.lvbitx", tick_rate=1 / TICK,
            channels=tuple(f"DIO{i}" for i in range(8)), counter=True,
        ),
        "wide": BitfileEntry(
            name="wide", path="/tmp/wide.lvbitx", tick_rate=1 / TICK,
            channels=tuple(f"DIO{i}" for i in range(32)), counter=True,
        ),
    }


def test_the_narrowest_image_that_fits_is_chosen():
    """A five-channel sequence should not take the 32-channel image when
    an eight-channel one would do."""
    assert find_bitfile(5, library=_library()).name == "eight"
    assert find_bitfile(2, library=_library()).name == "small"
    assert find_bitfile(20, library=_library()).name == "wide"


def test_a_counter_is_asked_for_rather_than_hoped_for():
    assert find_bitfile(2, counter=True, library=_library()).name == "eight"


def test_an_empty_library_says_why_it_is_empty():
    """The shipped state, and not an omission: a bitfile is compiled from
    a LabVIEW project and cannot be shipped for anyone."""
    with pytest.raises(BitfileError) as error:
        find_bitfile(4, library={})
    message = str(error.value)
    assert "fresh install" in message
    assert "ni_rseries.toml" in message
    assert "`bitfile` setting" in message


def test_the_packaged_library_is_empty_and_the_card_table_is_not():
    assert load_bitfiles() == {}
    assert len(load_models()) > 5


# --- Compiling to instructions ----------------------------------------------


def test_an_element_becomes_one_instruction_word():
    """Ticks in the low 32 bits, the channel mask in the high 32."""
    sequence = build("rabi", RigProfile(analog_mw=False), points=2)
    intervals = list(_expand(sequence))
    words = compile_instructions(
        intervals, ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"}),
        ("DIO0", "DIO1", "DIO2"), TICK,
    )
    assert len(words) == len(intervals)
    for word, interval in zip(words, intervals, strict=True):
        assert word & 0xFFFFFFFF == max(round(interval.duration / TICK), 1)


def test_position_in_the_channel_list_is_the_bit_set():
    """The one thing here that can silently drive the wrong wires."""
    intervals = [_interval(1e-7, {"mw": True})]
    words = compile_instructions(
        intervals, ChannelMap({"mw": "DIO3"}),
        ("DIO0", "DIO1", "DIO2", "DIO3"), TICK,
    )
    assert words[0] >> 32 == 0b1000


def test_a_channel_the_image_does_not_drive_sets_no_bit():
    words = compile_instructions(
        [_interval(1e-7, {"mw": True})], ChannelMap({"mw": "DIO9"}),
        ("DIO0", "DIO1"), TICK,
    )
    assert words[0] >> 32 == 0


def test_a_long_element_is_split_rather_than_wrapped():
    """A tick count has 32 bits. Wrapping one would be a sequence that
    runs and measures something else entirely."""
    long = (MAX_TICKS + 1000) * TICK
    words = compile_instructions(
        [_interval(long, {"laser": True})], ChannelMap({"laser": "DIO0"}),
        ("DIO0",), TICK,
    )
    assert len(words) == 2
    assert sum(word & 0xFFFFFFFF for word in words) == MAX_TICKS + 1000
    assert all(word >> 32 == 1 for word in words)


def test_an_element_shorter_than_a_tick_still_plays():
    """Rounded up to one tick, never to zero: a zero-length instruction
    is one the engine skips."""
    words = compile_instructions(
        [_interval(TICK / 100, {"laser": True})], ChannelMap({"laser": "DIO0"}),
        ("DIO0",), TICK,
    )
    assert words[0] & 0xFFFFFFFF == 1


# --- Against a session ------------------------------------------------------


class FakeRegister:
    def __init__(self, value=0):
        self.value = value
        self.writes: list = []

    def write(self, value):
        self.value = value
        self.writes.append(value)

    def read(self):
        return self.value


class FakeFifo:
    def __init__(self, data=None):
        self.started = False
        self.written: list[int] = []
        self.data = list(data or [])

    def start(self):
        self.started = True

    def write(self, values, timeout_ms=None):
        self.written.extend(values)

    def read(self, count, timeout_ms=None):
        taken, self.data = self.data[:count], self.data[count:]
        return types.SimpleNamespace(data=taken, elements_remaining=len(self.data))


class FakeSession:
    """`nifpga.Session`, as far as this adapter uses it."""

    opened: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, bitfile, resource, counter=True, counts=None):
        FakeSession.opened.append((str(bitfile), str(resource)))
        self.bitfile = str(bitfile)
        self.resource = str(resource)
        self.closed = False
        gateware = Gateware()
        self.registers = {
            name: FakeRegister() for name in gateware.pulser_names
            if name != gateware.instructions
        }
        self.fifos = {gateware.instructions: FakeFifo()}
        if counter:
            self.registers.update({
                name: FakeRegister() for name in gateware.counter_names
                if name != gateware.counts
            })
            self.fifos[gateware.counts] = FakeFifo(counts)

    def close(self):
        self.closed = True


@pytest.fixture
def nifpga(monkeypatch):
    """A stand-in `nifpga` module, so the real adapter's driver path runs."""
    FakeSession.opened = []
    sessions: list[FakeSession] = []

    def make(bitfile, resource, **kw):
        session = FakeSession(bitfile, resource, **_options)
        sessions.append(session)
        return session

    _options: dict = {"counter": True, "counts": None}
    module = types.ModuleType("nifpga")
    module.Session = make
    monkeypatch.setitem(sys.modules, "nifpga", module)
    return types.SimpleNamespace(sessions=sessions, options=_options)


def _entry(path, counter=True, memory=0):
    return BitfileEntry(
        name="eight", path=str(path), tick_rate=1 / TICK, memory=memory,
        channels=("DIO0", "DIO1", "DIO2", "DIO3"), counter=counter,
    )


LINES = "DIO0, DIO1, DIO2, DIO3"


async def _connected(bitfile, nifpga, **kw):
    kw.setdefault("channels", LINES)
    kw.setdefault("tick_rate", 1 / TICK)
    adapter = NIRSeriesAdapter(bitfile=str(bitfile), model="7852", **kw)
    await adapter.connect()
    return adapter


async def test_a_pinned_bitfile_is_what_gets_loaded(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    assert FakeSession.opened == [(str(bitfile), "RIO0")]
    assert (await adapter.read())["loaded"] == str(bitfile)
    await adapter.disconnect()


async def test_uploading_streams_instructions_and_says_how_many(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    sequence = build("rabi", RigProfile(analog_mw=False), points=4)
    report = await adapter.upload_sequence(
        sequence, ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"})
    )

    session = nifpga.sessions[0]
    written = session.fifos["Instructions"].written
    assert report.instructions == len(written)
    assert session.registers["Instruction Count"].value == len(written)
    assert report.points == 4
    assert report.readouts == sequence.readouts()
    await adapter.disconnect()


async def test_playing_loops_so_a_measurement_can_average(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    await adapter.upload_sequence(
        build("rabi", RigProfile(analog_mw=False), points=2),
        ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"}),
    )
    await adapter.pulser_on()

    session = nifpga.sessions[0]
    assert session.registers["Loop"].value is True
    assert session.registers["Run"].value is True

    await adapter.pulser_off()
    assert session.registers["Run"].value is False
    await adapter.disconnect()


async def test_pulser_off_is_safe_before_anything_played(bitfile, nifpga):
    """An abort calls it and cannot know how far the run got."""
    adapter = await _connected(bitfile, nifpga)
    await adapter.pulser_off()
    await adapter.disconnect()


async def test_playing_without_a_sequence_says_so(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    with pytest.raises(RuntimeError, match="upload_sequence"):
        await adapter.pulser_on()
    await adapter.disconnect()


async def test_an_analog_shape_is_refused_with_the_way_out(bitfile, nifpga):
    """This engine plays a channel mask per element; it is not an AWG."""
    adapter = await _connected(bitfile, nifpga)
    with pytest.raises(Exception, match="analog_mw=False"):
        await adapter.upload_sequence(
            build("rabi", RigProfile(analog_mw=True), points=2),
            ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"}),
        )
    await adapter.disconnect()


async def test_a_sequence_too_deep_for_the_memory_is_refused(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    adapter._entry = _entry(bitfile, memory=4)
    with pytest.raises(BitfileError, match="holds 4"):
        await adapter.upload_sequence(
            build("rabi", RigProfile(analog_mw=False), points=20),
            ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"}),
        )
    await adapter.disconnect()


# --- Choosing the image from the sequence -----------------------------------


async def test_with_no_bitfile_pinned_the_sequence_chooses_one(
    bitfile, nifpga, monkeypatch
):
    """The half that lets a measurement drive the card without being told
    which image to use."""
    entry = _entry(bitfile)
    monkeypatch.setattr(
        "labpilot.instruments.NI.fpga.find_bitfile",
        lambda channels, **kw: entry,
    )
    adapter = NIRSeriesAdapter(model="7852")
    await adapter.connect()
    # Nothing is loaded until there is a sequence to load it for.
    assert nifpga.sessions == []

    await adapter.upload_sequence(
        build("rabi", RigProfile(analog_mw=False), points=3),
        ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"}),
    )
    assert FakeSession.opened == [(str(bitfile), "RIO0")]
    assert (await adapter.read())["loaded"] == str(bitfile)
    await adapter.disconnect()


async def test_the_chosen_image_is_asked_for_the_channels_the_sequence_uses(
    bitfile, nifpga, monkeypatch
):
    asked: list[int] = []

    def choose(channels, **kw):
        asked.append(channels)
        return _entry(bitfile)

    monkeypatch.setattr("labpilot.instruments.NI.fpga.find_bitfile", choose)
    adapter = NIRSeriesAdapter(model="7852")
    await adapter.connect()
    await adapter.upload_sequence(
        build("rabi", RigProfile(analog_mw=False), points=3),
        ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"}),
    )
    assert asked == [3]
    await adapter.disconnect()


# --- Capabilities follow the gateware ---------------------------------------


def test_a_card_with_nothing_loaded_claims_no_counter():
    """Advertising one that may not exist is worse than binding a second
    instrument that was not needed."""
    assert "gated_counter" not in NIRSeriesAdapter(model="7852").schema.capabilities


async def test_an_image_that_counts_says_so_on_its_schema(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    assert "gated_counter" in adapter.schema.capabilities
    assert "pulser" in adapter.schema.capabilities
    await adapter.disconnect()


async def test_an_image_that_only_pulses_does_not(pulser_only, nifpga):
    """Read off the image itself: it lists its registers, so whether it
    counts is a question the file answers."""
    nifpga.options["counter"] = False
    adapter = await _connected(pulser_only, nifpga)
    assert "gated_counter" not in adapter.schema.capabilities
    with pytest.raises(RuntimeError, match="no counting registers"):
        await adapter.configure_gates(1e-9, 3e-6, 4)
    await adapter.disconnect()


# --- The counting half ------------------------------------------------------


async def test_gates_are_quantised_to_the_engines_tick(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    config = await adapter.configure_gates(3e-9, 1e-6, 8)

    # 100 MHz ticks: 3 ns is not expressible, 10 ns is.
    assert config.bin_width_s == pytest.approx(TICK)
    assert config.gates == 8
    assert not config.exact
    session = nifpga.sessions[0]
    assert session.registers["Bin Ticks"].value == 1
    assert session.registers["Gates"].value == 8
    assert session.registers["Bins"].value == config.bins
    await adapter.disconnect()


async def test_the_trace_comes_back_shaped_with_real_axes(bitfile, nifpga):
    nifpga.options["counts"] = list(range(2 * 5))
    adapter = await _connected(bitfile, nifpga)
    config = await adapter.configure_gates(TICK, 5 * TICK, 2)
    await adapter.start_counting()
    trace = await adapter.get_trace()

    counts = trace.arrays["counts"]
    assert counts.values.shape == config.shape == (2, 5)
    assert [axis.name for axis in counts.axes] == ["gate", "time"]
    assert counts.axes[1].unit == "s"
    assert counts.axes[1].values[1] == pytest.approx(TICK)
    await adapter.disconnect()


async def test_a_short_read_is_padded_so_a_live_plot_still_draws(bitfile, nifpga):
    """A trace is asked for while the run is still accumulating."""
    nifpga.options["counts"] = [7, 7, 7]
    adapter = await _connected(bitfile, nifpga)
    await adapter.configure_gates(TICK, 5 * TICK, 2)
    await adapter.start_counting()
    counts = (await adapter.get_trace()).arrays["counts"].values

    assert counts.shape == (2, 5)
    assert list(counts[0][:3]) == [7, 7, 7]
    assert counts.sum() == 21
    await adapter.disconnect()


async def test_counter_status_reports_the_sweeps_register(bitfile, nifpga):
    adapter = await _connected(bitfile, nifpga)
    await adapter.configure_gates(TICK, 5 * TICK, 2)
    nifpga.sessions[0].registers["Sweeps"].value = 42
    await adapter.start_counting()

    status = await adapter.counter_status()
    assert status == {"running": True, "sweeps": 42}
    await adapter.stop_counting()
    assert (await adapter.counter_status())["running"] is False
    await adapter.disconnect()


# --- Reconciling what was declared against what is there ---------------------


async def test_a_session_missing_a_register_is_reported_in_every_reading(
    bitfile, nifpga, monkeypatch
):
    """The safety net for parsing .lvbitx ourselves: NI has changed that
    schema, and this is where a parse that quietly found nothing shows
    up."""
    adapter = await _connected(bitfile, nifpga)
    del nifpga.sessions[0].registers["Loop"]
    adapter._reconcile()

    warning = (await adapter.read())["warning"]
    assert "Loop" in warning
    await adapter.disconnect()


def test_an_image_without_the_pulser_registers_is_refused(tmp_path):
    """An image with no instruction FIFO is not a pulse sequencer, and
    saying so beats a session that opens and plays nothing."""
    path = tmp_path / "counter_only.lvbitx"
    path.write_text(
        '<?xml version="1.0"?><Bitfile><Registers>'
        "<Register><Name>Count</Name></Register>"
        "</Registers></Bitfile>"
    )
    adapter = NIRSeriesAdapter(bitfile=str(path), model="7852")
    with pytest.raises(BitfileError) as error:
        adapter._use(None, str(path))
    assert "Instructions" in str(error.value)
    assert "gateware" in str(error.value)


def test_the_gateware_names_are_overridable(tmp_path):
    """A lab with a working sequencer VI renames four strings rather than
    editing Python."""
    gateware = Gateware.from_dict({"run": "Start", "instructions": "Pulse FIFO"})
    assert gateware.run == "Start"
    assert gateware.instructions == "Pulse FIFO"
    # Anything left out keeps its default.
    assert gateware.loop == "Loop"
    # And anything unrecognised is ignored rather than raising.
    assert Gateware.from_dict({"nonsense": "x"}).run == "Run"


# --- Helpers ----------------------------------------------------------------


def _expand(sequence):
    from labpilot.core.pulse.sampling import expand

    return expand(sequence)


def _interval(duration, channels):
    return types.SimpleNamespace(
        duration=duration, channels=channels, name="", start=0.0
    )


# --- The point of all of it: a pulsed measurement drives this card ----------


async def test_one_card_fills_both_roles_of_a_pulsed_measurement(bitfile, nifpga):
    """An image that plays *and* counts is the reason to use an R-Series
    board at all, and `PulsedMeasurementPlan` binds a pulser and a counter
    as separate roles — so the same adapter is registered for both.

    Nothing special makes that legal: the card is `kind="generic"`, which
    fits any role, and it advertises both capabilities because its bitfile
    has both. What a device can do follows from how it is configured.
    """
    from labpilot.core.run import PulsedMeasurementPlan
    from labpilot.core.session import Session

    nifpga.options["counts"] = list(range(4096))
    adapter = await _connected(bitfile, nifpga)

    session = Session()
    session.register(adapter, "pulser")
    session.register(adapter, "counter")

    sequence = build("rabi", RigProfile(analog_mw=False), points=6)
    measurement = PulsedMeasurementPlan(
        sequence,
        channels={"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"},
        bin_width=TICK, sweeps=4, checkpoints=2,
    )

    # Everything the run needs is knowable before the card is touched.
    descriptor = await measurement.describe(session)
    assert descriptor.axes[1].name == "tau"
    assert len(descriptor.axes[1].values) == 6

    await adapter.disconnect()


async def test_the_sequences_own_readout_count_configures_the_counter(
    bitfile, nifpga
):
    """The gate count comes from the sequence, not from a hand-typed
    number — the counter is armed for exactly the readouts the program
    will produce."""
    adapter = await _connected(bitfile, nifpga)
    sequence = build("rabi", RigProfile(analog_mw=False), points=7)
    await adapter.upload_sequence(
        sequence, ChannelMap({"laser": "DIO0", "mw": "DIO1", "gate": "DIO2"})
    )
    config = await adapter.configure_gates(TICK, 10 * TICK, sequence.readouts())

    assert config.gates == sequence.readouts() == 7
    assert nifpga.sessions[0].registers["Gates"].value == 7
    await adapter.disconnect()


# --- What the configuration says, before anything is loaded -----------------


def test_a_stated_tick_rate_is_reported_before_a_bitfile_loads():
    """It is the number every duration gets quantised to, so a rate
    someone typed that reads back as the card's base clock is a setting
    that looks ignored."""
    card = NIRSeriesAdapter(model="7852", channels="DIO0, DIO1", tick_rate=1 / TICK)
    assert card.resolution == pytest.approx(TICK)
    assert card.pulser_constraints().digital_channels == ("DIO0", "DIO1")


def test_with_nothing_stated_the_cards_base_clock_is_the_answer():
    assert NIRSeriesAdapter(model="7852").resolution == pytest.approx(1 / 40e6)


def test_the_channel_list_takes_the_string_a_form_field_holds():
    """The same reason instruments/NI/channels.py takes one: the whole
    wiring has to fit in a connection form."""
    card = NIRSeriesAdapter(channels=" DIO0 , DIO1,, DIO2 ")
    assert card.channels == ("DIO0", "DIO1", "DIO2")
    assert NIRSeriesAdapter(channels=("DIO0", "DIO1")).channels == ("DIO0", "DIO1")


def test_it_configures_with_no_driver_and_no_card(monkeypatch):
    """The offline half: nothing here imports nifpga."""
    monkeypatch.delitem(sys.modules, "nifpga", raising=False)
    card = NIRSeriesAdapter(model="7856", channels="DIO0", tick_rate=1 / TICK)

    assert card.schema.kind == "generic"
    assert "pulser" in card.schema.capabilities
    assert len(card.schema.parameters[1].choices) > 5
    assert "nifpga" not in sys.modules
