"""The Swabian Time Tagger driver, against a stand-in for the vendor API.

Until this driver existed, the only implementation of `GatedCounterMixin`
was the mock, so a pulsed rig could play a sequence on real hardware and
count nothing. Which makes the driver worth testing properly, and it
cannot be: the `TimeTagger` package ships with Swabian's installer, not
from PyPI, and there is no tagger on this machine.

So the vendor module is stood in for. That is not a test of the hardware —
nothing here proves the device behaves as documented — but it does test
every line this repo is responsible for: that the channels are checked
against what the device reports, that a bin width becomes a whole number
of picoseconds, that the record length is derived from the integers the
device will really use, and that the trace comes back with axes.

What the stand-in asserts about the vendor API is written down in
`_TimeDifferences.__init__` below: argument order and units. If Swabian
ever change those, these tests keep passing and the driver breaks — the
one failure mode a stand-in cannot cover, and the reason the module
docstring says it has not been run against hardware.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from labpilot.core.device.capabilities import GATED_COUNTER, capabilities_of
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.gated_counter_mixin import GatedCounterMixin
from labpilot.instruments.Swabian.time_tagger import PICOSECOND, TimeTaggerAdapter

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- A stand-in for Swabian's package ----------------------------------------


class _TimeDifferences:
    """The one vendor class this driver depends on.

    The signature is the contract being relied on:
    `(tagger, click, start, next, sync, binwidth_ps, n_bins, n_histograms)`,
    with the bin width an integer number of picoseconds.
    """

    def __init__(self, tagger, click, start, next_, sync, binwidth, n_bins, n_histograms):
        assert isinstance(binwidth, int), "binwidth must be whole picoseconds"
        self.args = (click, start, next_, sync, binwidth, n_bins, n_histograms)
        self.binwidth = binwidth
        self.n_bins = n_bins
        self.n_histograms = n_histograms
        self.running = False
        self.sweeps = 0
        self.cleared = 0
        # One count in a different bin per histogram, so a transposed
        # reshape would be visible rather than merely wrong-shaped.
        self.data = np.arange(n_histograms * n_bins).reshape(n_histograms, n_bins)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def clear(self):
        self.cleared += 1

    def isRunning(self):  # noqa: N802 - the vendor's spelling
        return self.running

    def getCounts(self):  # noqa: N802
        return self.sweeps

    def getData(self):  # noqa: N802
        return self.data


class _Tagger:
    def __init__(self, serial="TT20-0001", channels=(1, 2, 3, 4, -1, -2, -3, -4)):
        self.serial = serial
        self.channels = channels
        self.levels: dict[int, float] = {}
        self.dead_time: dict[int, int] = {}
        self.freed = False

    def getSerial(self):  # noqa: N802
        return self.serial

    def getModel(self):  # noqa: N802
        return "Time Tagger 20"

    def getChannelList(self):  # noqa: N802
        return list(self.channels)

    def setTriggerLevel(self, channel, level):  # noqa: N802
        self.levels[channel] = level

    def setDeadtime(self, channel, ps):  # noqa: N802
        self.dead_time[channel] = ps


@pytest.fixture
def vendor(monkeypatch):
    """Swabian's `TimeTagger` module, as far as this driver uses it."""
    taggers: list[_Tagger] = []

    def create(serial=""):
        tagger = _Tagger(serial=serial or "TT20-0001")
        taggers.append(tagger)
        return tagger

    module = SimpleNamespace(
        createTimeTagger=create,
        freeTimeTagger=lambda tagger: setattr(tagger, "freed", True),
        TimeDifferences=_TimeDifferences,
        taggers=taggers,
    )
    monkeypatch.setitem(sys.modules, "TimeTagger", module)
    return module


async def counter(vendor, **kwargs) -> TimeTaggerAdapter:
    adapter = TimeTaggerAdapter(**kwargs)
    await adapter.connect()
    return adapter


# --- It is a gated counter ---------------------------------------------------


def test_it_declares_the_contract_the_pulsed_plan_looks_for():
    assert GATED_COUNTER in capabilities_of(TimeTaggerAdapter)
    assert issubclass(TimeTaggerAdapter, GatedCounterMixin)


def test_it_is_the_first_real_one():
    """Not a claim about this driver so much as about the repo: if a
    second non-mock gated counter is added, this test is where to say so."""
    real = [
        key for key, cls in adapter_registry.list().items()
        if GATED_COUNTER in capabilities_of(cls) and not key.startswith("mock")
    ]
    assert "swabian_time_tagger" in real


def test_it_describes_itself_without_the_vendor_package():
    """The package ships with Swabian's installer, so most machines will
    never have it — and the catalogue still has to list this."""
    schema = TimeTaggerAdapter.describe()
    assert schema is not None
    assert "gated_counter" in schema.capabilities
    assert any(e.adapter_key == "swabian_time_tagger" for e in INSTRUMENT_CATALOG)


def test_connecting_without_it_says_where_it_comes_from():
    """`pip install TimeTagger` is not the answer, so the message must not
    imply it is."""
    adapter = TimeTaggerAdapter()
    if "TimeTagger" in sys.modules:  # pragma: no cover - not on this machine
        pytest.skip("the vendor package is installed here")
    with pytest.raises(ImportError, match="driver installation"):
        adapter._import()


# --- Wiring ------------------------------------------------------------------


async def test_the_trigger_level_reaches_both_input_channels(vendor):
    await counter(vendor, click_channel=1, gate_channel=2, trigger_level=0.8)
    tagger = vendor.taggers[0]
    assert tagger.levels == {1: 0.8, 2: 0.8}


async def test_a_channel_the_device_does_not_have_is_refused_by_name(vendor):
    """A wrong channel number otherwise shows up as a measurement that
    counts nothing, which is a much worse afternoon."""
    with pytest.raises(ValueError, match="click_channel=9"):
        await counter(vendor, click_channel=9)


async def test_a_falling_edge_channel_is_a_negative_number_not_an_error(vendor):
    """The vendor's own convention: `-3` is channel 3's falling edge."""
    adapter = await counter(vendor, click_channel=1, gate_channel=-3)
    assert adapter._read_sync()["gate_channel"] == -3


async def test_a_dead_time_is_only_applied_when_asked_for(vendor):
    await counter(vendor, dead_time_ps=0)
    assert vendor.taggers[0].dead_time == {}

    await counter(vendor, dead_time_ps=25_000)
    assert vendor.taggers[1].dead_time == {1: 25_000}


async def test_rewiring_drops_the_histogram_counted_against_the_old_wiring(vendor):
    """Carrying it forward would mix two measurements into one array."""
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 100e-9, 4)
    assert adapter._measurement is not None

    await adapter.write({"click_channel": 3})
    assert adapter._measurement is None
    with pytest.raises(RuntimeError, match="configure_gates"):
        await adapter.start_counting()


# --- configure_gates ---------------------------------------------------------


async def test_the_measurement_is_built_the_way_the_contract_needs(vendor):
    """`start` and `next` are the same channel because one gate edge ends
    the previous readout and begins this one."""
    adapter = await counter(vendor, click_channel=1, gate_channel=2, sync_channel=3)
    await adapter.configure_gates(bin_width_s=1e-9, record_length_s=3e-6, gates=50)

    click, start, next_, sync, binwidth, bins, histograms = adapter._measurement.args
    assert (click, start, next_, sync) == (1, 2, 2, 3)
    assert binwidth == 1000  # picoseconds
    assert (bins, histograms) == (3000, 50)


async def test_no_sync_channel_passes_zero_rather_than_a_channel(vendor):
    adapter = await counter(vendor, sync_channel=0)
    await adapter.configure_gates(1e-9, 100e-9, 2)
    assert adapter._measurement.args[3] == 0


async def test_a_bin_width_becomes_a_whole_number_of_picoseconds(vendor):
    """1.4 ns is legal and becomes 1400 ps exactly. A request that lands
    off the grid is rounded onto it — silently, when the difference is
    smaller than the device's own 1 ps resolution, because reporting a
    0.4 ps "adjustment" is noise rather than information."""
    adapter = await counter(vendor)

    exact = await adapter.configure_gates(1.4e-9, 140e-9, 4)
    assert adapter._measurement.binwidth == 1400
    assert exact.exact

    rounded = await adapter.configure_gates(1.0004e-9, 100e-9, 4)
    assert adapter._measurement.binwidth == 1000
    assert rounded.bin_width_s == pytest.approx(1e-9)


async def test_the_record_length_comes_back_derived_from_the_integers_used(vendor):
    """So the caller's `bins` and the device's cannot disagree — the
    failure `GateConfig` exists to prevent."""
    adapter = await counter(vendor)
    config = await adapter.configure_gates(
        bin_width_s=4e-9, record_length_s=3.003e-6, gates=10
    )
    assert config.bin_width_s == 4e-9
    assert config.bins == round(config.record_length_s / config.bin_width_s)
    assert config.record_length_s == pytest.approx(config.bins * 4e-9)
    assert adapter._measurement.n_bins == config.bins

    # And the difference is reported rather than absorbed: 3.003 µs is not
    # a whole number of 4 ns bins, so the run really covers 3.004 µs.
    assert not config.exact
    assert "whole number of 4 ns bins" in config.report()
    assert config.quantised["record_length_s"] == config.record_length_s


async def test_a_configuration_too_big_for_any_memory_is_refused(vendor):
    """A mistyped sweep count should not become a driver-level failure."""
    adapter = await counter(vendor)
    with pytest.raises(ValueError, match="histogram cells"):
        await adapter.configure_gates(PICOSECOND, 1e-3, 1_000_000)


async def test_configuring_does_not_start_counting(vendor):
    """The contract says so, and a run that starts before the pulser does
    accumulates a sweep of nothing."""
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 100e-9, 4)
    assert adapter._measurement.running is False
    assert (await adapter.counter_status())["running"] is False


# --- Counting ----------------------------------------------------------------


async def test_start_and_stop_drive_the_measurement(vendor):
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 100e-9, 4)

    await adapter.start_counting()
    assert (await adapter.counter_status())["running"] is True

    await adapter.stop_counting()
    assert (await adapter.counter_status())["running"] is False


async def test_stopping_when_nothing_runs_is_not_an_error(vendor):
    """It is what an aborted run calls, and an abort cannot know how far
    the run got."""
    adapter = await counter(vendor)
    await adapter.stop_counting()
    await adapter.configure_gates(1e-9, 100e-9, 2)
    await adapter.stop_counting()


async def test_sweeps_are_what_a_pulsed_run_counts_its_progress_in(vendor):
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 100e-9, 4)
    adapter._measurement.sweeps = 137

    assert (await adapter.counter_status())["sweeps"] == 137
    assert adapter._read_sync()["sweeps"] == 137


async def test_the_trace_is_gate_by_time_bin_with_real_axes(vendor):
    """A `Dataset` rather than a bare array plus an info dict, so the run
    lands in HDF5 with coordinates nobody had to re-derive."""
    adapter = await counter(vendor)
    config = await adapter.configure_gates(bin_width_s=2e-9, record_length_s=40e-9, gates=6)
    trace = await adapter.get_trace()

    counts = trace.primary()
    assert counts.values.shape == (6, 20) == config.shape
    readout, time = counts.axes
    assert readout.name == "readout"
    assert time.name == "time"
    assert time.unit == "s"
    assert time.values[1] == pytest.approx(2e-9)
    assert np.array_equal(counts.values, adapter._measurement.data)


async def test_the_trace_can_be_read_while_counting(vendor):
    """Which is what lets a pulsed run stream a converging picture instead
    of waiting for the end."""
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 20e-9, 3)
    await adapter.start_counting()

    assert (await adapter.get_trace()).primary().values.shape == (3, 20)
    assert adapter._measurement.running is True


async def test_reading_a_trace_before_configuring_says_what_is_missing(vendor):
    adapter = await counter(vendor)
    with pytest.raises(RuntimeError, match="no gates configured"):
        await adapter.get_trace()


async def test_clearing_throws_the_accumulation_away(vendor):
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 20e-9, 3)
    await adapter.clear()
    assert adapter._measurement.cleared == 1


async def test_disconnecting_stops_the_measurement_and_frees_the_device(vendor):
    """A tagger left claimed is a tagger the next process cannot open."""
    adapter = await counter(vendor)
    await adapter.configure_gates(1e-9, 20e-9, 3)
    await adapter.start_counting()

    await adapter.disconnect()
    assert vendor.taggers[0].freed is True
    assert adapter._measurement is None


async def test_the_reading_says_which_unit_produced_it(vendor):
    adapter = await counter(vendor, serial_number="TT20-0042")
    reading = (await adapter.read()).as_dict()
    assert reading["serial_number"] == "TT20-0042"
    assert reading["model"] == "Time Tagger 20"
