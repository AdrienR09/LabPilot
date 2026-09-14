"""What an FPGA bitfile *is*, and which one to load for a given sequence.

## The fact this whole adapter is shaped by

**A bitfile is compiled gateware.** Building one needs LabVIEW FPGA and
the Xilinx toolchain and takes tens of minutes on a desktop. It is not
something a measurement can do between two points of a sweep, and
"convert the pulse sequence into an FPGA program" cannot mean emitting
one at run time.

Qudi's own FPGA pulser is the clearest confirmation. It ships
*pre-compiled* `.bit` files and switches between them to change the
sample rate — `pulsegen_8chnl_500MHz_LX150.bit` or the 950 MHz one, and
nothing in between, because those are the two images someone compiled.

So the division of labour here is:

- the **bitfile** is a fixed pulse-sequencer engine burned into the FPGA.
  It fixes the tick rate, which lines it drives and how deep its
  instruction memory is — that is, it *is* the constraint set;
- the **sequence** is data streamed into that engine: one
  `(channel mask, ticks)` instruction per element, exactly what a
  PulseBlaster or a PulseStreamer consumes.

`upload_sequence` therefore compiles to *instructions*, never to
gateware, and the two ways of choosing a bitfile both make sense:
pin one in the configuration, or let the measurement pick the image whose
engine can play what the sequence asks for.

## A `.lvbitx` describes itself

It is XML with the bitstream base64'd inside it, and the register and
FIFO names are in plain text in that XML. So the adapter can read a
bitfile's whole host interface **with no card present** — which is the
same problem `models.py` solves for DAQmx by hand, except here the answer
is genuinely in a file we already have rather than in a device we cannot
reach.

Parsing is deliberately forgiving: it searches for the elements it knows
and reports what it found rather than insisting on a layout. NI has
changed the schema between LabVIEW versions, and a bitfile this cannot
read is still a bitfile the *driver* can load — so a failed parse costs
the offline checks and nothing else. Opening the card then reconciles
what the file claimed against what the session actually exposes, the same
way `NICardAdapter` reconciles its model table against the live device.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labpilot.core.errors import LabPilotError
from labpilot.instruments._model_table import load_table

__all__ = [
    "BitfileEntry",
    "BitfileError",
    "BitfileInfo",
    "Gateware",
    "RSeriesModel",
    "find_bitfile",
    "find_model",
    "load_bitfiles",
    "load_models",
    "read_bitfile",
]

_PACKAGED = Path(__file__).parent / "rseries.toml"
_USER = Path.home() / ".labpilot" / "config" / "ni_rseries.toml"


class BitfileError(LabPilotError):
    """A bitfile that cannot be read, or that does not fit the sequence."""


# --- What one bitfile offers ------------------------------------------------


@dataclass(frozen=True, slots=True)
class BitfileInfo:
    """A `.lvbitx`'s host interface, read from the file itself."""

    path: Path
    signature: str = ""
    registers: tuple[str, ...] = ()
    """Control and indicator names, as `nifpga` will key `session.registers`."""
    fifos: tuple[str, ...] = ()
    """DMA channel names, as `session.fifos` will key them."""
    parsed: bool = True
    """False when the XML did not have a shape this could read. Everything
    above is then empty and no offline check runs — see the module
    docstring on why that is a degradation and not an error."""
    note: str = ""

    def has(self, *names: str) -> bool:
        """Whether every name is a register or a FIFO of this bitfile.

        True for an unparsed bitfile: nothing is known, so nothing is
        refused. The session reconciles it on connect instead.
        """
        if not self.parsed:
            return True
        known = {*self.registers, *self.fifos}
        return all(name in known for name in names)

    def missing(self, *names: str) -> tuple[str, ...]:
        """Which of these the bitfile does not declare — empty if unparsed."""
        if not self.parsed:
            return ()
        known = {*self.registers, *self.fifos}
        return tuple(name for name in names if name not in known)


def read_bitfile(path: str | Path) -> BitfileInfo:
    """Read a `.lvbitx`'s interface without loading it onto anything.

    Raises only if the file is absent: an unreadable one comes back with
    `parsed=False` and a note, because an image this cannot parse is
    still one `nifpga` may well load.
    """
    path = Path(path).expanduser()
    if not path.exists():
        raise BitfileError(
            f"No bitfile at {path}. Point `bitfile` at the .lvbitx your "
            f"LabVIEW FPGA project built, or leave it empty to let the "
            f"sequence pick one from the library "
            f"(~/.labpilot/config/ni_rseries.toml)."
        )

    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as error:
        return BitfileInfo(
            path=path, parsed=False,
            note=f"not readable as XML ({error}); its interface is unknown "
                 f"until the card is opened",
        )

    signature = ""
    for tag in ("SignatureRegister", "Signature"):
        found = root.find(f".//{tag}")
        if found is not None and found.text:
            signature = found.text.strip()
            break

    registers = _names(root, "Register")
    fifos = _names(root, "Channel") or _names(root, "DmaChannel")
    if not registers and not fifos:
        return BitfileInfo(
            path=path, signature=signature, parsed=False,
            note="its XML has no Register or Channel elements this "
                 "recognises; NI has changed the schema between LabVIEW "
                 "versions, so the interface is left to the live session",
        )
    return BitfileInfo(
        path=path, signature=signature, registers=registers, fifos=fifos
    )


def _names(root: Any, tag: str) -> tuple[str, ...]:
    """Every `<tag>`'s name, however this schema version spells it.

    A `Name` child or a `name` attribute — both appear in the wild — and
    hidden entries are dropped, since `nifpga` does not key them either.
    """
    found: list[str] = []
    for element in root.iter(tag):
        hidden = element.find("Hidden")
        if hidden is not None and (hidden.text or "").strip().lower() == "true":
            continue
        child = element.find("Name")
        name = (child.text if child is not None else None) or element.get("name")
        if name and name.strip():
            found.append(name.strip())
    return tuple(dict.fromkeys(found))


# --- The contract between this adapter and the gateware ---------------------


@dataclass(frozen=True, slots=True)
class Gateware:
    """Which of a bitfile's registers and FIFOs mean what.

    The adapter and the LabVIEW VI have to agree on names, and there is no
    standard to appeal to — so the agreement is written here, defaulted to
    the names the shipped reference VI uses, and every one of them is
    overridable in configuration. A lab with a working pulse-sequencer VI
    of its own renames four strings rather than editing Python.

    The engine this describes is deliberately the simplest thing that can
    play a pulse sequence, and the same one a PulseBlaster has: a list of
    `(channel mask, ticks)` instructions, played in order, optionally
    looping. Everything clever a sequence does — sweeps, alternation —
    is already flattened into that list by `core/pulse/sampling.expand`.
    """

    #: Host -> target, U64: ticks in the low 32 bits, channel mask in the
    #: high 32. One word per element.
    instructions: str = "Instructions"
    #: How many instructions were written, so the engine knows where the
    #: program ends without a sentinel.
    instruction_count: str = "Instruction Count"
    #: Start and stop playing.
    run: str = "Run"
    #: Play the program over and over rather than once. What averaging a
    #: pulsed measurement over many sweeps needs.
    loop: str = "Loop"

    # --- The counter half, when the image has one ---------------------
    counts: str = "Counts"
    """Target -> host, U32: one word per time bin, gate after gate."""
    bin_ticks: str = "Bin Ticks"
    gates: str = "Gates"
    bins: str = "Bins"
    sweeps: str = "Sweeps"
    """Completed passes over every gate — what a pulsed run counts its
    progress in."""
    counter_run: str = "Count"

    @property
    def pulser_names(self) -> tuple[str, ...]:
        return (self.instructions, self.instruction_count, self.run, self.loop)

    @property
    def counter_names(self) -> tuple[str, ...]:
        return (
            self.counts, self.bin_ticks, self.gates, self.bins,
            self.sweeps, self.counter_run,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Gateware:
        """Overrides from configuration, ignoring anything unrecognised."""
        if not data:
            return cls()
        known = set(cls.__slots__)
        return cls(**{k: str(v) for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__slots__}


# --- The cards, and the library of images for them --------------------------


@dataclass(frozen=True, slots=True)
class RSeriesModel:
    """One R-Series card: what it physically has, and how fast it ticks.

    Far less load-bearing than `NICardModel` is for a DAQmx card, and for
    a good reason: on an R-Series card the *bitfile* decides which lines
    are driven, at what derived clock, and how deep the program memory is.
    This is the envelope around that — how many lines exist to be driven
    at all, and the base clock every derived one comes from.

    So an absent field means "unknown, do not validate", exactly as in
    `models.py`, and being wrong here costs a pre-flight check rather than
    a wrong measurement.
    """

    number: str
    family: str = ""
    label: str = ""
    buses: tuple[str, ...] = ()
    fpga: str = ""
    """The part, e.g. "Virtex-5 LX50". Names the compile target a bitfile
    has to have been built for, which is the one mismatch that produces a
    driver error nobody can read."""
    base_clock: float | None = None
    """The onboard oscillator, in Hz. Derived clocks in the gateware are
    multiples of it, so it is what a tick rate has to divide into."""
    dio: int = 0
    ai: int = 0
    ao: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalise_number(self.number))
        object.__setattr__(self, "buses", tuple(self.buses))
        if not self.label:
            object.__setattr__(self, "label", f"NI {self.number}")

    @property
    def stated(self) -> bool:
        """Whether this entry describes any I/O at all. False is the
        escape hatch for a card the table does not list — nothing is
        checked and the bitfile is taken at its word."""
        return bool(self.dio or self.ai or self.ao)

    def product_names(self) -> tuple[str, ...]:
        return tuple(f"{bus}-{self.number}" for bus in self.buses) or (self.number,)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"number": self.number}
        for name in ("family", "label", "buses", "fpga", "base_clock",
                     "dio", "ai", "ao"):
            value = getattr(self, name)
            if value not in (None, (), "", 0):
                data[name] = list(value) if isinstance(value, tuple) else value
        return data


@dataclass(frozen=True, slots=True)
class BitfileEntry:
    """One compiled image in the library, and what its engine can play.

    This is what makes "let the measurement choose the bitfile" possible
    without compiling anything: the lab compiles its images once, says
    here what each one does, and a sequence then selects among them.
    """

    name: str
    path: str = ""
    model: str = ""
    """Which card it was compiled for. A bitfile is built for one part and
    will not load onto another."""
    tick_rate: float | None = None
    """Ticks per second of the engine's clock — the resolution every
    duration is quantised to."""
    channels: tuple[str, ...] = ()
    """The physical lines this image drives, in bit order. Position in
    this tuple *is* the bit in the instruction word's channel mask."""
    memory: int = 0
    """How many instructions its program memory holds. 0 is unstated."""
    counter: bool = False
    """Whether the image also has the counting half — see `Gateware`."""
    gateware: dict[str, str] = None  # type: ignore[assignment]
    """Register/FIFO name overrides for this image, if it does not use the
    reference VI's names."""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "channels", tuple(self.channels))
        object.__setattr__(self, "gateware", dict(self.gateware or {}))

    @property
    def resolution(self) -> float:
        """Seconds per tick — what a duration is rounded to."""
        return 1.0 / self.tick_rate if self.tick_rate else 0.0

    def fits(self, wanted: int, tick_rate: float | None = None) -> bool:
        """Whether this image can drive `wanted` channels at that rate."""
        if wanted > len(self.channels):
            return False
        return tick_rate is None or self.tick_rate == tick_rate


#: Every R-Series number is four digits followed by an R, so the digits
#: alone are the key: `PXIe-7856R`, `7856R` and `7856` are one entry, and
#: neither the bus prefix nor the suffix is ever a reason to miss a card.
_NUMBER = re.compile(r"(\d{4})")


def normalise_number(name: str) -> str:
    """The bare model number in whatever someone typed — `"PXIe-7856R"`,
    `"7856r"` and `"7856"` are one entry."""
    match = _NUMBER.search(str(name))
    return match.group(1).lower() if match else str(name).strip().lower()


_models: dict[tuple[Path, Path], dict[str, RSeriesModel]] = {}
_library: dict[tuple[Path, Path], dict[str, BitfileEntry]] = {}


def load_models(
    packaged: Path | None = None, user: Path | None = None, *, refresh: bool = False
) -> dict[str, RSeriesModel]:
    """Every known R-Series card, keyed by number."""
    key = (packaged or _PACKAGED, user or _USER)
    if refresh:
        _models.pop(key, None)
    if key not in _models:
        _models[key] = {
            number: RSeriesModel(**entry)
            for number, entry in load_table(
                key[0], key[1], section="card", key="number",
                normalise=normalise_number,
            ).items()
        }
    return _models[key]


def load_bitfiles(
    packaged: Path | None = None, user: Path | None = None, *, refresh: bool = False
) -> dict[str, BitfileEntry]:
    """The lab's compiled images, keyed by name.

    Packaged plus the user's file merged over it, the same rule every
    model table here follows — and this one is *expected* to be empty out
    of the box, because a bitfile is built from a LabVIEW project nobody
    can ship for you. What ships is the shape of the entry and the
    reference VI's register names.
    """
    key = (packaged or _PACKAGED, user or _USER)
    if refresh:
        _library.pop(key, None)
    if key not in _library:
        _library[key] = {
            name: BitfileEntry(**entry)
            for name, entry in load_table(
                key[0], key[1], section="bitfile", key="name",
                normalise=lambda v: str(v).strip().lower(),
            ).items()
        }
    return _library[key]


def find_model(name: str, models: dict[str, RSeriesModel] | None = None) -> RSeriesModel:
    """The model for a product name, however it was spelled."""
    table = models if models is not None else load_models()
    number = normalise_number(name)
    if number in table:
        return table[number]
    raise BitfileError(
        f"No R-Series model {name!r} in the table (read as {number!r}). "
        f"Known: {', '.join(sorted(table))}. Either set the model to "
        f"'generic', which validates nothing and leaves the checking to "
        f"the bitfile, or add the card to "
        f"~/.labpilot/config/ni_rseries.toml."
    )


def find_bitfile(
    channels: int,
    *,
    tick_rate: float | None = None,
    counter: bool = False,
    library: dict[str, BitfileEntry] | None = None,
) -> BitfileEntry:
    """The image whose engine can play what is being asked for.

    This is the half of the adapter that lets a *measurement* choose the
    bitfile: it knows the sequence needs five channels and a counter, and
    the library says which compiled image offers that. Nothing is
    compiled — the choice is among images the lab already built.

    The narrowest fit wins, so a five-channel sequence loads the
    eight-channel image rather than the thirty-two-channel one when both
    are present and both would work.
    """
    table = library if library is not None else load_bitfiles()
    fitting = [
        entry for entry in table.values()
        if entry.fits(channels, tick_rate) and (entry.counter or not counter)
    ]
    if not fitting:
        raise BitfileError(
            f"No bitfile in the library drives {channels} channel(s)"
            + (f" at {tick_rate / 1e6:.6g} MHz" if tick_rate else "")
            + (" with a counter" if counter else "")
            + ". "
            + (
                f"It holds: {', '.join(sorted(table))}. "
                if table else
                "It is empty, which is the state a fresh install is in — a "
                "bitfile is compiled from a LabVIEW FPGA project and cannot "
                "be shipped for you. "
            )
            + "Either add the image you compiled to "
            "~/.labpilot/config/ni_rseries.toml, or name one directly with "
            "the adapter's `bitfile` setting."
        )
    return min(fitting, key=lambda entry: (len(entry.channels), entry.name))
