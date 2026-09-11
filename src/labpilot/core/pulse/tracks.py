"""A sequence as tracks on a timeline — one lane per instrument.

This is the model behind the pulse editor, and it exists because the two
useful ways of looking at a sequence are not the same shape.

**The model is vertical.** A `PulseElement` is one interval with a value
for *every* channel, so a sequence is a run of time slices. That is what
a pulser plays, and it is what makes `increment` a single number per
slice.

**Editing is horizontal.** A person draws a laser pulse from 1 to 4 µs on
the laser track, a microwave pulse from 0 to 20 ns on the microwave
track, and an APD gate on a third — three independent objects on three
lanes, none of which knows about the others' edges.

Converting between them is the whole of this module, and it is one idea:
**every edge on every track is an element boundary**. Collect the times at
which anything changes, sort them, and each consecutive pair becomes a
`PulseElement` whose channels are whatever each track holds across it.
Going the other way, adjacent elements holding the same value on a
channel merge back into the one pulse someone actually drew.

Kept out of the Qt file for the usual reason: the slicing rule and the
sweep arithmetic are the fiddly parts, they are pure data, and `tests/`
is Qt-free.

## The timeline has a length of its own

Not merely "wherever the last pulse ends". The repolarisation wait at the
end of a sequence is *silence* — every channel low — and silence has no
edges to find. A timeline that stopped at its last drawn pulse would drop
that wait, and a sequence that repolarises for 0 ns instead of 1 µs still
runs, still produces a curve, and produces the wrong one.

## The sweep belongs to a pulse

`Pulse.sweep` says this pulse is what the measurement varies — its
**duration**, or the microwave **frequency** driving it. Everything after
a lengthening pulse shifts, which is what a swept sequence physically
does. `SweepAxis` holds only where the axis goes — endpoints, count,
spacing — shared by every marked pulse, because a measurement has one
x-axis: a Ramsey's tau appears once per alternating arm and a Hahn echo's
twice, and marking each of them is what says they grow together.

An earlier design floated the sweep free of the drawing, as shaded
regions dragged over it. That was one mechanism too many: a region had to
be lined up with a pulse by hand and could silently drift off it, and the
one thing it bought — sweeping a *gap*, which is not a drawn object — is
better bought by making the gap a drawn object.

## A gap is a pulse that drives nothing

`Pulse.drives = False` makes a pulse a **timing block**: it holds its span
of the timeline, it takes a name, it can be swept, and its channel stays
low across it. A Ramsey's free evolution and a T1's wait are then
ordinary objects to click, name and mark.

On the readout lane that same flag answers "is this a measurement?" — a
driving pulse there opens the counter gate and counts as a readout, a
non-driving one is a delay between readouts. One flag, because they are
one question: does this pulse assert its channel?

Linear spacing becomes one block repeated `points` times with an
`increment`, which is the model's own sweep primitive. Log spacing cannot
be written that way — no constant increment produces a geometric series —
so it becomes `points` blocks of one repetition each, with each swept
pulse set to that point's length. A frequency sweep changes no element at
all: the pattern plays unchanged and `PulsedMeasurementPlan` steps the
bound source between passes. All three produce the same kind of `Sweep`
on the finished sequence, so nothing downstream has to know which was
used.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.pulse.sequence import (
    PulseBlock,
    PulseElement,
    PulseSequence,
    SequenceError,
    Sweep,
    log_sweep,
)
from labpilot.core.pulse.shapes import SHAPES, Shape, shape_from_dict, shape_to_dict

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "DURATION",
    "FREQUENCY",
    "LINEAR",
    "LOG",
    "Pulse",
    "SweepAxis",
    "Timeline",
    "Track",
    "blank_pulse",
    "ordered_channels",
    "timeline_from_sequence",
]

LINEAR = "linear"
LOG = "log"

#: What a marked pulse varies. `DURATION` stretches the pulse itself and
#: the pulser plays every point in one pass; `FREQUENCY` leaves the drawing
#: untouched and steps the microwave source between passes. Both live on
#: `Pulse.sweep`.
DURATION = "duration"
FREQUENCY = "frequency"

#: Two edges closer together than this are the same edge. A pulse whose
#: end was dragged onto another track's edge should produce one boundary,
#: not a one-femtosecond element the pulser then refuses.
EPSILON = 1e-13

#: Channels a rig almost always has, in the order a physicist reads them,
#: and so the order the lanes are stacked in. Anything else follows
#: alphabetically, so the lane order is stable across edits.
_PREFERRED = ("laser", "green", "mw", "microwave", "gate", "apd", "trigger")


@dataclass(frozen=True, slots=True)
class Pulse:
    """One drawn object on one track.

    `value` is `True` for a digital pulse or a `Shape` for an analog one.
    A track holds only what it *does*; the gaps between pulses are low by
    omission, exactly as they are in the element model.

    Two flags carry everything the editor used to express with separate
    machinery, and both are per-pulse because that is where a person is
    already looking when they want to change them.
    """

    start: float
    stop: float
    value: bool | Shape = True
    name: str = ""

    sweep: str = ""
    """What about this pulse the measurement varies: `""` nothing,
    `DURATION` its length, `FREQUENCY` the microwave carrier driving it.

    Every pulse with a sweep follows the **same** axis — one measurement
    has one x-axis — which is what a Ramsey needs: its tau appears once
    per alternating arm and a Hahn echo's twice, and marking each of them
    says they grow together rather than leaving two sweeps to be kept in
    step by hand.
    """

    drives: bool = True
    """Whether this pulse actually asserts its channel.

    `False` makes it a **timing block**: it holds its span of the
    timeline, it takes a name, it can be swept — and the channel stays
    low across it. That is how a *gap* becomes a drawn object.

    A gap is the thing the old region mechanism existed for, because a
    Ramsey's free evolution is not a pulse and could not be selected or
    swept. Drawing it as a non-driving block on the readout lane (or any
    lane) makes it an ordinary object you can click, name and sweep.

    On the readout lane this is also exactly the question "is this a
    measurement?" — a driving pulse there opens the counter gate and
    counts as a readout; a non-driving one is a delay between readouts.
    """

    def __post_init__(self) -> None:
        if self.stop < self.start:
            raise SequenceError(
                f"Pulse {self.name or '<unnamed>'} ends before it starts "
                f"({self.start} s -> {self.stop} s)"
            )
        if self.start < 0:
            raise SequenceError(
                f"Pulse {self.name or '<unnamed>'} starts before zero ({self.start} s)"
            )
        if self.sweep not in ("", DURATION, FREQUENCY):
            raise SequenceError(
                f"Pulse {self.name or '<unnamed>'} sweeps {self.sweep!r} — "
                f"use {DURATION!r}, {FREQUENCY!r}, or '' for a fixed pulse"
            )

    @property
    def duration(self) -> float:
        return self.stop - self.start

    @property
    def analog(self) -> bool:
        return isinstance(self.value, Shape)

    def covers(self, start: float, stop: float) -> bool:
        """Whether this pulse is high across the whole of `[start, stop)`."""
        return self.start - EPSILON <= start and stop <= self.stop + EPSILON

    def moved(self, start: float, stop: float) -> Pulse:
        return replace(self, start=start, stop=stop)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "stop": self.stop,
            "name": self.name,
            "value": True if self.value is True else shape_to_dict(self.value),
            "sweep": self.sweep,
            "drives": self.drives,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Pulse:
        value = data.get("value", True)
        return cls(
            start=float(data["start"]),
            stop=float(data["stop"]),
            value=True if value is True else shape_from_dict(value),
            name=str(data.get("name", "")),
            sweep=str(data.get("sweep", "")),
            drives=bool(data.get("drives", True)),
        )


@dataclass(slots=True)
class Track:
    """One instrument's lane: a channel name and the pulses drawn on it.

    Mutable, unlike everything else in `core/pulse/`, because this is what
    a UI holds and edits between saves. What gets saved is the
    `PulseSequence` it converts to, which is frozen.
    """

    channel: str
    pulses: list[Pulse] = field(default_factory=list)
    label: str = ""
    """What the lane is called on screen when that differs from the
    symbolic channel — "APD readout" for `gate`."""

    def sorted(self) -> list[Pulse]:
        return sorted(self.pulses, key=lambda pulse: pulse.start)

    def at(self, start: float, stop: float) -> bool | Shape:
        """What this track does across `[start, stop)` — `False` if nothing.

        A non-driving pulse answers `False` like an empty stretch does: it
        holds the time but asserts nothing, which is the whole of what
        makes it a gap rather than an output.
        """
        for pulse in self.pulses:
            if pulse.drives and pulse.covers(start, stop):
                return pulse.value
        return False

    def edges(self) -> list[float]:
        """Every time this track changes anything.

        Non-driving pulses included: their edges are still element
        boundaries, because a swept gap needs an element of its own to
        carry the increment.
        """
        return [t for pulse in self.pulses for t in (pulse.start, pulse.stop)]

    @property
    def driving(self) -> list[Pulse]:
        """The pulses that actually assert this channel."""
        return [pulse for pulse in self.pulses if pulse.drives]

    @property
    def end(self) -> float:
        return max((pulse.stop for pulse in self.pulses), default=0.0)

    def overlapping(self) -> tuple[Pulse, Pulse] | None:
        """The first pair of pulses that overlap, if any.

        Two pulses on one track at the same time is not something a pulser
        could play — a channel has one level at a time — so it is caught
        here rather than producing an element whose value depends on which
        pulse happened to be checked first.
        """
        ordered = self.sorted()
        for earlier, later in pairwise(ordered):
            if later.start < earlier.stop - EPSILON:
                return earlier, later
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "label": self.label,
            "pulses": [pulse.to_dict() for pulse in self.sorted()],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Track:
        return cls(
            channel=str(data["channel"]),
            label=str(data.get("label", "")),
            pulses=[Pulse.from_dict(p) for p in data.get("pulses") or ()],
        )


@dataclass(frozen=True, slots=True)
class SweepAxis:
    """Where the swept pulses go — one axis, shared by all of them.

    **Which** pulses move is on the pulses (`Pulse.sweep`), because that
    is where a person is already looking when they decide. What they move
    *to* is here, because a measurement has one x-axis: a Ramsey's tau
    appears once per alternating arm and a Hahn echo's twice, and all of
    them take the same value at each point.

    The axis therefore carries only the endpoints and the count. The
    quantity and the unit are not stored at all — they follow from what
    the marked pulses sweep, which is the only way the two cannot end up
    disagreeing. `Timeline.sweep_quantity` answers that question.

    `start` is optional and means "wherever the drawn pulse already is".
    A duration sweep leaves it at zero: the first value is the length
    someone drew, so reading it off the canvas is what keeps the drawing
    honest. A frequency sweep has nothing drawn to read, so it states
    both ends.
    """

    points: int = 50
    stop: float = 0.0
    """The value at the last point."""
    start: float = 0.0
    """The value at the first point, or 0 to take it from the drawing."""
    spacing: str = LINEAR
    name: str = ""
    """What to call the axis. Empty takes the quantity's own name — `tau`
    for a duration, `frequency` for a carrier."""

    def __post_init__(self) -> None:
        if self.points < 1:
            raise SequenceError(f"A sweep needs at least one point, got {self.points}")
        if self.spacing not in (LINEAR, LOG):
            raise SequenceError(
                f"Unknown sweep spacing {self.spacing!r} — use {LINEAR!r} or {LOG!r}"
            )

    def values(self, quantity: str, first: float) -> Sweep:
        """The values this axis takes, as the sequence's own `Sweep`.

        `first` is the drawn length, used when `start` is left at zero.
        `quantity` decides the name, the unit, and whether the pulser
        plays the points or an instrument steps them.
        """
        start = self.start or first
        stop = self.stop or start
        unit = "Hz" if quantity == FREQUENCY else "s"
        # A name carried over from the other quantity is not a name someone
        # chose, it is a leftover — and leaving it would label a 2.87 GHz
        # axis "tau". A name that is neither default was chosen, and stays.
        default, stale = (
            (FREQUENCY, "tau") if quantity == FREQUENCY else ("tau", FREQUENCY)
        )
        name = default if self.name in ("", stale) else self.name

        if self.spacing == LOG:
            sweep = log_sweep(name, start, stop, self.points, unit)
        else:
            sweep = Sweep(
                name,
                tuple(float(v) for v in np.linspace(start, stop, self.points)),
                unit,
            )
        if quantity == FREQUENCY:
            # `parameter` is what tells the run to step a device between
            # points instead of expecting the pulser to have played them.
            return replace(sweep, parameter=FREQUENCY)
        return sweep

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": self.points, "start": self.start, "stop": self.stop,
            "spacing": self.spacing, "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SweepAxis:
        return cls(
            points=int(data.get("points", 50)),
            start=float(data.get("start", 0.0)),
            stop=float(data.get("stop", 0.0)),
            spacing=str(data.get("spacing", LINEAR)),
            name=str(data.get("name", "")),
        )


@dataclass(slots=True)
class Timeline:
    """What the editor holds: lanes, a length, and a sweep.

    `duration` is the timeline's own end, not wherever the last pulse
    happens to stop — see the module docstring on why trailing silence is
    load-bearing.
    """

    tracks: list[Track] = field(default_factory=list)
    duration: float = 0.0
    sweep: SweepAxis | None = None

    @property
    def end(self) -> float:
        """Where the timeline actually ends: its declared length, or the
        last drawn edge when nothing longer has been declared."""
        return max(self.duration, *(track.end for track in self.tracks), 0.0)

    @property
    def channels(self) -> list[str]:
        return [track.channel for track in self.tracks]

    def track(self, channel: str) -> Track:
        for track in self.tracks:
            if track.channel == channel:
                return track
        raise KeyError(
            f"No track {channel!r} — this timeline has "
            f"{', '.join(self.channels) or 'none'}"
        )

    def to_sequence(
        self,
        name: str,
        *,
        laser_channel: str = "laser",
        gate_channel: str | None = "gate",
        alternating: bool = False,
        rotating_frame: bool = True,
        description: str = "",
        validate: bool = True,
    ) -> PulseSequence:
        """Slice the drawn tracks at every edge and build a playable sequence.

        `validate=False` is for a timeline mid-edit: a half-drawn sequence
        has no readout yet, and refusing to render it would make the
        editor unusable. Saving always validates.
        """
        if not self.tracks:
            raise SequenceError(f"Sequence {name!r} has no tracks to build from")
        for track in self.tracks:
            clash = track.overlapping()
            if clash is not None:
                earlier, later = clash
                raise SequenceError(
                    f"Two pulses overlap on track {track.channel!r}: "
                    f"{earlier.name or 'one'} runs to {earlier.stop * 1e9:.1f} ns "
                    f"and {later.name or 'the next'} starts at "
                    f"{later.start * 1e9:.1f} ns. A channel has one level at a time."
                )

        self._check_swept(laser_channel, gate_channel)

        boundaries = self._boundaries()
        if len(boundaries) < 2:
            raise SequenceError(
                f"Sequence {name!r} has nothing drawn on any track — there is "
                f"nothing to play"
            )

        # Only lanes that actually assert something become channels. An
        # empty lane — or one holding nothing but timing blocks — means the
        # rig has that instrument and this sequence does not drive it, and
        # writing it into every element as `False` would make the sequence
        # claim a channel the pulser then has to have free.
        drawn = [track for track in self.tracks if track.driving]
        elements = [
            PulseElement(
                duration=stop - start,
                channels={track.channel: track.at(start, stop) for track in drawn},
                name=self._name_at(start, stop),
            )
            for start, stop in pairwise(boundaries)
        ]

        sequence = PulseSequence(
            name=name,
            blocks=tuple(self._blocks(elements, boundaries)),
            sweep=self.sweep_values(),
            rotating_frame=rotating_frame,
            alternating=alternating,
            laser_channel=laser_channel,
            gate_channel=gate_channel,
            description=description,
        )
        if validate:
            sequence.validate()
        return sequence

    # --- What the marked pulses say ---------------------------------------

    @property
    def swept(self) -> list[Pulse]:
        """Every pulse this measurement varies, in time order."""
        return sorted(
            (pulse for track in self.tracks for pulse in track.pulses if pulse.sweep),
            key=lambda pulse: pulse.start,
        )

    @property
    def sweep_quantity(self) -> str:
        """What the marked pulses vary — `""` when none are marked.

        Read off the pulses rather than stored beside them, so the axis
        and the drawing cannot come to disagree about what is being
        measured.
        """
        modes = {pulse.sweep for pulse in self.swept}
        if not modes:
            return ""
        if len(modes) > 1:
            raise SequenceError(
                f"Pulses on this timeline sweep different things "
                f"({', '.join(sorted(modes))}). A measurement has one x-axis, "
                f"so every marked pulse must vary the same quantity."
            )
        return modes.pop()

    def sweep_values(self) -> Sweep | None:
        """This measurement's axis, or None when nothing is marked."""
        quantity = self.sweep_quantity
        if not quantity:
            return None
        axis = self.sweep or SweepAxis()
        first = self.swept[0].duration if quantity == DURATION else 0.0
        return axis.values(quantity, first)

    def _check_swept(self, laser: str = "", gate: str | None = None) -> None:
        """The ways a set of marked pulses can be inconsistent."""
        marked = self.swept
        quantity = self.sweep_quantity
        if quantity == DURATION and len(marked) > 1:
            lengths = [pulse.duration for pulse in marked]
            if max(lengths) - min(lengths) > EPSILON:
                raise SequenceError(
                    f"{len(marked)} pulses are swept but they are different "
                    f"lengths ({', '.join(f'{v * 1e9:.1f}' for v in lengths)} ns). "
                    f"They all take the same value at each point — a Ramsey's "
                    f"tau appears once per arm — so they must start equal."
                )
        if quantity != FREQUENCY:
            return

        if len(marked) > 1:
            raise SequenceError(
                f"{len(marked)} pulses sweep the microwave frequency. Only one "
                f"can: the frequency belongs to the source, not to a pulse, so "
                f"marking a second says the source has two frequencies at once."
            )
        # A frequency belongs to a *drive*. A laser pulse and a counter
        # gate are on/off lines with no carrier to move, so marking one
        # would name a setting the run then cannot find on any source.
        channel = self.track_of(marked[0])
        if channel in (laser, gate):
            raise SequenceError(
                f"The pulse {marked[0].name or '<unnamed>'} is on "
                f"{channel!r}, which is "
                f"{'the laser' if channel == laser else 'the readout gate'} — "
                f"an on/off line with no frequency to sweep. Mark the "
                f"microwave pulse instead, or sweep this one's length."
            )

    def track_of(self, pulse: Pulse) -> str:
        """Which channel a drawn pulse sits on."""
        for track in self.tracks:
            if any(other is pulse for other in track.pulses):
                return track.channel
        return ""

    # --- Slicing ----------------------------------------------------------

    def _boundaries(self) -> list[float]:
        """Every time at which anything changes, deduplicated and sorted.

        Every pulse's edges, driving or not: a timing block holds real
        time, and a swept one needs an element of its own for the
        increment to land on.
        """
        times = [0.0, self.end]
        for track in self.tracks:
            times.extend(track.edges())

        ordered: list[float] = []
        for time in sorted(times):
            if not ordered or time - ordered[-1] > EPSILON:
                ordered.append(time)
        return ordered

    def _name_at(self, start: float, stop: float) -> str:
        """A name for a slice, from whichever drawn pulse spans it.

        Names are what makes a saved sequence readable — "pi/2",
        "readout", "tau" rather than twelve unnamed intervals — so the
        first named pulse covering the slice lends it its name. Timing
        blocks count: naming the gap is most of why drawing it is better
        than leaving it implicit.
        """
        for track in self.tracks:
            for pulse in track.sorted():
                if pulse.name and pulse.covers(start, stop):
                    return pulse.name
        return ""

    def _blocks(
        self, elements: list[PulseElement], boundaries: list[float]
    ) -> list[PulseBlock]:
        """The elements as blocks, with the sweep applied.

        Linear: one block repeated `points` times, each swept pulse's
        increment on the *last* element inside it, so the pulse's total
        length grows by one step while any edges inside it stay put.

        Log: one block per point, each played once, each swept pulse's
        last element lengthened so the pulse measures that point's value.
        A geometric series has no constant increment, so there is nothing
        else it could be.

        Frequency: one block played once, exactly as drawn. The points are
        not in the sequence at all — the source changes between passes —
        so there is nothing here to vary.
        """
        quantity = self.sweep_quantity
        values = self.sweep_values()
        if quantity != DURATION or values is None:
            name = values.name if values is not None else "block"
            return [PulseBlock(name, tuple(elements), repetitions=1)]

        axis = self.sweep or SweepAxis()
        last = self._last_elements(boundaries)
        fixed = self._fixed_lengths(elements, boundaries, last)

        if axis.spacing == LINEAR:
            step = (
                (values.values[1] - values.values[0]) if len(values) > 1 else 0.0
            )
            swept = list(elements)
            for index in last:
                swept[index] = _with(swept[index], increment=step)
            return [PulseBlock(values.name, tuple(swept), repetitions=len(values))]

        blocks: list[PulseBlock] = []
        for point, value in enumerate(values.values):
            stretched = list(elements)
            for number, index in enumerate(last):
                stretched[index] = _with(
                    stretched[index], duration=max(value - fixed[number], 0.0)
                )
            blocks.append(PulseBlock(f"{values.name}_{point}", tuple(stretched)))
        return blocks

    def _last_elements(self, boundaries: list[float]) -> list[int]:
        """The index of the final element inside each swept pulse."""
        chosen: list[int] = []
        for pulse in self.swept:
            inside = [
                position for position in range(len(boundaries) - 1)
                if (
                    boundaries[position] >= pulse.start - EPSILON
                    and boundaries[position + 1] <= pulse.stop + EPSILON
                )
            ]
            if not inside:
                raise SequenceError(
                    f"The swept pulse {pulse.name or '<unnamed>'} "
                    f"({pulse.start * 1e9:.1f}-{pulse.stop * 1e9:.1f} ns) has no "
                    f"length to grow. Drag its edges apart, or turn its sweep off."
                )
            chosen.append(inside[-1])
        return chosen

    def _fixed_lengths(
        self, elements: list[PulseElement], boundaries: list[float], last: list[int]
    ) -> list[float]:
        """Per swept pulse, how much of it does *not* grow.

        A pulse cut in two by another track's edge keeps its first half
        fixed and grows the second, so the value it measures is the fixed
        part plus the swept element.
        """
        totals: list[float] = []
        for number, pulse in enumerate(self.swept):
            total = 0.0
            for position in range(len(boundaries) - 1):
                inside = (
                    boundaries[position] >= pulse.start - EPSILON
                    and boundaries[position + 1] <= pulse.stop + EPSILON
                )
                if inside and position != last[number]:
                    total += elements[position].duration
            totals.append(total)
        return totals

    # --- Storage ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """What a workflow parameter stores — plain data, no pulse objects."""
        return {
            "tracks": [track.to_dict() for track in self.tracks],
            "duration": self.duration,
            "sweep": self.sweep.to_dict() if self.sweep else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Timeline:
        sweep = data.get("sweep")
        return cls(
            tracks=[Track.from_dict(t) for t in data.get("tracks") or ()],
            duration=float(data.get("duration", 0.0)),
            sweep=SweepAxis.from_dict(sweep) if sweep else None,
        )


def _with(
    element: PulseElement, *, duration: float | None = None, increment: float = 0.0
) -> PulseElement:
    return PulseElement(
        duration=element.duration if duration is None else duration,
        channels=element.channels,
        increment=increment,
        name=element.name,
    )


def ordered_channels(channels: Iterable[str]) -> list[str]:
    """Lane order: the well-known channels first, then the rest sorted."""
    names = set(channels)
    first = [name for name in _PREFERRED if name in names]
    return first + sorted(names - set(first))


def blank_pulse(start: float = 0.0, duration: float = 100e-9, shape: str = "") -> Pulse:
    """A new drawn pulse — digital unless a shape is named."""
    if not shape:
        return Pulse(start, start + duration)
    if shape not in SHAPES:
        raise SequenceError(
            f"Unknown pulse shape {shape!r} — known shapes are "
            f"{', '.join(sorted(SHAPES))}"
        )
    return Pulse(start, start + duration, SHAPES[shape]())


# --- Sequence -> timeline ---------------------------------------------------


def timeline_from_sequence(
    sequence: PulseSequence, channels: Iterable[str] = ()
) -> Timeline:
    """The sequence drawn as tracks, at the first point of its sweep.

    Adjacent elements holding the same value on a channel merge back into
    the one pulse someone drew, so a sequence that another track's edges
    sliced into twelve elements comes back as three.

    `channels` are the rig's declared channels, which get a lane even when
    no element uses them yet — so a sequence loaded into an editor still
    has somewhere to put the laser.
    """
    declared = ordered_channels(channels)
    used = ordered_channels(sequence.channels)
    lanes = declared + [name for name in used if name not in declared]

    block = sequence.blocks[0] if sequence.blocks else PulseBlock("block")
    tracks = [Track(channel=name) for name in lanes]
    by_channel = {track.channel: track for track in tracks}

    time = 0.0
    for element in block.elements:
        for channel, value in element.channels.items():
            if value is False:
                continue
            track = by_channel.get(channel)
            if track is None:
                track = Track(channel=channel)
                tracks.append(track)
                by_channel[channel] = track
            _extend(track, time, time + element.duration, value, element.name)
        time += element.duration

    axis, quantity, spans = _axis_of(sequence, block)
    line = Timeline(tracks=tracks, duration=time, sweep=axis)
    if quantity:
        _mark_swept(
            line, quantity, spans,
            laser=sequence.laser_channel, gate=sequence.gate_channel,
        )
    return line


def _extend(
    track: Track, start: float, stop: float, value: bool | Shape, name: str
) -> None:
    """Add `[start, stop)` to the track, merging with the pulse before it
    when they touch and hold the same value."""
    previous = track.pulses[-1] if track.pulses else None
    if (
        previous is not None
        and abs(previous.stop - start) <= EPSILON
        and _same(previous.value, value)
    ):
        track.pulses[-1] = Pulse(previous.start, stop, previous.value, previous.name)
        return
    track.pulses.append(Pulse(start, stop, value, name))


def _same(left: bool | Shape, right: bool | Shape) -> bool:
    """Whether two channel values are the same drawn pulse.

    A `Shape` compares by its serialised parameters rather than by
    identity: two `Sin`s of equal amplitude, frequency and phase in
    consecutive elements are one drawn microwave pulse that another
    track's edge happened to cut in half.
    """
    if isinstance(left, Shape) != isinstance(right, Shape):
        return False
    if isinstance(left, Shape) and isinstance(right, Shape):
        return shape_to_dict(left) == shape_to_dict(right)
    return bool(left) is bool(right)


def _axis_of(
    sequence: PulseSequence, block: PulseBlock
) -> tuple[SweepAxis | None, str, list[tuple[float, float]]]:
    """The axis, what it varies, and which spans of the drawing move.

    Recovered from the elements carrying an increment (linear) or, for a
    multi-block log sweep, from the elements whose length differs between
    the first two blocks — the same elements the editor would have
    written. A frequency sweep changes no element at all, so its axis is
    entirely in the sweep's own values and there is no span to find.
    """
    if sequence.sweep is None or not len(sequence.sweep):
        return None, "", []

    values = sequence.sweep.array
    axis = SweepAxis(
        points=len(values), start=float(values[0]), stop=float(values[-1]),
        spacing=LINEAR, name=sequence.sweep.name,
    )
    if sequence.sweep.stepped:
        return axis, FREQUENCY, []

    swept = [
        position for position, element in enumerate(block.elements) if element.increment
    ]
    if not swept and len(sequence.blocks) > 1:
        second = sequence.blocks[1]
        swept = [
            position
            for position, (a, b) in enumerate(
                zip(block.elements, second.elements, strict=False)
            )
            if abs(a.duration - b.duration) > EPSILON
        ]
        axis = replace(axis, spacing=LOG)
    if not swept:
        return None, "", []

    # A swept pulse measures the sweep's first *value*, which is not always
    # the swept element's own length: a pulse cut in two by another track's
    # edge keeps a fixed first half. So the span is anchored at its end and
    # extended backwards by the value.
    first = float(values[0])
    spans = []
    for position in swept:
        stop = sum(e.duration for e in block.elements[: position + 1])
        spans.append((max(stop - first, 0.0), stop))
    return axis, DURATION, spans


def _mark_swept(
    line: Timeline,
    quantity: str,
    spans: list[tuple[float, float]],
    *,
    laser: str,
    gate: str | None,
) -> None:
    """Put the sweep back on the pulses it belongs to.

    A span that coincides with something drawn marks that pulse. One that
    does not is a **gap** — a Ramsey's free evolution, a T1's wait — and
    becomes a timing block on the readout lane, which is exactly what it
    was in the editor before it was saved. Round-tripping a sequence
    therefore gives back a drawing whose every swept interval is an object
    you can click.
    """
    if quantity == FREQUENCY:
        # The frequency belongs to the source, not to a pulse, so it goes
        # on whichever pulse is doing the driving — which is any lane that
        # is neither the laser nor the readout.
        for track in line.tracks:
            if track.channel in (laser, gate):
                continue
            drive = next((p for p in track.sorted() if p.drives), None)
            if drive is not None:
                _replace_pulse(track, drive, sweep=FREQUENCY)
                return
        return

    lane = next((t for t in line.tracks if gate and t.channel == gate), None)
    for start, stop in spans:
        found = _pulse_at(line, start, stop)
        if found is not None:
            track, pulse = found
            _replace_pulse(track, pulse, sweep=DURATION)
        elif lane is not None:
            lane.pulses.append(
                Pulse(start, stop, True, "tau", sweep=DURATION, drives=False)
            )


def _pulse_at(line: Timeline, start: float, stop: float) -> tuple[Track, Pulse] | None:
    for track in line.tracks:
        for pulse in track.sorted():
            if abs(pulse.start - start) <= EPSILON and abs(pulse.stop - stop) <= EPSILON:
                return track, pulse
    return None


def _replace_pulse(track: Track, pulse: Pulse, **fields: Any) -> None:
    track.pulses[track.pulses.index(pulse)] = replace(pulse, **fields)
