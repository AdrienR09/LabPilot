"""What a particular NI card *is* — its ports, and what they can do.

## Why this file exists at all

Four frameworks were read before writing it — qudi (`ni_x_series/`),
pylablib (`devices/NI/daq.py`), pyMoDAQ, and Micro-Manager's DAQ adapter —
and **none of them contains a table of NI card models.** Every one of them
asks the driver at run time: qudi reads `co_physical_chans`, `terminals`,
`ai_max_multi_chan_rate` and `ci_max_timebase` off a live
`nidaqmx.system.Device`; pylablib reads `product_type` and nothing else.

That is the right thing to do *when a card is present*, and it is why
none of them can help you the rest of the time. Configuring which terminal
the APD is wired to, which two AO lines drive the galvos, and whether the
card you are about to buy even has four counters is work you do at a desk,
with no card in the machine — and NI-DAQmx does not exist for macOS at
all, so on this development machine there is no card that could answer.

So this is the piece the references leave out: a static, editable
inventory of card models, used to lay out and validate a configuration
offline. It is deliberately *not* authoritative. When a real card is
opened, `NICardAdapter` asks DAQmx and the device wins — see
`reconcile()`, which reports every disagreement rather than hiding it,
because a wrong table entry that silently overrides a real device is worse
than no table at all.

## Where the numbers come from, and how wrong ones get fixed

From NI's published specifications for each family, entered by hand. Three
things keep that honest:

- a field nobody was sure of is **left out**, and an absent field means
  "unknown, do not validate" rather than a plausible-looking guess;
- `reconcile()` compares the table with the live device on connect;
- `scripts/ni_probe.py` prints a connected card's real inventory as a TOML
  block, so correcting an entry — or adding a model that was never in the
  file — is a copy and paste rather than a code change.

## One model, many product names

`PCIe-6363`, `PXIe-6363` and `USB-6363` are the same card on three buses,
and DAQmx reports whichever one you have as `product_type`. So an entry is
keyed on the **number** and matching ignores the bus prefix entirely: a
bus this file does not list is never a reason to refuse a card, because
being wrong about which buses NI shipped is much more likely than the card
in front of you not existing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labpilot.core.device.constraints import Constraints, ScalarConstraint
from labpilot.instruments._model_table import load_table

__all__ = [
    "AI",
    "AO",
    "CTR",
    "DIO",
    "PFI",
    "NICardModel",
    "find_model",
    "load_models",
    "model_numbers",
    "normalise_number",
]

#: Terminal kinds a model can offer. The strings are the ones used in
#: channel specs, adapter errors and the model file alike.
AI = "ai"
AO = "ao"
CTR = "ctr"
PFI = "pfi"
DIO = "dio"

_PACKAGED = Path(__file__).parent / "models.toml"
_USER = Path.home() / ".labpilot" / "config" / "ni_models.toml"

#: `PCIe-6363`, `pxie6363`, `Dev1: USB-6363` — anything with the number in it.
_NUMBER = re.compile(r"(\d{4}[A-Za-z]?)")


def normalise_number(name: str) -> str:
    """The bare model number in whatever someone typed.

    `"PCIe-6363"`, `"pcie-6363"` and `"6363"` all give `"6363"`. Returns
    the input lowercased and stripped if it holds no number at all, so the
    caller's error message can quote what was actually asked for.
    """
    match = _NUMBER.search(str(name))
    return match.group(1).lower() if match else str(name).strip().lower()


@dataclass(frozen=True, slots=True)
class NICardModel:
    """One NI DAQ card model: how many of each port, and their limits.

    Counts are what generate terminal names, so they must be right or a
    configuration cannot be validated at all. Rates and ranges only feed
    pre-flight checks, so `None` — "not stated" — is a legitimate value
    and means the check is skipped.
    """

    number: str
    family: str = ""
    label: str = ""
    buses: tuple[str, ...] = ()

    ai: int = 0
    ai_rate: float | None = None
    """Aggregate sample rate in S/s: the whole card's budget for a
    multiplexed model, per channel for a simultaneous-sampling one."""
    ai_simultaneous: bool = False
    ai_bits: int | None = None
    ai_ranges: tuple[float, ...] = ()
    """The ± voltage ranges the input amplifier offers, largest last."""

    ao: int = 0
    ao_rate: float | None = None
    """`None` means software-timed only — a USB-6008's outputs update when
    you write them and cannot follow a clock, which is the difference
    between a card that can scan and one that cannot."""
    ao_range: float | None = None

    dio: int = 0
    dio_ports: tuple[int, ...] = ()
    pfi: int | None = None
    counters: int = 0
    counter_bits: int | None = None
    timebase: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalise_number(self.number))
        object.__setattr__(self, "buses", tuple(self.buses))
        object.__setattr__(self, "ai_ranges", tuple(float(r) for r in self.ai_ranges))
        object.__setattr__(self, "dio_ports", tuple(int(p) for p in self.dio_ports) or _ports(self.dio))
        if not self.label:
            object.__setattr__(self, "label", f"NI {self.number}")

    # --- What it offers ---------------------------------------------------

    def product_names(self) -> tuple[str, ...]:
        """Every name DAQmx might report this card as, e.g.
        `("PCIe-6363", "PXIe-6363", "USB-6363")`."""
        return tuple(f"{bus}-{self.number}" for bus in self.buses) or (self.number,)

    def terminals(self, kind: str) -> tuple[str, ...]:
        """Every terminal of one kind, in DAQmx's own naming.

        Digital lines come back as `port0/line0`; everything else is the
        familiar `ai0` / `ao1` / `ctr3` / `pfi8`. All lowercase, which is
        what `channels.py` canonicalises to — DAQmx itself is
        case-insensitive.
        """
        if kind == AI:
            return tuple(f"ai{i}" for i in range(self.ai))
        if kind == AO:
            return tuple(f"ao{i}" for i in range(self.ao))
        if kind == CTR:
            return tuple(f"ctr{i}" for i in range(self.counters))
        if kind == PFI:
            return () if self.pfi is None else tuple(f"pfi{i}" for i in range(self.pfi))
        if kind == DIO:
            return tuple(
                f"port{port}/line{line}"
                for port, lines in enumerate(self.dio_ports)
                for line in range(lines)
            )
        raise ValueError(f"No such terminal kind: {kind!r}")

    @property
    def stated(self) -> bool:
        """Whether this entry describes any ports at all.

        An entry that describes none is not a card with no ports — it is
        the escape hatch for a card this table does not list. Nothing is
        checked against it offline; NI-DAQmx does the checking when the
        card is opened, which it would have done anyway. That keeps an
        unlisted model from being a dead end without letting a guessed
        inventory reject a working rig.
        """
        return bool(self.ai or self.ao or self.counters or self.dio)

    def knows(self, kind: str) -> bool:
        """Whether this model states its inventory of `kind`.

        A card with `pfi` unstated is not a card with no PFI lines; it is
        one whose count nobody entered, and a terminal on it must be taken
        on trust rather than rejected.
        """
        if kind == PFI:
            return self.pfi is not None
        return bool(self.terminals(kind))

    @property
    def timed_output(self) -> bool:
        """Whether the analog outputs can follow a hardware clock — the
        precondition for `hardware_scan`."""
        return self.ao > 0 and self.ao_rate is not None

    @property
    def voltage_range(self) -> tuple[float, float]:
        """The widest input range, as `(min, max)`. `(-10, 10)` when the
        model does not state its ranges, which is the near-universal
        default and the one every existing adapter here assumed."""
        widest = max(self.ai_ranges, default=10.0)
        return (-widest, widest)

    # --- Pre-flight checks ------------------------------------------------

    def constraints(self) -> Constraints:
        """What this card will do with a requested rate or range.

        Only what the model actually states: an unstated rate contributes
        no constraint, so `quantise` passes the request through untouched
        rather than clipping it to a number nobody verified.
        """
        scalars: list[ScalarConstraint] = []
        if self.ai_rate is not None:
            scalars.append(
                ScalarConstraint("ai_rate", bounds=(None, self.ai_rate), unit="S/s")
            )
        if self.ao_rate is not None:
            scalars.append(
                ScalarConstraint("ao_rate", bounds=(None, self.ao_rate), unit="S/s")
            )
        if self.ai_ranges:
            scalars.append(
                ScalarConstraint("voltage_range", allowed=self.ai_ranges, unit="V")
            )
        if self.timebase is not None:
            scalars.append(
                ScalarConstraint("counter_timebase", bounds=(None, self.timebase), unit="Hz")
            )
        return Constraints(scalars=tuple(scalars), extra={"model": self.number})

    def to_dict(self) -> dict[str, Any]:
        """The TOML shape, for `scripts/ni_probe.py` and round-trip tests."""
        data: dict[str, Any] = {"number": self.number, "family": self.family}
        for name in (
            "label", "buses", "ai", "ai_rate", "ai_simultaneous", "ai_bits",
            "ai_ranges", "ao", "ao_rate", "ao_range", "dio", "dio_ports",
            "pfi", "counters", "counter_bits", "timebase", "notes",
        ):
            value = getattr(self, name)
            if value not in (None, (), "", 0, False):
                data[name] = list(value) if isinstance(value, tuple) else value
        return data


def _ports(dio: int) -> tuple[int, ...]:
    """How `dio` digital lines are grouped into ports.

    NI's own layouts, which are not a straight division into eights: an
    X- or M-Series card with 48 lines puts 32 of them on port 0 (the
    hardware-timed, correlated port) and eight each on ports 1 and 2, and
    the 24-line version has eight on each of the three.
    """
    layouts = {48: (32, 8, 8), 24: (8, 8, 8), 13: (8, 4, 1), 12: (8, 4)}
    if dio in layouts:
        return layouts[dio]
    full, rest = divmod(dio, 8)
    return tuple([8] * full + ([rest] if rest else []))


# --- The table ---------------------------------------------------------------


_cache: dict[tuple[Path, Path], dict[str, NICardModel]] = {}


def load_models(
    packaged: Path | None = None, user: Path | None = None, *, refresh: bool = False
) -> dict[str, NICardModel]:
    """Every known card model, keyed by number.

    The packaged file is the base and `~/.labpilot/config/ni_models.toml`
    is merged over it — see `instruments/_model_table.py`, which holds
    that rule for every device family that has a model table, and the bug
    it exists to prevent.
    """
    key = (packaged or _PACKAGED, user or _USER)
    if refresh:
        _cache.pop(key, None)
    if key in _cache:
        return _cache[key]

    models = {
        number: NICardModel(**entry)
        for number, entry in load_table(
            key[0], key[1], section="card", key="number", normalise=normalise_number
        ).items()
    }
    _cache[key] = models
    return models


def find_model(name: str, models: dict[str, NICardModel] | None = None) -> NICardModel:
    """The model for a product name, however it was spelled.

    Raises `KeyError` naming the closest few, because the alternative —
    quietly falling back to a generic card — would validate a terminal
    that does not exist and fail later, on hardware, with a DAQmx error
    number instead of a sentence.
    """
    table = models if models is not None else load_models()
    number = normalise_number(name)
    if number in table:
        return table[number]

    near = sorted(n for n in table if n[:2] == number[:2]) or sorted(table)
    raise KeyError(
        f"No NI card model {name!r} in the table (read as {number!r}). "
        f"Nearest: {', '.join(near[:6])}. Either set the model to 'generic', "
        f"which validates no terminals and leaves the checking to NI-DAQmx, "
        f"or add the card to ~/.labpilot/config/ni_models.toml — "
        f"`python scripts/ni_probe.py` prints the block for one that is "
        f"plugged in."
    )


def model_numbers() -> tuple[str, ...]:
    """Every model number in the table, sorted — for a settings dropdown."""
    return tuple(sorted(load_models()))
