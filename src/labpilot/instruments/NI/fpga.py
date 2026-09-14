"""NI R-Series (FPGA) cards as a pulse sequencer, and optionally a counter.

An R-Series board is a user-programmable FPGA with analog and digital I/O
on it. What it *does* is whatever gateware you compiled for it, which
makes it a different kind of instrument from every other adapter here:
the card is the same, and two labs' cards do entirely different things.

## The bitfile is the instrument

Compiling gateware needs LabVIEW FPGA and the Xilinx toolchain and takes
tens of minutes. So "convert the pulse sequence into an FPGA program"
cannot mean emitting a bitfile at run time, and this adapter does not
pretend otherwise — see `bitfiles.py`, which is where that reasoning
lives and which qudi's own FPGA pulser confirms by shipping pre-compiled
images and swapping between them to change the sample rate.

What it does instead is the thing a PulseBlaster and a PulseStreamer both
do: compile the sequence into **instructions** — one `(channel mask,
ticks)` word per element — and stream them into the engine the bitfile
already put on the card. `upload_sequence` never sees a waveform and
never builds an array, which is the whole reason it takes the abstract
sequence rather than samples.

## Two ways to choose the image, both first-class

- **Pinned in the configuration**: set `bitfile` to a `.lvbitx` and that
  is what gets loaded. You compiled it, you know what it does.
- **Chosen by the measurement**: leave `bitfile` empty and
  `upload_sequence` picks from the library in
  `~/.labpilot/config/ni_rseries.toml` the image whose engine can play
  what this sequence asks for — enough channels, the right tick rate, a
  counter if the run needs one. Still no compiling: the choice is among
  images the lab already built.

The second is what makes a pulsed measurement able to drive this card
without being told which image to use, and it is why the library entry
states a tick rate and a channel list rather than only a path.

## Capabilities follow the gateware, not the class

Every image this adapter drives is a pulser, so `PulserMixin` is
inherited. The *counter* half is declared on the schema only when the
loaded bitfile actually has the counting registers and FIFO — which
`capabilities_of` reads off the instance, so a card whose image only
pulses does not advertise a counter it cannot deliver. That is the same
reasoning that makes the DAQ card `generic`: what a device can do follows
from how it is configured, not from which class was instantiated.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta
from labpilot.core.device.capabilities import GATED_COUNTER
from labpilot.core.device.constraints import Constraints, ScalarConstraint
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.pulse.sampling import SamplingError, expand
from labpilot.core.pulse.shapes import Shape
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.gated_counter_mixin import (
    BIN_WIDTH,
    GATES,
    RECORD_LENGTH,
    GateConfig,
    GatedCounterMixin,
)
from labpilot.instruments.NI.bitfiles import (
    BitfileEntry,
    BitfileError,
    Gateware,
    find_bitfile,
    find_model,
    load_bitfiles,
    read_bitfile,
)
from labpilot.instruments.pulser_mixin import (
    PulserMixin,
    SequenceReport,
    pulser_constraints,
    quantise_elements,
)

if TYPE_CHECKING:
    from labpilot.core.pulse.sequence import ChannelMap, PulseSequence

__all__ = ["NIRSeriesAdapter", "compile_instructions"]

#: A tick count has 32 bits in the instruction word, so this is the
#: longest single element the engine can hold. Anything longer is split
#: into several instructions rather than refused — a 5 ms repolarisation
#: wait at 100 MHz is 500,000 ticks and fits easily, but a 1 s one at
#: 200 MHz would not, and silently wrapping it would be a sequence that
#: runs and measures the wrong thing.
MAX_TICKS = 0xFFFFFFFF


def compile_instructions(
    intervals: Any, channels: ChannelMap, lines: tuple[str, ...], resolution: float
) -> list[int]:
    """The sequence as the engine's instruction words.

    One U64 per element: ticks in the low 32 bits, the channel mask in
    the high 32. `lines` is the bitfile's channel list **in bit order**,
    so position in it is the bit set in the mask — which is the one thing
    in this file that can silently produce a working sequence on the
    wrong wires, and is why the library entry states the order.

    An element longer than `MAX_TICKS` becomes several instructions
    holding the same mask, so a long wait is expressed rather than
    wrapped.
    """
    index = {line: bit for bit, line in enumerate(lines)}
    words: list[int] = []
    for interval in intervals:
        mask = 0
        for symbolic, value in interval.channels.items():
            physical = channels[symbolic]
            if value is True and physical in index:
                mask |= 1 << index[physical]
        ticks = max(round(interval.duration / resolution), 1) if resolution else 1
        while ticks > MAX_TICKS:
            words.append((mask << 32) | MAX_TICKS)
            ticks -= MAX_TICKS
        words.append((mask << 32) | ticks)
    return words


class NIRSeriesAdapter(PulserMixin, GatedCounterMixin, AdapterBase):
    """One R-Series card, playing whatever its bitfile makes it.

    `kind="generic"`: the interesting contract is
    `upload_sequence`/`pulser_on`/`pulser_off` and, when the image has
    it, the counting half — not read and write. The same call
    `NICardAdapter` makes, for the same reason.
    """

    def __init__(
        self,
        resource: str = "RIO0",
        bitfile: str = "",
        model: str = "generic",
        channels: str | tuple[str, ...] = (),
        tick_rate: float = 0.0,
        gateware: dict[str, str] | None = None,
        name: str = "ni_rseries_fpga",
    ) -> None:
        super().__init__()
        self._name = name
        self.resource = str(resource)
        self.model = find_model(model)
        #: Pinned in configuration, or "" to let the sequence choose.
        self.bitfile = str(bitfile or "")
        #: What a pinned image drives, and how fast. A bitfile says which
        #: registers it has but not what they *mean*, so the lines it
        #: drives and the rate it ticks at cannot be read out of the file
        #: — and without them an image can be loaded and never played.
        #: Stating them here is what makes pinning one in configuration
        #: sufficient on its own, with no library entry.
        self.channels = _lines(channels)
        self.tick_rate = float(tick_rate or 0.0)
        self._gateware = Gateware.from_dict(gateware)

        self._session: Any = None
        self._entry: BitfileEntry | None = None
        self._info: Any = None
        self._loaded: str = ""
        self._report: SequenceReport | None = None
        self._config: GateConfig | None = None
        self._running = False
        self._counting = False
        self._started = 0.0
        self._differences: list[str] = []

    # --- What it is, before anything is opened ----------------------------

    @property
    def schema(self) -> DeviceSchema:
        capabilities = {"pulser"}
        if self._has_counter():
            capabilities.add(GATED_COUNTER)

        return DeviceSchema(
            name=self._name,
            kind="generic",
            parameters=(
                Parameter(
                    "bitfile", dtype="str", role=ParamRole.SETTING,
                    settable=True, readable=True,
                    description=(
                        "The .lvbitx to load. Empty lets the sequence choose "
                        "from the library in ~/.labpilot/config/ni_rseries.toml."
                    ),
                ),
                Parameter(
                    "model", dtype="str", role=ParamRole.SETTING,
                    settable=True, readable=True, choices=_model_choices(),
                    description="Which R-Series card this is.",
                ),
                Parameter(
                    "resource", dtype="str", role=ParamRole.STATUS, readable=True,
                    description="The RIO resource name, e.g. RIO0.",
                ),
                Parameter(
                    "loaded", dtype="str", role=ParamRole.STATUS, readable=True,
                    description="The bitfile actually on the card.",
                ),
                Parameter(
                    "tick_rate", unit="Hz", role=ParamRole.STATUS, readable=True,
                    description="The loaded engine's clock — what durations "
                                "are quantised to.",
                ),
                Parameter(
                    "playing", dtype="bool", role=ParamRole.STATUS, readable=True,
                ),
                Parameter(
                    "warning", dtype="str", role=ParamRole.STATUS, readable=True,
                    description="Any disagreement between what was declared "
                                "and what the card and its bitfile say.",
                ),
            ),
            tags=[
                "ni", "fpga", "r-series", "pulser", "sequencer", "odmr",
                "pulsed", "nifpga",
            ],
            capabilities=frozenset(capabilities),
        )

    def _has_counter(self) -> bool:
        """Whether the image in hand has the counting half.

        From the library entry when one chose the image, and otherwise
        from the bitfile's own declared registers — so a pinned image is
        asked directly rather than assumed either way. Unknown before
        anything is loaded, which reads as "no": advertising a counter
        that may not exist is worse than a run that binds a second
        instrument it did not need to.
        """
        if self._entry is not None:
            return self._entry.counter
        if self._info is not None:
            return self._info.has(*self._gateware.counter_names)
        return False

    # --- Constraints, from the image rather than the card -----------------

    def pulser_constraints(self) -> Any:
        """What the loaded engine can play.

        The bitfile's numbers, not the card's: an R-Series board drives
        whichever lines its gateware was built to drive, at whatever
        derived clock that gateware runs. The card only bounds it.
        """
        entry = self._entry
        rate = 1.0 / self.resolution
        lines = entry.channels if entry else self.channels
        return pulser_constraints(
            sample_rate=rate,
            digital_channels=lines,
            min_element=1.0 / rate if rate else 0.0,
            element_step=1.0 / rate if rate else 0.0,
            max_samples=(entry.memory or None) if entry else None,
        )

    def counter_constraints(self) -> Constraints:
        tick = self.resolution
        return Constraints(scalars=(
            ScalarConstraint(BIN_WIDTH, bounds=(tick, None), step=tick, unit="s"),
            ScalarConstraint(RECORD_LENGTH, bounds=(tick, None), step=tick, unit="s"),
            ScalarConstraint(GATES, bounds=(1, None), enforce_int=True),
        ))

    @property
    def resolution(self) -> float:
        """Seconds per tick of the engine that will play the sequence.

        The loaded image's rate when there is one; otherwise the rate the
        configuration stated, and only then the card's base clock. A
        `tick_rate` someone typed has to be reported back before anything
        is loaded, or it reads as a setting that was ignored — and on this
        adapter it is the number every duration gets quantised to.
        """
        if self._entry and self._entry.tick_rate:
            return 1.0 / self._entry.tick_rate
        if self.tick_rate:
            return 1.0 / self.tick_rate
        return 1.0 / (self.model.base_clock or 40e6)

    # --- Opening the card -------------------------------------------------

    def _connect_sync(self) -> None:
        if self.bitfile:
            # Read first, then describe: `_entry_for` asks the file
            # whether it has the counting half.
            self._info = read_bitfile(self.bitfile)
            self._use(self._entry_for(self.bitfile), self.bitfile)
        # With no bitfile pinned, nothing is loaded yet: the sequence
        # chooses one at upload. Connecting is then only "the resource
        # exists", which is worth doing now rather than at the first
        # measurement.
        self._open()

    def _entry_for(self, path: str) -> BitfileEntry | None:
        """What this adapter knows about the image it is about to load.

        A pinned bitfile is a path someone chose, and it can be described
        two ways: by a library entry that happens to name the same path,
        or by the `channels`/`tick_rate` given alongside it in the
        configuration. Either is sufficient, which is what makes "pin one
        in the config" a complete answer rather than half of one.

        The library wins where both exist, because an entry someone wrote
        for that exact image is more specific than a pair of connection
        fields.
        """
        for entry in load_bitfiles().values():
            if entry.path and str(entry.path).strip() == str(path).strip():
                return entry
        if not self.channels:
            return None
        return BitfileEntry(
            name=Path(path).stem,
            path=str(path),
            model=self.model.number,
            tick_rate=self.tick_rate or self.model.base_clock,
            channels=self.channels,
            # Read off the image itself: it lists its registers, so
            # whether it has the counting half is a question the file can
            # answer rather than one the configuration has to repeat.
            counter=bool(
                self._info is not None
                and self._info.parsed
                and self._info.has(*self._gateware.counter_names)
            ),
        )

    def _use(self, entry: BitfileEntry | None, path: str) -> None:
        self._info = read_bitfile(path)
        self._entry = entry
        missing = self._info.missing(*self._gateware.pulser_names)
        if missing:
            raise BitfileError(
                f"{path} has no {', '.join(missing)} — this adapter plays a "
                f"sequence by streaming instructions into those, so an image "
                f"without them is not a pulse sequencer. Either load the "
                f"reference VI's image, or map your own names with the "
                f"`gateware` setting (see instruments/NI/bitfiles.py)."
            )

    def _open(self) -> None:
        """Open the RIO session on whichever image is in hand.

        Keyed on `_info` rather than on `self.bitfile`: the image the
        *sequence* chose is just as loadable as the one pinned in the
        configuration, and gating this on the pinned setting meant the
        chosen path opened no session at all.
        """
        import nifpga

        self.close_session()
        if self._info is None:
            return
        self._session = nifpga.Session(
            bitfile=str(self._info.path), resource=self.resource
        )
        self._loaded = str(self._info.path)
        self._reconcile()

    def _reconcile(self) -> None:
        """Check what was declared against what the session actually has.

        The same contract `NICardAdapter` has with its model table: the
        device is right by definition, and a disagreement is reported in
        every reading rather than silently overriding either side. It
        matters more here, because `bitfiles.py` parses the `.lvbitx`
        itself and NI has changed that schema between LabVIEW versions —
        this is where a parse that quietly found nothing gets caught.
        """
        self._differences = []
        session = self._session
        if session is None:
            return
        live = {*getattr(session, "registers", {}), *getattr(session, "fifos", {})}
        for name in self._gateware.pulser_names:
            if name not in live:
                self._differences.append(
                    f"the session has no {name!r}, which this adapter writes "
                    f"to play a sequence"
                )
        if self._entry and self._entry.counter:
            for name in self._gateware.counter_names:
                if name not in live:
                    self._differences.append(
                        f"the library says this image counts, but the session "
                        f"has no {name!r}"
                    )

    def close_session(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            finally:
                self._session = None
                self._loaded = ""

    def _disconnect_sync(self) -> None:
        self._running = False
        self._counting = False
        self.close_session()

    # --- Readings ----------------------------------------------------------

    def _read_sync(self) -> dict[str, Any]:
        return {
            "bitfile": self.bitfile,
            "model": self.model.number,
            "resource": self.resource,
            "loaded": self._loaded,
            "tick_rate": (1.0 / self.resolution) if self.resolution else 0.0,
            "playing": self._running,
            "warning": self.warning,
        }

    @property
    def warning(self) -> str:
        """One line naming every disagreement, or "" when there is none."""
        notes = list(self._differences)
        if self._info is not None and not self._info.parsed:
            notes.append(
                f"{self._info.path.name} could not be read offline: "
                f"{self._info.note}"
            )
        return "; ".join(notes)

    async def set_bitfile(self, value: str) -> None:
        self.bitfile = str(value or "")
        if self.bitfile:
            self._info = read_bitfile(self.bitfile)
            self._use(self._entry_for(self.bitfile), self.bitfile)
        else:
            self._entry, self._info = None, None
        if self.connected:
            self._open()

    async def set_model(self, value: str) -> None:
        self.model = find_model(str(value))

    # --- The pulser --------------------------------------------------------

    async def upload_sequence(
        self, sequence: PulseSequence, channels: ChannelMap
    ) -> SequenceReport:
        """Compile the sequence to instructions and stream them in.

        Never to gateware — see the module docstring. When no bitfile is
        pinned this is also where the image gets chosen, from what the
        sequence actually needs.
        """
        sequence.validate()

        analog = sorted(
            channel
            for block in sequence.blocks
            for element in block.elements
            for channel, value in element.channels.items()
            if isinstance(value, Shape)
        )
        if analog:
            raise SamplingError(
                f"Sequence {sequence.name!r} drives {', '.join(analog)} with an "
                f"analog shape. This engine plays digital instructions — one "
                f"channel mask per element — so author it with "
                f"RigProfile(analog_mw=False) to gate an external source, or "
                f"load an image whose gateware synthesises a waveform and "
                f"drive that as an AWG."
            )

        if not self.bitfile:
            self._choose_for(sequence, channels)

        entry, constraints = self._entry, self.pulser_constraints()
        if entry is None or not entry.channels:
            raise BitfileError(
                f"{self._loaded or self.bitfile or 'no bitfile'} has no channel "
                f"list, so there is no way to know which bit drives which line. "
                f"Add an entry for it to ~/.labpilot/config/ni_rseries.toml "
                f"naming `channels` in bit order."
            )

        activation = constraints.check(sequence, channels)
        intervals = list(expand(sequence))
        quantised = quantise_elements(
            intervals, constraints, minimum=self.resolution
        )
        words = compile_instructions(
            intervals, channels, entry.channels, self.resolution
        )
        if entry.memory and len(words) > entry.memory:
            raise BitfileError(
                f"Sequence {sequence.name!r} compiles to {len(words):,} "
                f"instructions and {entry.name} holds {entry.memory:,}. Use an "
                f"image with deeper memory, or reduce the number of swept "
                f"points."
            )
        self._write_program(words)

        self._report = SequenceReport(
            name=sequence.name,
            channels={symbolic: channels[symbolic] for symbolic in sequence.channels},
            points=sequence.points,
            readouts=sequence.readouts(),
            duration=sequence.duration,
            quantised=quantised,
            instructions=len(words),
            activation=activation,
        )
        return self._report

    def _choose_for(self, sequence: PulseSequence, channels: ChannelMap) -> None:
        """Pick and load the image this sequence needs.

        The half of the adapter that lets a measurement drive the card
        without being told which bitfile to use.
        """
        wanted = len({channels[symbolic] for symbolic in sequence.channels})
        entry = find_bitfile(wanted, counter=self._config is not None)
        if not entry.path:
            raise BitfileError(
                f"Bitfile {entry.name!r} in the library has no `path`, so "
                f"there is nothing to load. Give it the .lvbitx it names."
            )
        self._use(entry, entry.path)
        self._open()

    def _write_program(self, words: list[int]) -> None:
        session = self._require_session()
        fifo = session.fifos[self._gateware.instructions]
        fifo.start()
        fifo.write(words, timeout_ms=5000)
        session.registers[self._gateware.instruction_count].write(len(words))

    async def pulser_on(self) -> None:
        if self._report is None:
            raise RuntimeError(
                f"{self._name} has no sequence loaded — call upload_sequence first"
            )
        session = self._require_session()
        # Looping, so the program free-runs until pulser_off. That is what
        # averaging a pulsed measurement over many sweeps needs: the engine
        # replays while the counter accumulates.
        session.registers[self._gateware.loop].write(True)
        session.registers[self._gateware.run].write(True)
        self._running = True

    async def pulser_off(self) -> None:
        # Safe when nothing is playing: an abort calls this and cannot know
        # how far the run got.
        if self._session is not None:
            self._session.registers[self._gateware.run].write(False)
        self._running = False

    # --- The counter, when the image has one -------------------------------

    async def configure_gates(
        self, bin_width_s: float, record_length_s: float, gates: int
    ) -> GateConfig:
        self._require_counter()
        quantised = self.counter_constraints().quantise({
            BIN_WIDTH: bin_width_s,
            RECORD_LENGTH: record_length_s,
            GATES: gates,
        })
        config = GateConfig(
            bin_width_s=float(quantised[BIN_WIDTH]),
            record_length_s=float(quantised[RECORD_LENGTH]),
            gates=int(quantised[GATES]),
            quantised=quantised,
        )
        session = self._require_session()
        session.registers[self._gateware.bin_ticks].write(
            max(round(config.bin_width_s / self.resolution), 1)
        )
        session.registers[self._gateware.gates].write(config.gates)
        session.registers[self._gateware.bins].write(config.bins)
        self._config = config
        self._elapsed = 0.0
        return config

    async def start_counting(self) -> None:
        if self._config is None:
            raise RuntimeError(
                f"{self._name} has no gates configured — call configure_gates first"
            )
        session = self._require_session()
        session.fifos[self._gateware.counts].start()
        session.registers[self._gateware.counter_run].write(True)
        self._counting = True
        self._started = time.monotonic()

    async def stop_counting(self) -> None:
        if self._session is not None:
            self._session.registers[self._gateware.counter_run].write(False)
        self._counting = False

    async def counter_status(self) -> dict[str, Any]:
        sweeps = 0
        if self._session is not None:
            sweeps = int(self._session.registers[self._gateware.sweeps].read())
        return {"running": self._counting, "sweeps": sweeps}

    async def get_trace(self) -> Dataset:
        """Everything counted so far, as a 2-D `(gate, time bin)` array.

        A `Dataset` with real axes rather than a bare array plus an info
        dict, so the run lands in HDF5 with coordinates nobody had to
        re-derive.
        """
        config = self._config
        if config is None:
            raise RuntimeError(f"{self._name} has no gates configured")
        session = self._require_session()

        wanted = config.gates * config.bins
        read = session.fifos[self._gateware.counts].read(wanted, timeout_ms=5000)
        counts = np.asarray(getattr(read, "data", read), dtype=np.int64)
        counts = _fit(counts, wanted).reshape(config.shape)

        return Dataset(
            arrays={
                "counts": DataArray(
                    name="counts", values=counts, unit="counts",
                    axes=(
                        Axis("gate", np.arange(config.gates, dtype=float),
                             kind="index"),
                        Axis(
                            "time",
                            np.arange(config.bins, dtype=float) * config.bin_width_s,
                            unit="s", kind="time",
                        ),
                    ),
                )
            },
            meta=RunMeta(plan_name=self._name),
        )

    def _require_counter(self) -> None:
        if not self._has_counter():
            raise RuntimeError(
                f"{self._name} is loaded with "
                f"{self._loaded or 'no bitfile'}, which has no counting "
                f"registers. Load an image whose library entry says "
                f"`counter = true`, or bind a separate counter — a Time "
                f"Tagger or an NI DAQ card's counters — for the readouts."
            )

    def _require_session(self) -> Any:
        if self._session is None:
            raise RuntimeError(
                f"{self._name} has no open session. Connect it, and give it a "
                f"bitfile — either pinned with `bitfile`, or by uploading a "
                f"sequence so one is chosen from the library."
            )
        return self._session


def _fit(values: np.ndarray, wanted: int) -> np.ndarray:
    """Exactly `wanted` counts — short reads padded, long ones cut.

    A FIFO read can come back short when the engine has not filled every
    gate yet, and a trace is asked for while a run is still accumulating.
    Reshaping a short read would raise; padding it shows the gates that
    have data and zeros for the rest, which is what a live plot wants.
    """
    if values.size == wanted:
        return values
    if values.size > wanted:
        return values[:wanted]
    return np.concatenate([values, np.zeros(wanted - values.size, dtype=np.int64)])


def _lines(channels: str | tuple[str, ...]) -> tuple[str, ...]:
    """The image's channel list, from a tuple or a comma-separated string.

    A string because that is what fits in a connection form field, the
    same reason `instruments/NI/channels.py` takes one. **Order is bit
    order** — position in this list is the bit set in the instruction
    word's channel mask, so it has to match the order the gateware
    unpacks them in.
    """
    if isinstance(channels, str):
        return tuple(name.strip() for name in channels.split(",") if name.strip())
    return tuple(str(name).strip() for name in channels if str(name).strip())


def _model_choices() -> tuple[str, ...]:
    from labpilot.instruments.NI.bitfiles import load_models

    return tuple(sorted(load_models()))


adapter_registry.register("ni_rseries_fpga", NIRSeriesAdapter)
