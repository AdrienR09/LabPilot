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

## The sweep is a set of regions, not a property of a pulse

`SweepAxis` marks intervals of the timeline that grow. Everything after
them shifts, which is what a swept sequence physically does. One
mechanism covers every case:

- a Rabi marks the region that coincides with its microwave pulse;
- a Ramsey marks a *gap*, which is not a drawn object at all — so a
  per-pulse increment could not express it without a second gesture;
- a Ramsey or a Hahn echo marks **two or four** regions, because each
  point's tau appears once per alternating arm and they all have to grow
  together. Hence a list of regions under one axis rather than one region
  per sweep.

Linear spacing becomes one block repeated `points` times with an
`increment`, which is the model's own sweep primitive. Log spacing cannot
be written that way — no constant increment produces a geometric series —
so it becomes `points` blocks of one repetition each, with each region
set to that point's length. Both produce the same `Sweep` on the finished
sequence, so nothing downstream has to know which was used.
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
    linear_sweep,
    log_sweep,
)
from labpilot.core.pulse.shapes import SHAPES, Shape, shape_from_dict, shape_to_dict

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "FREQUENCY",
    "LINEAR",
    "LOG",
    "TIME",
    "Pulse",
    "Region",
    "SweepAxis",
    "Timeline",
    "Track",
    "blank_pulse",
    "ordered_channels",
    "timeline_from_sequence",
]

LINEAR = "linear"
LOG = "log"

#: What a sweep varies. `TIME` stretches the marked regions and the pulser
#: plays every point in one pass; `FREQUENCY` leaves the drawn pattern
#: alone and steps the microwave source between passes — see `SweepAxis`.
TIME = "time"
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
    """

    start: float
    stop: float
    value: bool | Shape = True
    name: str = ""

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
        return Pulse(start, stop, self.value, self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "stop": self.stop,
            "name": self.name,
            "value": True if self.value is True else shape_to_dict(self.value),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Pulse:
        value = data.get("value", True)
        return cls(
            start=float(data["start"]),
            stop=float(data["stop"]),
            value=True if value is True else shape_from_dict(value),
            name=str(data.get("name", "")),
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
        """What this track does across `[start, stop)` — `False` if nothing."""
        for pulse in self.pulses:
            if pulse.covers(start, stop):
                return pulse.value
        return False

    def edges(self) -> list[float]:
        return [t for pulse in self.pulses for t in (pulse.start, pulse.stop)]

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
class Region:
    """One marked interval of the timeline that grows with the sweep."""

    start: float
    stop: float

    def __post_init__(self) -> None:
        if self.stop <= self.start:
            raise SequenceError(
                f"A sweep region is empty ({self.start} s -> {self.stop} s). "
                f"Drag its edges apart, or remove it."
            )

    @property
    def length(self) -> float:
        return self.stop - self.start

    def to_dict(self) -> dict[str, float]:
        return {"start": self.start, "stop": self.stop}


@dataclass(frozen=True, slots=True)
class SweepAxis:
    """The swept parameter, and how each point is reached.

    ## Two ways to sweep, and why both are here

    **Time** stretches marked intervals of the timeline. Several regions
    rather than one, because a point's tau can appear more than once in a
    single pass: Ramsey has one free-evolution gap per alternating arm and
    Hahn echo has two, and all of them are the same tau. They must
    therefore be the same length, which is checked here rather than
    producing a sequence that sweeps two different things under one axis
    name. The pulser plays every point in one pass.

    **Frequency** leaves the drawn pattern completely alone and steps the
    microwave source between passes. No pulse duration can encode it, so
    there is nothing to mark on the timeline; the sequence carries the
    values and `PulsedMeasurementPlan` walks them. This is pulsed ODMR,
    and it is one field rather than a second editor because everything
    else about the two is identical — same tracks, same readout, same
    extraction, same analysis.

    `quantity` is what separates them, and it is what decides whether
    `regions` are required.
    """

    regions: tuple[Region, ...] = ()
    points: int = 50
    step: float = 20e-9
    """Added to each region's length per point. Linear time sweeps only."""
    stop_value: float = 0.0
    """The value at the *last* point. Used by a logarithmic time sweep,
    where a constant step cannot express a geometric series, and by every
    frequency sweep, which is naturally given as start-to-stop."""
    spacing: str = LINEAR
    name: str = "tau"
    unit: str = "s"
    quantity: str = TIME
    start_value: float = 0.0
    """The value at the *first* point. Frequency sweeps only — a time
    sweep's first value is a length someone drew, so reading it off the
    regions is the only way the two cannot disagree."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "regions", tuple(self.regions))
        if self.quantity not in (TIME, FREQUENCY):
            raise SequenceError(
                f"Unknown sweep quantity {self.quantity!r} — use {TIME!r} or "
                f"{FREQUENCY!r}"
            )
        if self.points < 1:
            raise SequenceError(f"A sweep needs at least one point, got {self.points}")
        if self.spacing not in (LINEAR, LOG):
            raise SequenceError(
                f"Unknown sweep spacing {self.spacing!r} — use {LINEAR!r} or {LOG!r}"
            )

        if self.quantity == FREQUENCY:
            # Defaults carried over from a time sweep would name the axis
            # "tau" and label it in seconds, which is how a plot ends up
            # claiming a 2.87 GHz resonance sits at 2.87 gigaseconds.
            if self.name == "tau":
                object.__setattr__(self, "name", FREQUENCY)
            if self.unit == "s":
                object.__setattr__(self, "unit", "Hz")
            if self.start_value <= 0 or self.stop_value <= 0:
                raise SequenceError(
                    f"A {self.name} sweep needs a positive start and stop "
                    f"(got {self.start_value} and {self.stop_value} {self.unit})"
                )
            return

        if not self.regions:
            raise SequenceError(
                "A sweep needs at least one marked region on the timeline"
            )
        lengths = [region.length for region in self.regions]
        if max(lengths) - min(lengths) > EPSILON:
            raise SequenceError(
                f"The {len(self.regions)} regions of sweep {self.name!r} are "
                f"different lengths ({', '.join(f'{v * 1e9:.1f}' for v in lengths)} ns). "
                f"They all take the same value each point, so they must start "
                f"the same length."
            )

    @property
    def stepped(self) -> bool:
        """Whether an instrument steps this sweep rather than the pulser
        playing it. The timeline is untouched by such a sweep, which is
        why nothing is marked on it."""
        return self.quantity != TIME

    @property
    def length(self) -> float:
        """Each region's length at the first point — a time sweep's first
        value, and 0 for a sweep that marks no regions."""
        return self.regions[0].length if self.regions else 0.0

    def sweep(self) -> Sweep:
        """The values this axis takes, as the sequence's own `Sweep`."""
        if self.quantity == FREQUENCY:
            base = (
                log_sweep(self.name, self.start_value, self.stop_value,
                          self.points, self.unit)
                if self.spacing == LOG
                else Sweep(
                    self.name,
                    tuple(
                        float(v) for v in
                        np.linspace(self.start_value, self.stop_value, self.points)
                    ),
                    self.unit,
                )
            )
            # `parameter` is what tells the run to step a device between
            # points instead of expecting the pulser to have played them.
            return replace(base, parameter=FREQUENCY)
        if self.spacing == LOG:
            return log_sweep(
                self.name, self.length, self.stop_value or self.length,
                self.points, self.unit,
            )
        return linear_sweep(self.name, self.length, self.step, self.points, self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regions": [region.to_dict() for region in self.regions],
            "points": self.points, "step": self.step,
            "stop_value": self.stop_value, "spacing": self.spacing,
            "name": self.name, "unit": self.unit,
            "quantity": self.quantity, "start_value": self.start_value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SweepAxis:
        return cls(
            regions=tuple(
                Region(float(r["start"]), float(r["stop"]))
                for r in data.get("regions") or ()
            ),
            points=int(data.get("points", 50)),
            step=float(data.get("step", 20e-9)),
            stop_value=float(data.get("stop_value", 0.0)),
            spacing=str(data.get("spacing", LINEAR)),
            name=str(data.get("name", "tau")),
            unit=str(data.get("unit", "s")),
            quantity=str(data.get("quantity", TIME)),
            start_value=float(data.get("start_value", 0.0)),
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

        for number, region in enumerate(self.sweep.regions if self.sweep else ()):
            if region.stop > self.end + EPSILON:
                raise SequenceError(
                    f"Sweep region {number + 1} runs to "
                    f"{region.stop * 1e9:.1f} ns, past the end of the timeline "
                    f"at {self.end * 1e9:.1f} ns. Move it over the pulse or the "
                    f"gap that should grow."
                )

        boundaries = self._boundaries()
        if len(boundaries) < 2:
            raise SequenceError(
                f"Sequence {name!r} has nothing drawn on any track — there is "
                f"nothing to play"
            )

        # Only lanes with something on them become channels. An empty lane
        # means the rig has that instrument and this sequence does not use
        # it, and writing it into every element as `False` would make the
        # sequence claim a channel the pulser then has to have free.
        drawn = [track for track in self.tracks if track.pulses]
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
            sweep=self.sweep.sweep() if self.sweep else None,
            rotating_frame=rotating_frame,
            alternating=alternating,
            laser_channel=laser_channel,
            gate_channel=gate_channel,
            description=description,
        )
        if validate:
            sequence.validate()
        return sequence

    # --- Slicing ----------------------------------------------------------

    def _boundaries(self) -> list[float]:
        """Every time at which anything changes, deduplicated and sorted.

        Includes zero, the timeline's end, and each sweep region's own
        edges — the last of those whether or not a pulse happens to start
        there, so a region always lines up with element boundaries and its
        increment has exactly one element to land on.
        """
        times = [0.0, self.end]
        for track in self.tracks:
            times.extend(track.edges())
        for region in self.sweep.regions if self.sweep else ():
            times.extend((region.start, region.stop))

        ordered: list[float] = []
        for time in sorted(times):
            if not ordered or time - ordered[-1] > EPSILON:
                ordered.append(time)
        return ordered

    def _name_at(self, start: float, stop: float) -> str:
        """A name for a slice, from whichever drawn pulse spans it.

        Names are what makes a saved sequence readable — "pi/2",
        "readout", "tau" rather than twelve unnamed intervals — so the
        first named pulse covering the slice lends it its name.
        """
        for track in self.tracks:
            for pulse in track.sorted():
                if pulse.name and pulse.covers(start, stop):
                    return pulse.name
        if self.sweep is not None and self._region_of(start, stop) is not None:
            return self.sweep.name
        return ""

    def _region_of(self, start: float, stop: float) -> int | None:
        for index, region in enumerate(self.sweep.regions if self.sweep else ()):
            if start >= region.start - EPSILON and stop <= region.stop + EPSILON:
                return index
        return None

    def _blocks(
        self, elements: list[PulseElement], boundaries: list[float]
    ) -> list[PulseBlock]:
        """The elements as blocks, with the sweep applied.

        Linear: one block repeated `points` times, each region's increment
        on the *last* element inside it, so the region's total length
        grows by `step` while any edges inside it stay put.

        Log: one block per point, each played once, each region's last
        element lengthened so the region measures that point's value. A
        geometric series has no constant increment, so there is nothing
        else it could be.

        Stepped (frequency): one block played once, exactly as drawn. The
        points are not in the sequence at all — something else changes
        between passes — so there is nothing here to vary.
        """
        sweep = self.sweep
        if sweep is None or sweep.stepped:
            name = sweep.name if sweep is not None else "block"
            return [PulseBlock(name, tuple(elements), repetitions=1)]

        last = self._last_elements(boundaries)
        fixed = self._fixed_lengths(elements, boundaries, last)

        if sweep.spacing == LINEAR:
            swept = list(elements)
            for index in last:
                swept[index] = _with(swept[index], increment=sweep.step)
            return [PulseBlock(sweep.name, tuple(swept), repetitions=sweep.points)]

        blocks: list[PulseBlock] = []
        for point, value in enumerate(sweep.sweep().values):
            stretched = list(elements)
            for region, index in enumerate(last):
                stretched[index] = _with(
                    stretched[index], duration=max(value - fixed[region], 0.0)
                )
            blocks.append(PulseBlock(f"{sweep.name}_{point}", tuple(stretched)))
        return blocks

    def _last_elements(self, boundaries: list[float]) -> list[int]:
        """The index of the final element inside each sweep region."""
        chosen: list[int] = []
        for number, region in enumerate(self.sweep.regions if self.sweep else ()):
            inside = [
                position for position in range(len(boundaries) - 1)
                if (
                    boundaries[position] >= region.start - EPSILON
                    and boundaries[position + 1] <= region.stop + EPSILON
                )
            ]
            if not inside:
                raise SequenceError(
                    f"Sweep region {number + 1} "
                    f"({region.start * 1e9:.1f}-{region.stop * 1e9:.1f} ns) does "
                    f"not line up with anything on the timeline. Move it over "
                    f"the pulse or the gap that should grow."
                )
            chosen.append(inside[-1])
        return chosen

    def _fixed_lengths(
        self, elements: list[PulseElement], boundaries: list[float], last: list[int]
    ) -> list[float]:
        """Per region, how much of it does *not* grow.

        A region cut in two by another track's edge keeps its first half
        fixed and grows the second, so the value the region measures is
        the fixed part plus the swept element.
        """
        totals: list[float] = []
        for number, region in enumerate(self.sweep.regions if self.sweep else ()):
            total = 0.0
            for position in range(len(boundaries) - 1):
                inside = (
                    boundaries[position] >= region.start - EPSILON
                    and boundaries[position + 1] <= region.stop + EPSILON
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

    return Timeline(tracks=tracks, duration=time, sweep=_axis_of(sequence, block))


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


def _axis_of(sequence: PulseSequence, block: PulseBlock) -> SweepAxis | None:
    """Where the sweep sits on the drawn timeline, if there is one.

    Recovered from the elements carrying an increment (linear) or, for a
    multi-block log sweep, from the elements whose length differs between
    the first two blocks — which are the same elements the editor would
    have written.
    """
    if sequence.sweep is None or not len(sequence.sweep):
        return None

    values = sequence.sweep.array
    if sequence.sweep.stepped:
        # Nothing on the timeline moved, so there is nothing to find in the
        # elements: the axis is entirely in the sweep's own values.
        return SweepAxis(
            points=len(values), spacing=LINEAR, quantity=FREQUENCY,
            start_value=float(values[0]), stop_value=float(values[-1]),
            name=sequence.sweep.name, unit=sequence.sweep.unit,
        )

    swept = [
        position for position, element in enumerate(block.elements) if element.increment
    ]
    spacing, step, stop_value = LINEAR, 0.0, 0.0

    if swept:
        step = block.elements[swept[0]].increment
    elif len(sequence.blocks) > 1:
        second = sequence.blocks[1]
        swept = [
            position
            for position, (a, b) in enumerate(
                zip(block.elements, second.elements, strict=False)
            )
            if abs(a.duration - b.duration) > EPSILON
        ]
        spacing, stop_value = LOG, float(values[-1])
    if not swept:
        return None

    # A region measures the sweep's first *value*, which is not always the
    # swept element's own length: a region cut in two by another track's
    # edge keeps a fixed first half. So the region is anchored at its end
    # and extended backwards by the value.
    first = float(values[0])
    regions = []
    for position in swept:
        stop = sum(e.duration for e in block.elements[: position + 1])
        regions.append(Region(max(stop - first, 0.0), stop))

    return SweepAxis(
        regions=tuple(regions), points=len(values), step=step,
        stop_value=stop_value, spacing=spacing,
        name=sequence.sweep.name, unit=sequence.sweep.unit,
    )
