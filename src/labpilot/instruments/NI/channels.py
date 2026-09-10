"""Which terminal does what — the per-rig half of an NI card's config.

A card model says a 6363 has `ai0..ai31`, `ao0..ao3`, four counters and
sixteen PFI lines. It cannot say that `ao0` drives the galvo's X axis and
`ctr0` counts the APD wired to `pfi8`. That is a fact about *this* rig,
changes when someone re-plugs a BNC, and is what has to be written down.

## Names are the rig's, terminals are the card's

`read()` comes back as `{"apd": 1.2e5, "photodiode": 0.41}`, not
`{"ctr0": ..., "ai0": ...}`. The indirection is the whole point: a
workflow binds to `apd`, and moving the APD from `pfi8` to `pfi12` is one
character in a config file rather than an edit to every script. It is the
same reasoning that keeps a `PulseSequence`'s channels symbolic.

## Two spellings, one meaning

A list of records for a config file or the console:

    channels=[{"name": "x", "kind": "ao", "terminal": "ao0"},
              {"name": "apd", "kind": "ci", "terminal": "ctr0",
               "source": "pfi8"}]

and a one-line string for the connect form, which has nowhere to put a
table:

    channels="x=ao0, y=ao1, apd=ctr0/pfi8, pd=ai0, shutter=do:port0/line0"

The kind is inferred from the terminal — `ai0` can only be an input,
`ctr0/pfi8` can only be a counter — except for a digital line, where
`port0/line0` is equally plausibly an input or an output. Guessing there
would mean a shutter that silently never opens, so it is the one case that
must be spelled out: `do:port0/line0`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from labpilot.instruments.NI.models import AI, AO, CTR, DIO, PFI, NICardModel

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "KINDS",
    "Channel",
    "parse_channels",
    "validate_channels",
]

#: What a configured channel can be. The first two are analog in/out, then
#: counter input (edge counting), digital in/out, and counter output (a
#: pulse train from one of the card's counters).
KINDS = ("ai", "ao", "ci", "di", "do", "co")

_READABLE = ("ai", "ci", "di")
_WRITABLE = ("ao", "do")

_TERMINAL = re.compile(r"^(ai|ao|ctr)(\d+)$")
_LINE = re.compile(r"^port(\d+)/line(\d+)$")
_PFI = re.compile(r"^pfi(\d+)$")


@dataclass(frozen=True, slots=True)
class Channel:
    """One rig-level name, wired to one terminal of the card."""

    name: str
    kind: str
    terminal: str
    source: str = ""
    """The input terminal a counter counts edges on (`pfi8`), or the one a
    counter output drives. Empty for everything else."""
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A channel needs a name")
        if self.kind not in KINDS:
            raise ValueError(
                f"Channel {self.name!r} has kind {self.kind!r}; "
                f"expected one of {', '.join(KINDS)}"
            )
        object.__setattr__(self, "terminal", _canonical(self.terminal))
        object.__setattr__(self, "source", _canonical(self.source))
        if not self.unit:
            object.__setattr__(self, "unit", _UNITS[self.kind])

    @property
    def readable(self) -> bool:
        return self.kind in _READABLE

    @property
    def settable(self) -> bool:
        return self.kind in _WRITABLE

    @property
    def dtype(self) -> str:
        return "bool" if self.kind in ("di", "do") else "f8"

    @property
    def limits(self) -> tuple[float | None, float | None] | None:
        if self.minimum is None and self.maximum is None:
            return None
        return (self.minimum, self.maximum)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name, "kind": self.kind, "terminal": self.terminal
        }
        if self.source:
            data["source"] = self.source
        if self.minimum is not None:
            data["min"] = self.minimum
        if self.maximum is not None:
            data["max"] = self.maximum
        return data

    def __str__(self) -> str:
        wired = f"{self.terminal}/{self.source}" if self.source else self.terminal
        return f"{self.name}={self.kind}:{wired}"


_UNITS = {"ai": "V", "ao": "V", "ci": "counts/s", "di": "", "do": "", "co": "Hz"}


def _canonical(terminal: str) -> str:
    """DAQmx is case-insensitive and tolerates a leading device name; this
    is the one spelling everything downstream compares against."""
    text = str(terminal or "").strip().lstrip("/").lower()
    # "dev1/ai0" -> "ai0". A digital line is "port0/line0", which has a
    # slash of its own, so only a leading device segment is dropped.
    if "/" in text and not text.startswith(("port", "ctr", "ai", "ao", "pfi")):
        text = text.split("/", 1)[1]
    return text


# --- Parsing -----------------------------------------------------------------


def parse_channels(spec: Any) -> tuple[Channel, ...]:
    """Channels from whichever spelling was given.

    Accepts the string form, a list of dicts, a list of `Channel`s, or a
    plain `{name: terminal}` mapping — the last because
    `{"x": "ao0", "y": "ao1"}` is what the adapter this replaces took, and
    a config written against it should keep working.
    """
    if spec is None or spec == "" or spec == () or spec == []:
        return ()
    if isinstance(spec, Channel):
        return (spec,)
    if isinstance(spec, str):
        return tuple(_parse_one(part) for part in _split(spec))
    if isinstance(spec, dict):
        return tuple(
            _parse_one(f"{name}={value}") if isinstance(value, str)
            else _from_dict({**value, "name": name})
            for name, value in spec.items()
        )
    parsed: list[Channel] = []
    for item in spec:
        if isinstance(item, Channel):
            parsed.append(item)
        elif isinstance(item, str):
            parsed.append(_parse_one(item))
        else:
            parsed.append(_from_dict(item))
    return tuple(parsed)


def _split(spec: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]", spec) if part.strip()]


def _from_dict(item: dict[str, Any]) -> Channel:
    name = str(item.get("name") or "")
    terminal = str(item.get("terminal") or "")
    kind = str(item.get("kind") or "")
    source = str(item.get("source") or "")
    if not kind:
        kind, terminal, source = _infer(name, terminal or source)
    return Channel(
        name=name,
        kind=kind,
        terminal=terminal,
        source=source or str(item.get("source") or ""),
        minimum=_number(item.get("min", item.get("minimum"))),
        maximum=_number(item.get("max", item.get("maximum"))),
        unit=str(item.get("unit") or ""),
    )


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _parse_one(text: str) -> Channel:
    """`"apd=ci:ctr0/pfi8"` and everything shorter that means the same."""
    if "=" not in text:
        raise ValueError(
            f"Channel {text!r} has no name — write it as "
            f"name=terminal, e.g. 'apd=ctr0/pfi8'"
        )
    name, _, wiring = text.partition("=")
    kind, terminal, source = _infer(name.strip(), wiring.strip())
    return Channel(name=name.strip(), kind=kind, terminal=terminal, source=source)


def _infer(name: str, wiring: str) -> tuple[str, str, str]:
    """`(kind, terminal, source)` from `"ci:ctr0/pfi8"` or just
    `"ctr0/pfi8"`."""
    kind = ""
    if ":" in wiring:
        prefix, _, wiring = wiring.partition(":")
        kind = prefix.strip().lower()
        if kind not in KINDS:
            raise ValueError(
                f"Channel {name!r} names kind {kind!r}; "
                f"expected one of {', '.join(KINDS)}"
            )

    wiring = wiring.strip()
    source = ""
    if wiring.lower().startswith("ctr") and "/" in wiring:
        wiring, _, source = wiring.partition("/")

    terminal = _canonical(wiring)
    if kind:
        return kind, terminal, _canonical(source)

    if terminal.startswith("ai"):
        return "ai", terminal, ""
    if terminal.startswith("ao"):
        return "ao", terminal, ""
    if terminal.startswith("ctr"):
        return "ci", terminal, _canonical(source)
    if _LINE.match(terminal):
        raise ValueError(
            f"Channel {name!r} is wired to the digital line {terminal!r}, but a "
            f"line can be an input or an output and guessing wrong means a "
            f"shutter that never opens — write 'do:{terminal}' to drive it or "
            f"'di:{terminal}' to read it"
        )
    raise ValueError(
        f"Channel {name!r} is wired to {wiring!r}, which is not a terminal this "
        f"understands. Expected ai0, ao0, ctr0/pfi8, or port0/line0 with a "
        f"'di:'/'do:' prefix"
    )


# --- Validation --------------------------------------------------------------


def validate_channels(
    channels: Iterable[Channel], model: NICardModel
) -> tuple[Channel, ...]:
    """Every channel checked against what the card actually has.

    Raises on the first problem, naming the terminals that *do* exist —
    the error is read by someone who mistyped `ai32` on a 32-channel card
    and needs to be told it counts from zero, not handed a DAQmx status
    code three minutes later when the run starts.

    A model that does not state its inventory of some kind (`pfi` is the
    usual one) does not police that kind: see `NICardModel.knows`.
    """
    checked = tuple(channels)
    _no_duplicates(checked)

    for channel in checked:
        _check_terminal(channel, model)
        _check_source(channel, model)
        _check_range(channel, model)
    return checked


def _no_duplicates(channels: Sequence[Channel]) -> None:
    by_name: dict[str, Channel] = {}
    by_terminal: dict[tuple[str, str], Channel] = {}
    for channel in channels:
        if channel.name in by_name:
            raise ValueError(
                f"Two channels are both named {channel.name!r} "
                f"({by_name[channel.name]} and {channel})"
            )
        by_name[channel.name] = channel
        # A terminal may legitimately appear twice across kinds (a counter
        # and its source), so the key is the pair.
        key = (channel.kind, channel.terminal)
        if key in by_terminal:
            raise ValueError(
                f"{channel.terminal!r} is used by both "
                f"{by_terminal[key].name!r} and {channel.name!r}"
            )
        by_terminal[key] = channel


def _check_terminal(channel: Channel, model: NICardModel) -> None:
    kind = {"ai": AI, "ao": AO, "ci": CTR, "co": CTR, "di": DIO, "do": DIO}[channel.kind]
    if not model.knows(kind):
        if kind in (AI, AO, CTR, DIO):
            raise ValueError(
                f"{channel.name!r} needs {_describe(kind)}, and the "
                f"{model.number} has none"
            )
        return
    available = model.terminals(kind)
    if channel.terminal not in available:
        raise ValueError(
            f"{channel.name!r} is wired to {channel.terminal!r}, which the "
            f"{model.number} does not have — it offers {_summarise(available)}"
        )


def _check_source(channel: Channel, model: NICardModel) -> None:
    if channel.kind not in ("ci", "co"):
        return
    if not channel.source:
        if channel.kind == "ci":
            raise ValueError(
                f"Counter channel {channel.name!r} does not say which terminal "
                f"it counts — write it as '{channel.name}={channel.terminal}/pfi8'"
            )
        return
    if not _PFI.match(channel.source) and not _LINE.match(channel.source):
        raise ValueError(
            f"{channel.name!r} counts edges on {channel.source!r}, which is not "
            f"an input terminal — expected a PFI line such as 'pfi8'"
        )
    if model.knows(PFI) and _PFI.match(channel.source):
        available = model.terminals(PFI)
        if channel.source not in available:
            raise ValueError(
                f"{channel.name!r} counts edges on {channel.source!r}, which the "
                f"{model.number} does not have — it offers {_summarise(available)}"
            )


def _check_range(channel: Channel, model: NICardModel) -> None:
    if channel.kind not in ("ai", "ao") or channel.limits is None:
        return
    low, high = channel.limits
    widest = model.ao_range if channel.kind == "ao" else max(model.ai_ranges, default=None)
    if widest is None:
        return
    if (low is not None and low < -widest) or (high is not None and high > widest):
        raise ValueError(
            f"{channel.name!r} asks for {low}..{high} V, outside the "
            f"{model.number}'s ±{widest} V"
        )


def _describe(kind: str) -> str:
    return {
        AI: "an analog input", AO: "an analog output",
        CTR: "a counter", DIO: "a digital line",
    }[kind]


def _summarise(terminals: Sequence[str]) -> str:
    """`ai0..ai31` rather than thirty-two names in an error message."""
    if len(terminals) <= 4:
        return ", ".join(terminals)
    return f"{terminals[0]}..{terminals[-1]} ({len(terminals)} of them)"
