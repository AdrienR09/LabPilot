"""PicoQuant PicoHarp 300 in T3 mode, as a gated photon counter.

The photon counter for a pulsed NV rig, and the one real instrument the
whole pulsed stack was waiting on. `MockGatedCounter` synthesises the
physics and the Swabian Time Tagger implements the contract, but a Time
Tagger is a different instrument; if the PicoHarp is what is on the
bench, this is what counts.

## T3 mode *is* the gated-counter contract

`GatedCounterMixin` wants a 2-D `(gate, time_bin)` array: one histogram
per readout window. T3 mode gives, for every photon, the sync period it
arrived in and how long after that sync it arrived — which is exactly
those two indices:

    gate     = sync period, modulo the number of readouts per sequence
    time_bin = the record's own `dtime`, already in device resolution units

So CH0 takes the pulse sequence's gate line and CH1 takes the APD, and
the sequence's readouts become the histogram's first axis.

## The device does not do this for us

Unlike the Time Tagger, whose `TimeDifferences` builds per-readout
histograms in hardware, the PicoHarp streams raw records and nothing
else. So this adapter reads the FiFo on a background thread and
accumulates the histogram itself, vectorised with numpy — `PH_ReadFiFo`
blocks for up to the device's 80 ms timeout, which is why it is a thread
and not a coroutine.

The consequence worth knowing: if the host cannot keep up, the device's
FiFo fills and records are **lost**. That is not an error the driver
raises, so `PH_GetFlags` is checked each pass and `fifo_overruns` is
reported in the schema. A trace taken while that number is climbing is
missing photons, and it does not look like it is.

## The record format, and how it was established

A T3 record is one 32-bit word:

    [ 4 bits channel | 12 bits dtime | 16 bits sync counter ]

`channel == 15` is not a channel — it is the sync counter wrapping, and
the true sync index continues 65536 further on. Every other record is a
photon.

That matters enough to say where it comes from, because getting it wrong
produces an adapter that runs and counts nonsense. The function
signatures are from PicoQuant's own `phlib.h`; the limits are their
`phdefin.h` values; and the bit layout and the wraparound were confirmed
against **two** independent sources — PicoQuant's PicoHarp documentation
and `phconvert`'s `rtPicoHarp300T3` record definition
(`channel_bit=4, time_bit=16, dtime_bit=12, WRAPAROUND=65536`), which is
the reader most of the field uses for `.ptu` files.

## Two things this deliberately does not do

**No marker-based gate pinning.** The Time Tagger has a second input
that pins histogram 0 to the start of the sequence, so one dropped gate
shifts a single sweep instead of rotating every later one. The PicoHarp
has markers that could serve, but the meaning of the record `channel`
field for markers is the one part of the format the available
documentation contradicts itself about — one place says a marker is
`0b1000`, another `0b1111`, which is also the overflow value. Rather
than guess, markers are left disabled, so the only records that arrive
are photons and overflows and the decoding above is exact. **The cost is
real and is a property of the instrument here, not of this code: a lost
sync edge rotates the gate axis for the rest of the run.** Keep the
sequence's gate line clean, and prefer a Time Tagger where the sequence
is long.

**No PHR 800 router.** With one, record channels 1 to 3 carry the router's
extra inputs, which is a second claim on the same four bits. One
detector on CH1 is the configuration this supports, and
`PH_EnableRouting` is never called.

Driven through PicoQuant's `phlib` (`phlib64.dll` on Windows,
`libph300.so` on Linux) via ctypes — there is no PyPI package to depend
on, so there is no extra to install, only PicoQuant's own driver. Loaded
inside `_connect_sync`, so this adapter registers, describes itself and
is probeable on a machine that has never seen one. **Not run against
hardware**; the contract, the quantisation, the decoding and the trace's
shape are covered headlessly in `tests/test_picoharp300.py`, including a
synthetic record stream whose histogram is known in advance.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
import threading
from typing import Any

import numpy as np

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta
from labpilot.core.device.constraints import (
    Adjustment,
    Constraints,
    Quantised,
    ScalarConstraint,
)
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import DeviceError
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments._vendor_library import VendorLibrary
from labpilot.instruments.gated_counter_mixin import (
    BIN_WIDTH,
    GATES,
    RECORD_LENGTH,
    GateConfig,
    GatedCounterMixin,
)

__all__ = ["PicoHarp300Adapter", "decode_t3"]

# --- PicoQuant's constants (phdefin.h) ------------------------------------

MODE_T3 = 3
MAXDEVNUM = 8
TTREADMAX = 131_072
"""Records per `PH_ReadFiFo` call — 128K, the device's own ceiling."""
BINSTEPSMAX = 8
BASE_RESOLUTION = 4e-12
"""The PH300's finest bin. Re-read from the device on connect, so a unit
that reports otherwise wins over this."""

DISCR_MIN_MV, DISCR_MAX_MV = 0, 800
ZERO_CROSS_MIN_MV, ZERO_CROSS_MAX_MV = 0, 20
SYNC_DIVIDERS = (1, 2, 4, 8)
OFFSET_MAX_PS = 1_000_000_000
SYNC_OFFSET_MIN_PS, SYNC_OFFSET_MAX_PS = -99_999, 99_999
ACQ_MIN_MS, ACQ_MAX_MS = 1, 10 * 60 * 60 * 1000

FLAG_FIFOFULL = 0x0003

# --- The T3 record --------------------------------------------------------

T3_SYNC_BITS = 16
T3_DTIME_BITS = 12
T3_CHANNEL_SHIFT = T3_SYNC_BITS + T3_DTIME_BITS
T3_SYNC_MASK = (1 << T3_SYNC_BITS) - 1
T3_DTIME_MASK = (1 << T3_DTIME_BITS) - 1
T3_OVERFLOW_CHANNEL = 0xF
T3_WRAPAROUND = 1 << T3_SYNC_BITS
MAX_BINS = 1 << T3_DTIME_BITS
"""`dtime` is 12 bits, so no window can hold more than 4096 bins — and at
the coarsest 512 ps that caps the recorded window at 2.097 us. A readout
longer than that is not a setting this instrument has."""

#: Guards a mistyped sweep count from becoming a multi-gigabyte array.
MAX_CELLS = 200_000_000


def decode_t3(
    words: np.ndarray, gates: int, bins: int, sync_base: int = 0
) -> tuple[np.ndarray, int, int, int]:
    """Histogram one FiFo batch into `(gate, time_bin)`.

    Returns the counts for this batch, the new sync base, the highest
    absolute sync index seen, and how many photons arrived *after* the
    recorded window and were therefore dropped.

    Separate from the adapter and pure, because this is the part that is
    easy to get wrong and impossible to check with the instrument on the
    bench: a sign error here is a plausible-looking histogram.
    """
    words = np.asarray(words, dtype=np.uint32)
    channel = words >> np.uint32(T3_CHANNEL_SHIFT)
    overflow = channel == T3_OVERFLOW_CHANNEL

    # The correction for a photon is the number of wraps strictly before
    # it: an overflow record is not itself a photon, so a cumulative sum
    # evaluated at a photon's index counts exactly those.
    wraps = np.cumsum(overflow, dtype=np.int64) * T3_WRAPAROUND
    photons = ~overflow

    counts = np.zeros(gates * bins, dtype=np.int64)
    highest = -1
    dropped = 0

    if photons.any():
        sync = (
            (words[photons] & np.uint32(T3_SYNC_MASK)).astype(np.int64)
            + wraps[photons]
            + sync_base
        )
        dtime = ((words[photons] >> np.uint32(T3_SYNC_BITS))
                 & np.uint32(T3_DTIME_MASK)).astype(np.int64)

        # A photon later than the recorded window is not an error — it is
        # the window being shorter than the physics. Counted, not folded
        # back in, because wrapping it would put late light in the first
        # bin and look like a signal.
        inside = dtime < bins
        dropped = int((~inside).sum())
        highest = int(sync.max())

        flat = (sync[inside] % gates) * bins + dtime[inside]
        counts += np.bincount(flat, minlength=gates * bins)

    return (
        counts.reshape(gates, bins),
        sync_base + int(overflow.sum()) * T3_WRAPAROUND,
        highest,
        dropped,
    )


#: What `phlib` is called, per platform. One list, read by both the loader
#: and `vendor_library()` — a UI that reported different names from the ones
#: a connect tries would be worse than no UI.
LIBRARY_NAMES: tuple[str, ...] = (
    ("phlib64.dll", "phlib.dll") if sys.platform == "win32" else ("libph300.so",)
)


class PicoHarp300Adapter(GatedCounterMixin, AdapterBase):
    """A PicoHarp 300 counting photons into per-readout histograms.

    Args:
        device_index: Which unit, 0-7, as PicoQuant's library enumerates
            them. Ignored when `serial_number` is given.
        serial_number: Open the unit with this serial instead, whichever
            index it is on. The robust choice on a PC with two of them.
        sync_divider: Prescaler on CH0. **Leave it at 1 for pulsed work**
            — it exists to keep a high-repetition laser's sync below the
            device's rate ceiling, and dividing it would merge several
            readouts into one gate.
        sync_level_mv / sync_zero_cross_mv: CH0's CFD, for the gate line.
        input_level_mv / input_zero_cross_mv: CH1's CFD, for the detector.
        sync_offset_ps: Shifts CH0 against CH1, for cable-length
            differences.
        offset_ps: Delays the start of the recorded window after each
            gate — the device's own `PH_SetOffset`, so the window can skip
            a laser pulse's leading edge without spending bins on it.
        acquisition_ms: The device needs a measurement duration up front.
            The default is its maximum (10 hours); a run ends by calling
            `stop_counting`, not by this expiring.
        library: Path to `phlib`, when it is not where ctypes looks.
    """

    def __init__(
        self,
        device_index: int = 0,
        serial_number: str = "",
        sync_divider: int = 1,
        sync_level_mv: int = 100,
        sync_zero_cross_mv: int = 10,
        input_level_mv: int = 100,
        input_zero_cross_mv: int = 10,
        sync_offset_ps: int = 0,
        offset_ps: int = 0,
        acquisition_ms: int = ACQ_MAX_MS,
        library: str = "",
        name: str = "picoharp_300",
    ) -> None:
        super().__init__()
        self._index = int(device_index)
        self._serial = str(serial_number or "")
        self._sync_divider = int(sync_divider)
        self._sync_level = int(sync_level_mv)
        self._sync_zero_cross = int(sync_zero_cross_mv)
        self._input_level = int(input_level_mv)
        self._input_zero_cross = int(input_zero_cross_mv)
        self._sync_offset = int(sync_offset_ps)
        self._offset = int(offset_ps)
        self._acquisition_ms = int(acquisition_ms)
        self._library = str(library or "")
        self._name = name

        self._dll: Any = None
        self._model = ""
        self._part = ""
        self._version = ""
        self._base_resolution = BASE_RESOLUTION
        self._bin_steps = BINSTEPSMAX

        self._config: GateConfig | None = None
        self._counts: np.ndarray | None = None
        self._sync_base = 0
        self._highest_sync = -1
        self._dropped_late = 0
        self._fifo_overruns = 0
        self._reader: threading.Thread | None = None
        self._halt = threading.Event()
        self._tally = threading.Lock()

    # --- What it is --------------------------------------------------------

    @classmethod
    def vendor_library(cls) -> VendorLibrary:
        """What `library=` wants. PicoQuant's installer puts `phlib` on the
        library search path rather than in a fixed directory, so there are
        names to look for and no candidate paths."""
        return VendorLibrary(
            parameter="library",
            product="PicoHarp 300",
            vendor="PicoQuant",
            candidates=LIBRARY_NAMES,
            installer="PicoQuant's PicoHarp driver installation",
        )

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="counter",
            parameters=(
                Parameter("running", dtype="bool", role=ParamRole.STATUS),
                Parameter("sweeps", dtype="i8", role=ParamRole.STATUS,
                          description="Complete passes over every readout"),
                Parameter("gates", dtype="i8", role=ParamRole.STATUS),
                Parameter("bins", dtype="i8", role=ParamRole.STATUS),
                Parameter("resolution", unit="s", role=ParamRole.STATUS,
                          description="Width of one time bin, as set"),
                Parameter("sync_rate", unit="Hz", role=ParamRole.STATUS,
                          description="CH0 — the sequence's readout rate"),
                Parameter("input_rate", unit="Hz", role=ParamRole.STATUS,
                          description="CH1 — the detector's count rate"),
                Parameter(
                    "dropped_late", dtype="i8", role=ParamRole.STATUS,
                    description=(
                        "Photons that arrived after the recorded window "
                        "ended. Not an error — the window being shorter "
                        "than the physics."
                    ),
                ),
                Parameter(
                    "fifo_overruns", dtype="i8", role=ParamRole.STATUS,
                    description=(
                        "Times the device's FiFo filled because the host "
                        "could not keep up. Any value above zero means the "
                        "trace is missing photons."
                    ),
                ),
                Parameter("warnings", dtype="str", role=ParamRole.STATUS,
                          description="The device's own warning text, if any"),
                Parameter("model", dtype="str", role=ParamRole.STATUS),
                Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                Parameter(
                    "sync_divider", dtype="i8", settable=True,
                    role=ParamRole.SETTING, choices=SYNC_DIVIDERS,
                    description="Leave at 1 for pulsed work — see the class docstring",
                ),
                Parameter(
                    "sync_level_mv", dtype="i8", unit="mV", settable=True,
                    role=ParamRole.SETTING,
                    limits=(DISCR_MIN_MV, DISCR_MAX_MV),
                ),
                Parameter(
                    "sync_zero_cross_mv", dtype="i8", unit="mV", settable=True,
                    role=ParamRole.SETTING,
                    limits=(ZERO_CROSS_MIN_MV, ZERO_CROSS_MAX_MV),
                ),
                Parameter(
                    "input_level_mv", dtype="i8", unit="mV", settable=True,
                    role=ParamRole.SETTING,
                    limits=(DISCR_MIN_MV, DISCR_MAX_MV),
                ),
                Parameter(
                    "input_zero_cross_mv", dtype="i8", unit="mV", settable=True,
                    role=ParamRole.SETTING,
                    limits=(ZERO_CROSS_MIN_MV, ZERO_CROSS_MAX_MV),
                ),
                Parameter(
                    "sync_offset_ps", dtype="i8", unit="ps", settable=True,
                    role=ParamRole.SETTING,
                    limits=(SYNC_OFFSET_MIN_PS, SYNC_OFFSET_MAX_PS),
                ),
                Parameter(
                    "offset_ps", dtype="i8", unit="ps", settable=True,
                    role=ParamRole.SETTING, limits=(0, OFFSET_MAX_PS),
                ),
                Parameter(
                    "acquisition_ms", dtype="i8", unit="ms", settable=True,
                    role=ParamRole.SETTING, limits=(ACQ_MIN_MS, ACQ_MAX_MS),
                ),
            ),
            actions=["start_counting", "stop_counting", "clear", "calibrate"],
            tags=[
                "PicoQuant", "PicoHarp", "PicoHarp 300", "GatedCounter",
                "Photon", "TCSPC", "ODMR", "Pulsed",
            ],
        )

    def counter_constraints(self) -> Constraints:
        """What this device will do with a requested configuration.

        The bin width is not a granularity but a **ladder**: the device
        divides its base resolution by powers of two, so 4, 8, 16 … 512 ps
        and nothing between. `ScalarConstraint.allowed` says that exactly,
        rather than approximating it with a step that would accept 12 ps.
        """
        ladder = tuple(
            self._base_resolution * 2**step for step in range(self._bin_steps)
        )
        return Constraints(
            scalars=(
                ScalarConstraint(BIN_WIDTH, allowed=ladder, unit="s"),
                ScalarConstraint(
                    RECORD_LENGTH,
                    bounds=(ladder[0], MAX_BINS * ladder[-1]),
                    unit="s",
                ),
                ScalarConstraint(GATES, bounds=(1, 65536), enforce_int=True),
            )
        )

    # --- The library -------------------------------------------------------

    def _load(self) -> Any:
        candidates = [self._library] if self._library else list(LIBRARY_NAMES)
        loader = ctypes.WinDLL if sys.platform == "win32" else ctypes.CDLL
        errors = []
        for candidate in candidates:
            try:
                return loader(candidate)
            except OSError as exc:
                errors.append(f"{candidate}: {exc}")
        raise ImportError(
            "Talking to a PicoHarp 300 needs PicoQuant's own `phlib`, which "
            "comes with their driver installation rather than from PyPI — "
            "there is no package to pip-install. Pass library=<path> if it "
            "is installed somewhere ctypes does not look.\n  "
            + "\n  ".join(errors)
        )

    def _check(self, code: int, what: str) -> None:
        """Turn a PHLib return code into an error that names the call.

        Every function in the library returns 0 or a negative code, and
        the library itself can render the code as text — so there is no
        reason for a caller ever to see a bare number.
        """
        if code == 0:
            return
        text = ctypes.create_string_buffer(64)
        with contextlib.suppress(Exception):
            self._dll.PH_GetErrorString(text, ctypes.c_int(code))
        message = text.value.decode("ascii", "replace").strip()
        raise DeviceError(
            f"{what} failed: {message or 'error'} ({code})", device=self._name
        )

    # --- Connection --------------------------------------------------------

    def _connect_sync(self) -> None:
        self._dll = self._load()
        self._open()
        try:
            self._check(self._dll.PH_Initialize(self._index, MODE_T3), "PH_Initialize")
            self._read_hardware_info()
            self._check(self._dll.PH_Calibrate(self._index), "PH_Calibrate")
            self._apply_inputs()
        except Exception:
            with contextlib.suppress(Exception):
                self._dll.PH_CloseDevice(self._index)
            raise

    def _open(self) -> None:
        """Open the requested index, or hunt for a serial number.

        A serial is worth supporting as more than a label: a PC with two
        PicoHarps enumerates them in whatever order the USB stack found
        them, so an index is not stable across a reboot and a measurement
        can silently end up on the other instrument.
        """
        serial = ctypes.create_string_buffer(8)
        if not self._serial:
            self._check(
                self._dll.PH_OpenDevice(self._index, serial), "PH_OpenDevice"
            )
            self._serial = serial.value.decode("ascii", "replace").strip()
            return

        for index in range(MAXDEVNUM):
            if self._dll.PH_OpenDevice(index, serial) != 0:
                continue
            found = serial.value.decode("ascii", "replace").strip()
            if found == self._serial:
                self._index = index
                return
            with contextlib.suppress(Exception):
                self._dll.PH_CloseDevice(index)
        raise DeviceError(
            f"No PicoHarp with serial {self._serial!r} among the "
            f"{MAXDEVNUM} indices the library enumerates.",
            device=self._name,
        )

    def _read_hardware_info(self) -> None:
        model = ctypes.create_string_buffer(16)
        part = ctypes.create_string_buffer(8)
        version = ctypes.create_string_buffer(8)
        self._check(
            self._dll.PH_GetHardwareInfo(self._index, model, part, version),
            "PH_GetHardwareInfo",
        )
        self._model = model.value.decode("ascii", "replace").strip()
        self._part = part.value.decode("ascii", "replace").strip()
        self._version = version.value.decode("ascii", "replace").strip()

        resolution = ctypes.c_double(0)
        steps = ctypes.c_int(0)
        self._check(
            self._dll.PH_GetBaseResolution(
                self._index, ctypes.byref(resolution), ctypes.byref(steps)
            ),
            "PH_GetBaseResolution",
        )
        # Reported in picoseconds; the device's own answer wins over the
        # module constant, which is why `counter_constraints` is built from
        # it rather than from a literal.
        if resolution.value > 0:
            self._base_resolution = float(resolution.value) * 1e-12
        if steps.value > 0:
            self._bin_steps = int(steps.value)

    def _apply_inputs(self) -> None:
        self._check(
            self._dll.PH_SetSyncDiv(self._index, self._sync_divider),
            "PH_SetSyncDiv",
        )
        for channel, level, zero in (
            (0, self._sync_level, self._sync_zero_cross),
            (1, self._input_level, self._input_zero_cross),
        ):
            self._check(
                self._dll.PH_SetInputCFD(self._index, channel, level, zero),
                f"PH_SetInputCFD(channel {channel})",
            )
        self._check(
            self._dll.PH_SetSyncOffset(self._index, self._sync_offset),
            "PH_SetSyncOffset",
        )
        self._check(
            self._dll.PH_SetOffset(self._index, self._offset), "PH_SetOffset"
        )

    def _disconnect_sync(self) -> None:
        self._halt_reader()
        if self._dll is not None:
            with contextlib.suppress(Exception):
                self._dll.PH_StopMeas(self._index)
            with contextlib.suppress(Exception):
                self._dll.PH_CloseDevice(self._index)
        self._dll = None

    def _require(self) -> Any:
        if self._dll is None:
            raise DeviceError(f"{self._name} is not connected", device=self._name)
        return self._dll

    # --- Reading ------------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        # Refused rather than answered with zeros: every number below
        # would otherwise be a plausible reading from a device that is not
        # there, and a count rate of 0 is exactly what someone chasing a
        # dark detector is looking at.
        self._require()
        config = self._config
        sync_rate, input_rate = self._rates()
        with self._tally:
            dropped, overruns, highest = (
                self._dropped_late, self._fifo_overruns, self._highest_sync
            )
        gates = config.gates if config else 0
        return {
            "running": self._reader is not None and self._reader.is_alive(),
            "sweeps": (highest + 1) // gates if gates else 0,
            "gates": gates,
            "bins": config.bins if config else 0,
            "resolution": config.bin_width_s if config else self._base_resolution,
            "sync_rate": sync_rate,
            "input_rate": input_rate,
            "dropped_late": dropped,
            "fifo_overruns": overruns,
            "warnings": self._warnings(),
            "model": self._model,
            "serial_number": self._serial,
            "sync_divider": self._sync_divider,
            "sync_level_mv": self._sync_level,
            "sync_zero_cross_mv": self._sync_zero_cross,
            "input_level_mv": self._input_level,
            "input_zero_cross_mv": self._input_zero_cross,
            "sync_offset_ps": self._sync_offset,
            "offset_ps": self._offset,
            "acquisition_ms": self._acquisition_ms,
        }

    def _rates(self) -> tuple[float, float]:
        """CH0 and CH1 count rates — the alignment instrument.

        Read before the warnings deliberately: PicoQuant's library derives
        its warnings from the most recent rate reading, so asking for them
        in the other order reports warnings about whatever was true last
        time.
        """
        rates = []
        for channel in (0, 1):
            value = ctypes.c_int(0)
            try:
                code = self._require().PH_GetCountRate(
                    self._index, channel, ctypes.byref(value)
                )
            except Exception:
                return (0.0, 0.0)
            rates.append(float(value.value) if code == 0 else 0.0)
        return (rates[0], rates[1])

    def _warnings(self) -> str:
        flags = ctypes.c_int(0)
        try:
            if self._require().PH_GetWarnings(self._index, ctypes.byref(flags)) != 0:
                return ""
        except Exception:
            return ""
        if flags.value == 0:
            return ""
        text = ctypes.create_string_buffer(16384)
        with contextlib.suppress(Exception):
            self._dll.PH_GetWarningsText(self._index, text, flags)
        return text.value.decode("ascii", "replace").strip()

    # --- Settings -----------------------------------------------------------

    async def set_sync_divider(self, value: int) -> None:
        self._sync_divider = int(value)
        await self._reapply()

    async def set_sync_level_mv(self, value: int) -> None:
        self._sync_level = int(value)
        await self._reapply()

    async def set_sync_zero_cross_mv(self, value: int) -> None:
        self._sync_zero_cross = int(value)
        await self._reapply()

    async def set_input_level_mv(self, value: int) -> None:
        self._input_level = int(value)
        await self._reapply()

    async def set_input_zero_cross_mv(self, value: int) -> None:
        self._input_zero_cross = int(value)
        await self._reapply()

    async def set_sync_offset_ps(self, value: int) -> None:
        self._sync_offset = int(value)
        await self._reapply()

    async def set_offset_ps(self, value: int) -> None:
        self._offset = int(value)
        await self._reapply()

    async def set_acquisition_ms(self, value: int) -> None:
        self._acquisition_ms = int(value)

    async def _reapply(self) -> None:
        if self._dll is not None:
            await self._to_thread(self._apply_inputs)

    # --- The gated-counter contract ----------------------------------------

    async def configure_gates(
        self, bin_width_s: float, record_length_s: float, gates: int
    ) -> GateConfig:
        constraints = self.counter_constraints()
        quantised = constraints.quantise(
            {
                BIN_WIDTH: bin_width_s,
                RECORD_LENGTH: record_length_s,
                GATES: gates,
            }
        )
        width = float(quantised[BIN_WIDTH])
        count = int(quantised[GATES])
        bins = max(round(float(quantised[RECORD_LENGTH]) / width), 1)

        adjustments = list(quantised.adjustments)
        if bins > MAX_BINS:
            # Not a limit that can be expressed as a bound on the record
            # length, because it depends on the bin width that was only
            # just settled. Reported rather than absorbed: a readout
            # silently cut to 2 us would make every T1 wrong.
            bins = MAX_BINS
            adjustments.append(
                Adjustment(
                    RECORD_LENGTH, record_length_s, bins * width,
                    f"T3 dtime is {T3_DTIME_BITS} bits, so at most "
                    f"{MAX_BINS} bins per readout",
                )
            )
        record = bins * width
        # Any real difference is reported, not only one larger than half a
        # bin: the caller asked for a number and is getting a different
        # one, and absorbing small differences is how a 10% error in a
        # short readout window becomes invisible.
        if abs(record - record_length_s) > width * 1e-9:
            adjustments.append(
                Adjustment(
                    RECORD_LENGTH, record_length_s, record,
                    f"a whole number of {width * 1e12:g} ps bins",
                )
            )
        if bins * count > MAX_CELLS:
            raise ValueError(
                f"{bins} bins x {count} readouts is {bins * count} histogram "
                f"cells. Widen the bins or shorten the record."
            )

        config = GateConfig(
            bin_width_s=width,
            record_length_s=record,
            gates=count,
            quantised=Quantised(
                {**quantised.values, BIN_WIDTH: width, RECORD_LENGTH: record},
                tuple(adjustments),
            ),
        )

        # The bin width is set on the device as a power-of-two step, which
        # is what makes a record's `dtime` directly a bin index.
        step = round(float(np.log2(width / self._base_resolution)))
        await self._to_thread(
            lambda: self._check(
                self._require().PH_SetBinning(self._index, step), "PH_SetBinning"
            )
        )

        await self.stop_counting()
        with self._tally:
            self._config = config
            self._counts = np.zeros(config.shape, dtype=np.int64)
            self._sync_base = 0
            self._highest_sync = -1
            self._dropped_late = 0
            self._fifo_overruns = 0
        return config

    async def start_counting(self) -> None:
        if self._config is None:
            raise DeviceError(
                f"{self._name} has no gates configured — call configure_gates first",
                device=self._name,
            )
        if self._reader is not None and self._reader.is_alive():
            return
        dll = self._require()
        await self._to_thread(
            lambda: self._check(
                dll.PH_StartMeas(self._index, self._acquisition_ms), "PH_StartMeas"
            )
        )
        self._halt.clear()
        self._reader = threading.Thread(
            target=self._drain, name=f"{self._name}-fifo", daemon=True
        )
        self._reader.start()

    async def stop_counting(self) -> None:
        """Safe when nothing is running: it is what an aborted run calls,
        and an abort cannot know how far the run got."""
        if self._dll is not None:
            await self._to_thread(
                lambda: self._dll.PH_StopMeas(self._index)
            )
        await self._to_thread(self._halt_reader)

    def _halt_reader(self) -> None:
        self._halt.set()
        reader, self._reader = self._reader, None
        if reader is not None and reader.is_alive():
            reader.join(timeout=2.0)

    async def clear(self) -> None:
        """Throw away what has been accumulated and start from zero.

        The histogram lives here rather than on the device, so this does
        not touch the instrument — which also means it is safe to call
        while counting, between two sweeps of a run.
        """
        with self._tally:
            if self._counts is not None:
                self._counts[...] = 0
            self._sync_base = 0
            self._highest_sync = -1
            self._dropped_late = 0

    async def calibrate(self) -> None:
        """Re-run the device's own calibration. Takes a few seconds and
        must not overlap a measurement."""
        await self.stop_counting()
        dll = self._require()
        await self._to_thread(
            lambda: self._check(dll.PH_Calibrate(self._index), "PH_Calibrate")
        )

    async def counter_status(self) -> dict[str, Any]:
        with self._tally:
            highest = self._highest_sync
        gates = self._config.gates if self._config else 0
        return {
            "running": self._reader is not None and self._reader.is_alive(),
            "sweeps": (highest + 1) // gates if gates else 0,
        }

    async def get_trace(self) -> Dataset:
        """Everything counted so far, as `(readout, time_bin)` with axes.

        Safe to call while counting — the copy is taken under the same
        lock the reader thread accumulates under, so a trace is never a
        half-written batch.
        """
        if self._config is None or self._counts is None:
            raise DeviceError(
                f"{self._name} has no gates configured", device=self._name
            )
        config = self._config
        with self._tally:
            counts = self._counts.astype(float, copy=True)

        return Dataset(
            (
                DataArray(
                    "counts",
                    counts,
                    unit="counts",
                    axes=(
                        Axis("readout", np.arange(config.gates), kind="index"),
                        Axis(
                            "time",
                            np.arange(config.bins) * config.bin_width_s,
                            unit="s", kind="time",
                        ),
                    ),
                ),
            ),
            meta=RunMeta(device=self._name),
        )

    # --- The FiFo reader ----------------------------------------------------

    def _drain(self) -> None:
        """Read records until told to stop or the device's time is up.

        On its own thread because `PH_ReadFiFo` blocks for up to the
        device's 80 ms timeout, and because the histogramming has to keep
        up with it: anything slower and the device's FiFo fills and
        records are lost without the driver saying so.
        """
        buffer = (ctypes.c_uint * TTREADMAX)()
        actual = ctypes.c_int(0)
        status = ctypes.c_int(0)
        while not self._halt.is_set():
            dll = self._dll
            if dll is None:
                return
            try:
                if dll.PH_ReadFiFo(
                    self._index, buffer, TTREADMAX, ctypes.byref(actual)
                ) != 0:
                    return
            except Exception:  # pragma: no cover - the DLL going away mid-read
                return
            if actual.value > 0:
                self._accumulate(
                    np.frombuffer(buffer, dtype=np.uint32, count=actual.value)
                )
                self._note_flags()
                continue
            # Nothing waiting: the measurement is either still running and
            # idle, or its acquisition time has expired.
            with contextlib.suppress(Exception):
                if dll.PH_CTCStatus(self._index, ctypes.byref(status)) == 0 and status.value:
                    return

    def _accumulate(self, words: np.ndarray) -> None:
        config = self._config
        if config is None:
            return
        counts, sync_base, highest, dropped = decode_t3(
            words, config.gates, config.bins, self._sync_base
        )
        with self._tally:
            if self._counts is not None:
                self._counts += counts
            self._sync_base = sync_base
            self._dropped_late += dropped
            if highest > self._highest_sync:
                self._highest_sync = highest

    def _note_flags(self) -> None:
        """A full FiFo means photons were dropped, and nothing raises."""
        flags = ctypes.c_int(0)
        with contextlib.suppress(Exception):
            if self._dll.PH_GetFlags(self._index, ctypes.byref(flags)) != 0:
                return
        if flags.value & FLAG_FIFOFULL:
            with self._tally:
                self._fifo_overruns += 1


adapter_registry.register("picoharp_300", PicoHarp300Adapter)
