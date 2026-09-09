"""A sequence as an editable table — the columns, and what a cell holds.

This is the model behind the block editor: one row per `PulseElement`, one
column per channel, plus length and increment. Qudi's `pulsed_maingui.py`
builds the same table and is the reference for the one idea worth taking
whole — **the columns are not fixed**. They come from the channels in play,
and an analog channel contributes a shape column plus one column per that
shape's parameters, so the table grows a "Frequency (Hz)" column the moment
a `Sin` appears in it.

Kept out of the Qt file for the usual reason: the column rule and the
cell-to-channel mapping are the fiddly parts, they are pure data, and
`tests/` is Qt-free.

## Where the columns come from, and where they must not

From the **rig profile's symbolic channels**, and from the shapes the rows
actually use. Never from a connected pulser: an offline editor has none to
ask, and a sequence that took its channels from one is a sequence tied to
one rig's wiring — which is what symbolic channels exist to prevent. Qudi
takes its columns from the pulser's `activation_config`, which is the one
place its editor and this one genuinely disagree.

## The table form is the file form

A row *is* an element's entry in `PulseSequence.to_dict()`. There is no
second representation to keep in step, which is what lets a generated
sequence be loaded into the table, hand-edited, and saved back without
passing through anything lossy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from labpilot.core.pulse.sequence import PulseSequence, SequenceError
from labpilot.core.pulse.shapes import SHAPES

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "ANALOG",
    "DIGITAL",
    "INCREMENT",
    "LENGTH",
    "NAME",
    "SHAPE",
    "Column",
    "blank_element",
    "cell",
    "columns",
    "sequence_from_table",
    "set_cell",
    "table_from_sequence",
]

NAME = "name"
LENGTH = "length"
INCREMENT = "increment"
DIGITAL = "digital"
ANALOG = "analog"
SHAPE = "shape"

#: Channels a rig almost always has, in the order a physicist reads them.
#: Anything else follows, alphabetically, so the column order is stable
#: across edits rather than following dict insertion.
_PREFERRED = ("laser", "green", "mw", "microwave", "gate", "trigger")


@dataclass(frozen=True, slots=True)
class Column:
    """One column of the block editor.

    `key` is what `cell`/`set_cell` address it by; `channel` and `param`
    say which part of the row it reaches, so the Qt table needs no
    knowledge of the element's dict shape.
    """

    key: str
    label: str
    kind: str
    """One of NAME, LENGTH, INCREMENT, DIGITAL, ANALOG, SHAPE."""
    channel: str = ""
    param: str = ""
    unit: str = ""

    @property
    def editable_as_number(self) -> bool:
        return self.kind in (LENGTH, INCREMENT, ANALOG)


def _ordered(channels: Iterable[str]) -> list[str]:
    names = set(channels)
    first = [name for name in _PREFERRED if name in names]
    return first + sorted(names - set(first))


def columns(
    elements: Sequence[Mapping[str, Any]], channels: Iterable[str] = ()
) -> tuple[Column, ...]:
    """The columns this block needs, given its rows and the rig's channels.

    Dynamic in two ways, both deliberate:

    - A channel the rig declares gets a column even when no element uses
      it yet, so a new sequence starts with somewhere to put the laser.
    - An analog channel gets a shape column plus one column per parameter
      of every shape present on it. Mixed shapes on one channel are legal
      and produce the union, with a cell blank where its row's shape does
      not declare that parameter — which is what stops a Gauss row and a
      Sin row from having to agree.
    """
    declared = _ordered(channels)
    used = _ordered({name for element in elements for name in element.get("channels", {})})
    every = declared + [name for name in used if name not in declared]

    analog_shapes: dict[str, list[str]] = {}
    for element in elements:
        for name, value in (element.get("channels") or {}).items():
            if isinstance(value, dict) and value.get("shape"):
                shapes = analog_shapes.setdefault(name, [])
                if value["shape"] not in shapes:
                    shapes.append(value["shape"])

    built: list[Column] = [
        Column(NAME, "Name", NAME),
        Column(LENGTH, "Length", LENGTH, unit="s"),
        Column(INCREMENT, "Increment", INCREMENT, unit="s"),
    ]
    for name in every:
        if name not in analog_shapes:
            built.append(Column(name, name, DIGITAL, channel=name))
            continue

        built.append(Column(f"{name}.shape", f"{name} shape", SHAPE, channel=name))
        for parameter in _analog_params(analog_shapes[name]):
            built.append(
                Column(
                    f"{name}.{parameter.name}",
                    f"{name} {parameter.name.replace('_', ' ')}",
                    ANALOG,
                    channel=name,
                    param=parameter.name,
                    unit=parameter.unit,
                )
            )
    return tuple(built)


def _analog_params(shapes: Iterable[str]) -> list[Any]:
    """Every parameter of every shape used on one channel, in declaration
    order, without duplicates."""
    seen: dict[str, Any] = {}
    for name in shapes:
        cls = SHAPES.get(name)
        for parameter in getattr(cls, "params", ()) if cls else ():
            seen.setdefault(parameter.name, parameter)
    return list(seen.values())


def blank_element(channels: Iterable[str] = ()) -> dict[str, Any]:
    """A new row: 100 ns, no increment, every declared channel low.

    Low rather than absent, so the new row's cells are visibly off instead
    of empty — an element that names no channel is legal in the model and
    unreadable in a table.
    """
    return {
        "name": "",
        "duration": 100e-9,
        "increment": 0.0,
        "channels": dict.fromkeys(_ordered(channels), False),
    }


def cell(element: Mapping[str, Any], column: Column) -> Any:
    """What `column` shows for this row.

    `None` means "this cell does not apply" — an analog parameter column
    for a row whose shape does not declare it.
    """
    if column.kind == NAME:
        return element.get("name", "")
    if column.kind == LENGTH:
        return float(element.get("duration", 0.0))
    if column.kind == INCREMENT:
        return float(element.get("increment", 0.0))

    value = (element.get("channels") or {}).get(column.channel)
    if column.kind == DIGITAL:
        return value is True
    if column.kind == SHAPE:
        return value.get("shape", "") if isinstance(value, dict) else ""
    if isinstance(value, dict) and column.param in value:
        return value[column.param]
    return None


def set_cell(element: Mapping[str, Any], column: Column, value: Any) -> dict[str, Any]:
    """`element` with one cell changed — a new dict, never edited in place.

    Changing a shape rebuilds that channel from the new shape's defaults
    rather than carrying the old one's parameters across. A `Gauss` that
    inherited a `Chirp`'s `start_frequency` would be a silent wrong
    answer; a shape's parameters belong to the shape.
    """
    updated = {
        "name": element.get("name", ""),
        "duration": float(element.get("duration", 0.0)),
        "increment": float(element.get("increment", 0.0)),
        "channels": dict(element.get("channels") or {}),
    }

    if column.kind == NAME:
        updated["name"] = str(value)
        return updated
    if column.kind == LENGTH:
        updated["duration"] = max(float(value), 0.0)
        return updated
    if column.kind == INCREMENT:
        updated["increment"] = float(value)
        return updated

    channels = updated["channels"]
    if column.kind == DIGITAL:
        channels[column.channel] = bool(value)
        return updated

    if column.kind == SHAPE:
        name = str(value)
        if not name or name.lower() in ("", "off", "none"):
            channels[column.channel] = False
        elif name not in SHAPES:
            raise SequenceError(
                f"Unknown pulse shape {name!r} — known shapes are "
                f"{', '.join(sorted(SHAPES))}"
            )
        else:
            defaults = SHAPES[name]()
            channels[column.channel] = {
                "shape": name,
                **{p.name: getattr(defaults, p.name) for p in SHAPES[name].params},
            }
        return updated

    current = channels.get(column.channel)
    if isinstance(current, dict):
        channels[column.channel] = {**current, column.param: float(value)}
    return updated


def table_from_sequence(sequence: PulseSequence) -> list[dict[str, Any]]:
    """A sequence as blocks of editable rows.

    The rows are its serialised form verbatim — the same dicts that go
    into the file — so a generated sequence can be loaded, hand-edited and
    saved back without passing through a second representation.
    """
    return sequence.to_dict()["blocks"]


def sequence_from_table(
    blocks: Sequence[Mapping[str, Any]],
    name: str,
    *,
    sweep: Mapping[str, Any] | None = None,
    laser_channel: str = "laser",
    gate_channel: str | None = "gate",
    alternating: bool = False,
    rotating_frame: bool = True,
    description: str = "",
    validate: bool = True,
) -> PulseSequence:
    """Build a sequence from edited rows, and check it can be played.

    `validate=False` is for a table mid-edit: a half-built block has no
    readout yet and refusing to render it would make the editor unusable.
    Saving always validates.
    """
    if not blocks:
        raise SequenceError(f"Sequence {name!r} has no blocks to build from")

    sequence = PulseSequence.from_dict(
        {
            "name": name,
            "blocks": [
                {
                    "name": block.get("name") or f"block_{index}",
                    "repetitions": int(block.get("repetitions", 1) or 1),
                    "elements": list(block.get("elements") or ()),
                }
                for index, block in enumerate(blocks)
            ],
            "sweep": dict(sweep) if sweep else None,
            "laser_channel": laser_channel,
            "gate_channel": gate_channel,
            "alternating": alternating,
            "rotating_frame": rotating_frame,
            "description": description,
        }
    )
    if validate:
        sequence.validate()
    return sequence
