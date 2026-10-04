"""The PicoHarp 300 driver, and the T3 decoding it stands on.

Two kinds of test here, and the split matters.

`decode_t3` is a pure function over 32-bit words, so it can be tested
*exactly*: a synthetic record stream whose histogram is known in advance.
That is the part worth the most, because it is the part no amount of time
at the bench would catch — a sign error in the sync correction produces a
plausible histogram, not an error, and the physics would be blamed first.

Everything else goes through a stand-in for PicoQuant's `phlib`, because
the real one ships with their driver installation rather than from PyPI
and there is no PicoHarp on this machine. That is not a test of the
hardware. What the stand-in assumes about the library is written into
`_FakePHLib` — call names, argument order, units — and if PicoQuant ever
change those, these tests keep passing and the driver breaks. That is the
one failure mode a stand-in cannot cover and the reason the module
docstring says it has not been run against hardware.
"""

from __future__ import annotations

import ctypes

import numpy as np
import pytest

from labpilot.core.device.capabilities import GATED_COUNTER, capabilities_of
from labpilot.core.errors import DeviceError
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.gated_counter_mixin import (
    BIN_WIDTH,
    RECORD_LENGTH,
    GatedCounterMixin,
)
from labpilot.instruments.PicoQuant.picoharp300 import (
    BASE_RESOLUTION,
    MAX_BINS,
    MODE_T3,
    T3_OVERFLOW_CHANNEL,
    T3_WRAPAROUND,
    PicoHarp300Adapter,
    decode_t3,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- The record format ------------------------------------------------------


def photon(sync: int, dtime: int, channel: int = 0) -> int:
    """One T3 record: `[4 bits channel | 12 bits dtime | 16 bits sync]`."""
    return (channel << 28) | ((dtime & 0xFFF) << 16) | (sync & 0xFFFF)


def wrap() -> int:
    """A sync-counter overflow record — channel 15, nothing else read."""
    return T3_OVERFLOW_CHANNEL << 28


def test_one_photon_lands_in_its_own_cell():
    counts, _, highest, dropped = decode_t3(
        np.array([photon(sync=3, dtime=7)], dtype=np.uint32), gates=4, bins=16
    )
    assert counts[3, 7] == 1
    assert counts.sum() == 1
    assert (highest, dropped) == (3, 0)


def test_the_gate_is_the_sync_index_modulo_the_readout_count():
    """Which is what makes a sequence's readouts the histogram's first
    axis: sync 5 of a 4-readout sequence is readout 1 of the second pass."""
    counts, _, _, _ = decode_t3(
        np.array([photon(5, 2)], dtype=np.uint32), gates=4, bins=8
    )
    assert counts[1, 2] == 1


def test_dtime_is_already_a_bin_index():
    """Because the device's resolution is set to the requested bin width,
    so no division is needed — and none is done."""
    words = np.array([photon(0, bin_) for bin_ in range(8)], dtype=np.uint32)
    counts, _, _, _ = decode_t3(words, gates=1, bins=8)
    assert counts[0].tolist() == [1] * 8


def test_counts_accumulate_in_the_same_cell():
    words = np.array([photon(2, 5)] * 9, dtype=np.uint32)
    counts, _, _, _ = decode_t3(words, gates=4, bins=8)
    assert counts[2, 5] == 9


def test_an_overflow_record_is_not_a_photon():
    counts, base, highest, _ = decode_t3(
        np.array([wrap()], dtype=np.uint32), gates=2, bins=4
    )
    assert counts.sum() == 0
    assert base == T3_WRAPAROUND
    assert highest == -1, "no photon was seen, so there is no highest sync"


def test_a_photon_after_an_overflow_continues_past_the_wrap():
    """The whole reason the correction exists: sync 1 *after* a wrap is
    absolute sync 65537, which in a 4-readout sequence is readout 1 — not
    readout 1 of the first pass all over again."""
    words = np.array([wrap(), photon(1, 3)], dtype=np.uint32)
    counts, base, highest, _ = decode_t3(words, gates=4, bins=8)
    assert highest == T3_WRAPAROUND + 1
    assert counts[(T3_WRAPAROUND + 1) % 4, 3] == 1
    assert base == T3_WRAPAROUND


def test_a_photon_before_an_overflow_is_not_corrected():
    """A cumulative sum evaluated at a photon's own index must count only
    the wraps strictly before it. Getting this off by one shifts every
    gate by one readout, which looks exactly like a cabling delay."""
    words = np.array([photon(9, 1), wrap(), photon(9, 1)], dtype=np.uint32)
    counts, _, highest, _ = decode_t3(words, gates=5, bins=4)
    assert counts[9 % 5, 1] == 1, "the first photon was not corrected"
    assert counts[(T3_WRAPAROUND + 9) % 5, 1] == 1, "the second one was"
    assert highest == T3_WRAPAROUND + 9


def test_several_overflows_in_one_batch_each_count():
    words = np.array([wrap(), wrap(), photon(0, 0)], dtype=np.uint32)
    _, base, highest, _ = decode_t3(words, gates=1, bins=4)
    assert base == 2 * T3_WRAPAROUND
    assert highest == 2 * T3_WRAPAROUND


def test_the_sync_base_carries_between_batches():
    """Batches are whatever `PH_ReadFiFo` happened to return, so a wrap in
    one batch has to still apply in the next."""
    _, base, _, _ = decode_t3(np.array([wrap()], dtype=np.uint32), 1, 4)
    _, _, highest, _ = decode_t3(
        np.array([photon(2, 0)], dtype=np.uint32), 1, 4, sync_base=base
    )
    assert highest == T3_WRAPAROUND + 2


def test_a_photon_later_than_the_window_is_counted_not_folded_back():
    """Wrapping it would put late light in the first bin, which reads as
    signal. The window being shorter than the physics is a fact to
    report, not an error."""
    words = np.array([photon(0, 3), photon(0, 20)], dtype=np.uint32)
    counts, _, _, dropped = decode_t3(words, gates=1, bins=8)
    assert counts.sum() == 1
    assert counts[0, 0] == 0
    assert dropped == 1


def test_an_empty_batch_is_harmless():
    counts, base, highest, dropped = decode_t3(
        np.array([], dtype=np.uint32), gates=2, bins=4, sync_base=99
    )
    assert counts.sum() == 0
    assert (base, highest, dropped) == (99, -1, 0)


def test_a_whole_synthetic_sequence_histograms_as_designed():
    """The end-to-end shape of the thing: four readouts per pass, three
    passes, a known number of photons in known bins, plus a wrap in the
    middle to prove the correction survives real traffic."""
    gates, bins = 4, 16
    words: list[int] = []
    expected = np.zeros((gates, bins), dtype=int)
    for pass_ in range(3):
        for readout in range(gates):
            sync = pass_ * gates + readout
            for _ in range(readout + 1):          # readout 0 -> 1 photon, etc.
                words.append(photon(sync, dtime=2 * readout))
                expected[readout, 2 * readout] += 1

    counts, _, highest, dropped = decode_t3(
        np.asarray(words, dtype=np.uint32), gates, bins
    )
    assert counts.tolist() == expected.tolist()
    assert highest == 3 * gates - 1
    assert dropped == 0
    assert (highest + 1) // gates == 3, "three complete passes"


# --- A stand-in for PicoQuant's library ------------------------------------


class _FakePHLib:
    """The PHLib calls this driver makes, and the contract it relies on.

    Return 0 for success, negative for an error, exactly as the real
    library does; out-parameters arrive as ctypes references.
    """

    def __init__(self) -> None:
        self.opened: list[int] = []
        self.closed: list[int] = []
        self.mode: int | None = None
        self.calibrations = 0
        self.binning: int | None = None
        self.started: list[int] = []
        self.stopped = 0
        self.cfd: dict[int, tuple[int, int]] = {}
        self.sync_divider: int | None = None
        self.sync_offset: int | None = None
        self.offset: int | None = None
        self.serials = {0: "1041234"}
        self.records: list[int] = []
        self.ctc_done = 0
        self.flags = 0
        self.fail: set[str] = set()

    # -- lifecycle
    def PH_GetErrorString(self, buffer, code):  # noqa: N802
        buffer.value = b"a fake error"
        return 0

    def PH_OpenDevice(self, index, serial):  # noqa: N802
        if index not in self.serials:
            return -1
        serial.value = self.serials[index].encode()
        self.opened.append(index)
        return 0

    def PH_CloseDevice(self, index):  # noqa: N802
        self.closed.append(index)
        return 0

    def PH_Initialize(self, index, mode):  # noqa: N802
        if "init" in self.fail:
            return -2
        self.mode = mode
        return 0

    def PH_GetHardwareInfo(self, index, model, part, version):  # noqa: N802
        model.value, part.value, version.value = b"PicoHarp 300", b"930000", b"3.0"
        return 0

    def PH_GetBaseResolution(self, index, resolution, steps):  # noqa: N802
        resolution._obj.value = 4.0          # picoseconds, as the library reports
        steps._obj.value = 8
        return 0

    def PH_Calibrate(self, index):  # noqa: N802
        self.calibrations += 1
        return 0

    # -- inputs
    def PH_SetSyncDiv(self, index, div):  # noqa: N802
        self.sync_divider = div
        return 0

    def PH_SetInputCFD(self, index, channel, level, zero):  # noqa: N802
        self.cfd[channel] = (level, zero)
        return 0

    def PH_SetSyncOffset(self, index, offset):  # noqa: N802
        self.sync_offset = offset
        return 0

    def PH_SetOffset(self, index, offset):  # noqa: N802
        self.offset = offset
        return 0

    def PH_SetBinning(self, index, binning):  # noqa: N802
        if "binning" in self.fail:
            return -3
        self.binning = binning
        return 0

    # -- measurement
    def PH_StartMeas(self, index, tacq):  # noqa: N802
        self.started.append(tacq)
        return 0

    def PH_StopMeas(self, index):  # noqa: N802
        self.stopped += 1
        return 0

    def PH_CTCStatus(self, index, status):  # noqa: N802
        status._obj.value = self.ctc_done
        return 0

    def PH_ReadFiFo(self, index, buffer, count, actual):  # noqa: N802
        taken = self.records[:count]
        self.records = self.records[count:]
        for position, word in enumerate(taken):
            buffer[position] = word
        actual._obj.value = len(taken)
        return 0

    def PH_GetFlags(self, index, flags):  # noqa: N802
        flags._obj.value = self.flags
        return 0

    def PH_GetCountRate(self, index, channel, rate):  # noqa: N802
        rate._obj.value = 1000 if channel == 0 else 25000
        return 0

    def PH_GetWarnings(self, index, warnings):  # noqa: N802
        warnings._obj.value = 0
        return 0

    def PH_GetWarningsText(self, index, text, warnings):  # noqa: N802
        text.value = b""
        return 0


@pytest.fixture
def phlib(monkeypatch):
    fake = _FakePHLib()
    monkeypatch.setattr(PicoHarp300Adapter, "_load", lambda self: fake)
    return fake


async def _connected(phlib, **kwargs) -> PicoHarp300Adapter:
    adapter = PicoHarp300Adapter(**kwargs)
    await adapter.connect()
    return adapter


# --- Describing itself ------------------------------------------------------


def test_it_is_in_the_catalogue_and_the_registry():
    assert "picoharp_300" in adapter_registry.list()
    assert any(m.adapter_key == "picoharp_300" for m in INSTRUMENT_CATALOG)


def test_it_declares_the_gated_counter_capability():
    adapter = PicoHarp300Adapter()
    assert isinstance(adapter, GatedCounterMixin)
    assert GATED_COUNTER in capabilities_of(adapter)


def test_it_describes_itself_with_no_hardware_and_no_library():
    """Which is what makes it catalogued, tag-searchable and probeable on
    a machine that has never had a PicoHarp or PicoQuant's driver."""
    schema = PicoHarp300Adapter.describe()
    assert schema is not None
    assert schema.kind == "counter"
    assert GATED_COUNTER in schema.capabilities


def test_the_bin_width_is_a_ladder_not_a_granularity():
    """The device halves its base resolution in powers of two: 4, 8, 16 …
    512 ps and nothing between. A `step` would accept 12 ps."""
    constraint = next(
        c for c in PicoHarp300Adapter().counter_constraints().scalars
        if c.name == BIN_WIDTH
    )
    assert constraint.allowed == tuple(BASE_RESOLUTION * 2**n for n in range(8))


def test_a_missing_library_says_there_is_nothing_to_pip_install():
    with pytest.raises(ImportError, match="no package to pip-install"):
        PicoHarp300Adapter(library="definitely-not-a-real-library")._load()


# --- Connecting -------------------------------------------------------------


async def test_connecting_initialises_t3_mode_and_calibrates(phlib):
    adapter = await _connected(phlib)
    try:
        assert phlib.mode == MODE_T3
        assert phlib.calibrations == 1
    finally:
        await adapter.disconnect()


async def test_the_base_resolution_comes_from_the_device(phlib):
    """Reported in picoseconds, used in seconds — and the device's answer
    wins over the module constant, which is what `probe` then confirms."""
    adapter = await _connected(phlib)
    try:
        ladder = next(
            c for c in adapter.counter_constraints().scalars if c.name == BIN_WIDTH
        )
        assert ladder.allowed[0] == pytest.approx(4e-12)
    finally:
        await adapter.disconnect()


async def test_ch0_gets_the_sync_cfd_and_ch1_the_detector(phlib):
    """CH0 carries the sequence's gate line and CH1 the APD. Swapping them
    is a measurement that counts nothing, so the mapping is pinned here."""
    adapter = await _connected(
        phlib, sync_level_mv=120, sync_zero_cross_mv=5,
        input_level_mv=60, input_zero_cross_mv=11,
    )
    try:
        assert phlib.cfd[0] == (120, 5)
        assert phlib.cfd[1] == (60, 11)
    finally:
        await adapter.disconnect()


async def test_a_failed_initialisation_closes_the_device_again(phlib):
    """Otherwise the unit stays claimed and the next attempt cannot open
    it — which looks like a hardware fault."""
    phlib.fail.add("init")
    adapter = PicoHarp300Adapter()
    with pytest.raises(DeviceError, match="PH_Initialize failed"):
        await adapter.connect()
    assert phlib.closed == [0]


async def test_a_serial_number_is_hunted_across_the_indices(phlib):
    """A PC with two PicoHarps enumerates them in whatever order USB found
    them, so an index is not stable across a reboot and a measurement can
    silently run on the other instrument."""
    phlib.serials = {0: "1041111", 1: "1042222"}
    adapter = await _connected(phlib, serial_number="1042222")
    try:
        assert adapter._index == 1
        assert 0 in phlib.closed, "the wrong unit is released again"
    finally:
        await adapter.disconnect()


async def test_an_absent_serial_number_says_so(phlib):
    adapter = PicoHarp300Adapter(serial_number="9999999")
    with pytest.raises(DeviceError, match="No PicoHarp with serial"):
        await adapter.connect()


async def test_an_error_code_is_rendered_as_text(phlib):
    phlib.fail.add("init")
    with pytest.raises(DeviceError, match="a fake error"):
        await PicoHarp300Adapter().connect()


# --- Configuring ------------------------------------------------------------


async def test_a_bin_width_between_rungs_snaps_and_says_so(phlib):
    adapter = await _connected(phlib)
    try:
        config = await adapter.configure_gates(
            bin_width_s=12e-12, record_length_s=1e-9, gates=4
        )
        assert config.bin_width_s == pytest.approx(16e-12)
        assert not config.exact
        assert BIN_WIDTH in config.report()
    finally:
        await adapter.disconnect()


async def test_the_binning_step_is_the_power_of_two_the_width_implies(phlib):
    """Setting the device's resolution *to* the bin width is what lets a
    record's `dtime` be used as a bin index with no arithmetic."""
    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(
            bin_width_s=64e-12, record_length_s=6.4e-9, gates=2
        )
        assert phlib.binning == 4  # 4 ps * 2**4 = 64 ps
    finally:
        await adapter.disconnect()


async def test_the_record_length_becomes_a_whole_number_of_bins(phlib):
    adapter = await _connected(phlib)
    try:
        config = await adapter.configure_gates(
            bin_width_s=4e-12, record_length_s=11e-12, gates=1
        )
        assert config.bins == 3
        assert config.record_length_s == pytest.approx(12e-12)
        assert RECORD_LENGTH in config.report()
    finally:
        await adapter.disconnect()


async def test_a_window_longer_than_twelve_bits_is_capped_and_reported(phlib):
    """`dtime` is 12 bits, so no readout can hold more than 4096 bins.

    That ceiling cannot be stated as a bound on the record length,
    because it depends on the bin width that is only settled during the
    same call — at 4 ps, 2 us is comfortably inside the declared bound
    and still 500,000 bins. So it is reported as an adjustment rather
    than clamped: a readout silently cut short would make every T1 wrong.
    """
    adapter = await _connected(phlib)
    try:
        config = await adapter.configure_gates(
            bin_width_s=4e-12, record_length_s=2e-6, gates=1
        )
        assert config.bins == MAX_BINS
        assert config.record_length_s == pytest.approx(MAX_BINS * 4e-12)
        assert "12 bits" in config.report()
    finally:
        await adapter.disconnect()


async def test_a_window_past_the_instrument_entirely_is_clipped(phlib):
    """At the coarsest 512 ps the longest window this instrument can
    record is 2.097 us, and that *is* expressible as a bound."""
    adapter = await _connected(phlib)
    try:
        config = await adapter.configure_gates(
            bin_width_s=512e-12, record_length_s=10e-6, gates=1
        )
        assert config.bins == MAX_BINS
        assert config.record_length_s == pytest.approx(MAX_BINS * 512e-12)
        assert "maximum" in config.report()
    finally:
        await adapter.disconnect()


async def test_an_absurd_configuration_is_refused_rather_than_allocated(phlib):
    adapter = await _connected(phlib)
    try:
        with pytest.raises(ValueError, match="histogram cells"):
            await adapter.configure_gates(
                bin_width_s=4e-12, record_length_s=16e-9, gates=60000
            )
    finally:
        await adapter.disconnect()


async def test_configuring_reports_the_shape_the_trace_will_have(phlib):
    adapter = await _connected(phlib)
    try:
        config = await adapter.configure_gates(8e-12, 80e-12, 5)
        assert config.shape == (5, 10)
        trace = await adapter.get_trace()
        assert trace.arrays["counts"].values.shape == (5, 10)
    finally:
        await adapter.disconnect()


# --- Counting ---------------------------------------------------------------


async def test_counting_before_configuring_says_what_to_do_first(phlib):
    adapter = await _connected(phlib)
    try:
        with pytest.raises(DeviceError, match="configure_gates first"):
            await adapter.start_counting()
    finally:
        await adapter.disconnect()


async def test_a_trace_before_configuring_is_refused(phlib):
    adapter = await _connected(phlib)
    try:
        with pytest.raises(DeviceError, match="no gates configured"):
            await adapter.get_trace()
    finally:
        await adapter.disconnect()


async def test_the_device_is_given_an_acquisition_time(phlib):
    """It needs one up front; a run ends by calling `stop_counting`, not
    by this expiring, so the default is the device's maximum."""
    adapter = await _connected(phlib, acquisition_ms=5000)
    try:
        await adapter.configure_gates(4e-12, 16e-12, 2)
        await adapter.start_counting()
        assert phlib.started == [5000]
    finally:
        await adapter.stop_counting()
        await adapter.disconnect()


async def test_records_waiting_in_the_fifo_reach_the_histogram(phlib):
    gates, bins = 4, 8
    phlib.records = [photon(sync, 1) for sync in range(gates)]
    phlib.ctc_done = 1  # the measurement ends once the FiFo is drained

    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(4e-12, bins * 4e-12, gates)
        await adapter.start_counting()
        adapter._reader.join(timeout=5)
        trace = await adapter.get_trace()
        counts = trace.arrays["counts"].values
        assert counts[:, 1].tolist() == [1.0] * gates
        assert counts.sum() == gates
    finally:
        await adapter.stop_counting()
        await adapter.disconnect()


async def test_sweeps_counts_complete_passes_over_every_readout(phlib):
    """What a pulsed run reports its progress in."""
    gates = 4
    phlib.records = [photon(sync, 0) for sync in range(2 * gates)]
    phlib.ctc_done = 1

    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(4e-12, 16e-12, gates)
        await adapter.start_counting()
        adapter._reader.join(timeout=5)
        assert (await adapter.counter_status())["sweeps"] == 2
    finally:
        await adapter.stop_counting()
        await adapter.disconnect()


async def test_a_full_fifo_is_reported_because_nothing_raises(phlib):
    """A trace taken while this is climbing is missing photons, and it
    does not look like it is."""
    phlib.records = [photon(0, 0)]
    phlib.flags = 0x0003
    phlib.ctc_done = 1

    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(4e-12, 16e-12, 1)
        await adapter.start_counting()
        adapter._reader.join(timeout=5)
        assert (await adapter.read())["fifo_overruns"] >= 1
    finally:
        await adapter.stop_counting()
        await adapter.disconnect()


async def test_stopping_is_safe_when_nothing_is_running(phlib):
    """It is what an aborted run calls, and an abort cannot know how far
    the run got."""
    adapter = await _connected(phlib)
    try:
        await adapter.stop_counting()
        await adapter.stop_counting()
    finally:
        await adapter.disconnect()


async def test_stopping_stops_the_device_and_joins_the_reader(phlib):
    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(4e-12, 16e-12, 2)
        await adapter.start_counting()
        await adapter.stop_counting()
        assert adapter._reader is None
        assert phlib.stopped >= 1
    finally:
        await adapter.disconnect()


async def test_clearing_does_not_touch_the_instrument(phlib):
    """The histogram lives in the adapter, not on the device — which is
    also what makes this safe between two sweeps of a run."""
    phlib.records = [photon(0, 2)]
    phlib.ctc_done = 1

    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(4e-12, 16e-12, 1)
        await adapter.start_counting()
        adapter._reader.join(timeout=5)
        assert (await adapter.get_trace()).arrays["counts"].values.sum() == 1

        await adapter.clear()
        assert (await adapter.get_trace()).arrays["counts"].values.sum() == 0
    finally:
        await adapter.stop_counting()
        await adapter.disconnect()


# --- The trace --------------------------------------------------------------


async def test_the_trace_carries_real_axes(phlib):
    """The point of returning a `Dataset`: the run lands in HDF5 with
    coordinates, and a view lays itself out without being told."""
    adapter = await _connected(phlib)
    try:
        await adapter.configure_gates(16e-12, 16 * 16e-12, 3)
        array = (await adapter.get_trace()).arrays["counts"]
        readout, time = array.axes
        assert readout.name == "readout" and readout.kind == "index"
        assert time.name == "time" and time.unit == "s"
        assert time.values[1] == pytest.approx(16e-12)
        assert array.unit == "counts"
    finally:
        await adapter.disconnect()


async def test_the_count_rates_are_reported_for_alignment(phlib):
    """CH0 says the sequence is running, CH1 says the detector sees light.
    Between them they are the whole first-light diagnosis."""
    adapter = await _connected(phlib)
    try:
        reading = await adapter.read()
        assert reading["sync_rate"] == 1000
        assert reading["input_rate"] == 25000
        assert reading["model"] == "PicoHarp 300"
        assert reading["serial_number"] == "1041234"
    finally:
        await adapter.disconnect()


async def test_changing_a_cfd_level_reaches_the_device(phlib):
    adapter = await _connected(phlib)
    try:
        await adapter.write({"input_level_mv": 200})
        assert phlib.cfd[1][0] == 200
    finally:
        await adapter.disconnect()


async def test_the_sync_divider_only_offers_what_the_device_has(phlib):
    """And it must stay at 1 for pulsed work: dividing the sync would
    merge several readouts into one gate."""
    from labpilot.core.errors import ChoiceError

    adapter = await _connected(phlib)
    try:
        with pytest.raises(ChoiceError):
            adapter.validate_write({"sync_divider": 3})
        assert adapter.validate_write({"sync_divider": 4})
    finally:
        await adapter.disconnect()


async def test_disconnecting_stops_and_closes(phlib):
    adapter = await _connected(phlib)
    await adapter.configure_gates(4e-12, 16e-12, 2)
    await adapter.start_counting()
    await adapter.disconnect()
    assert phlib.closed == [0]
    with pytest.raises(DeviceError, match="not connected"):
        adapter._read_sync()


def test_ctypes_out_parameters_are_what_the_fake_assumes():
    """The stand-in reads `byref(x)._obj`, which only works because the
    driver passes `byref`. If it ever passed a pointer differently these
    tests would pass and the driver would read zeros."""
    value = ctypes.c_int(7)
    assert ctypes.byref(value)._obj is value
