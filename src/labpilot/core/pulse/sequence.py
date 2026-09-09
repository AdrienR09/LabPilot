"""The pulse sequence object model — device-independent, Qt-free, data.

A sequence describes *what should happen when*, on named channels, with
one quantity swept across repetitions. It says nothing about sample
rates, memory granularity or channel wiring, because the thing that
authors a sequence — a person at a desk, with no hardware — cannot know
any of that. Compiling to a device's own format is the pulser adapter's
job (`PulserMixin.upload_sequence`), which is where the constraints live.

Reimplemented from Qudi's `logic/pulsed/pulse_objects.py`, which is the
best pulse model in the field. Four deliberate differences:

1. **Channels are symbolic** — `"laser"`, `"mw"`, `"gate"`, never
   `"d_ch1"`. Qudi bakes physical channel names into its generation
   parameters, which ties a saved sequence to one rig's wiring. Here the
   mapping to physical channels belongs to the measurement workflow's
   bindings, so the same file runs on any rig.

2. **A sequence knows its own sweep.** `Sweep` carries the swept values
   and their unit, so a plan can state the run's axes *before the first
   point*. Qudi passes an equivalent fact to its measurement logic through
   a side-channel dict (`measurement_information`) after generation, which
   is why its templates configure the counter by hand.

3. **`repetitions` means what it says.** Qudi's means *extra* plays, so a
   block with `repetitions=3` runs four times — a documented trip-hazard
   in its own generator methods.

4. **Serialised as data, never pickle.** Qudi pickles its objects and pays
   for it across ~300 lines of loader: migration shims, a `ModuleNotFound`
   guard, and a `# FIXME` repairing an object its own pickle destroyed.

## The sweep primitive

Everything sweeps through one mechanism, taken directly from Qudi because
it is genuinely elegant: on the *n*-th repetition of a block, every
element lasts `duration + n * increment`. A whole Rabi is one four-element
block repeated fifty times, with an increment on the microwave element.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping

from labpilot.core.errors import LabPilotError
from labpilot.core.pulse.shapes import Shape, shape_from_dict, shape_to_dict

__all__ = [
    "ChannelMap",
    "PulseBlock",
    "PulseElement",
    "PulseSequence",
    "SequenceError",
    "Sweep",
    "linear_sweep",
    "log_sweep",
]


class SequenceError(LabPilotError):
    """A sequence that cannot be played as described."""


@dataclass(frozen=True, slots=True)
class Sweep:
    """The quantity this sequence varies, and the values it takes.

    This is the piece Qudi's model lacks, and the reason a pulsed run can
    describe itself: the axis of the resulting dataset is `values`, its
    unit is `unit`, and both are known before any hardware is touched.
    """

    name: str = "tau"
    values: tuple[float, ...] = ()
    unit: str = "s"
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(float(v) for v in self.values))
        if not self.name:
            raise SequenceError("A sweep needs a name")

    def __len__(self) -> int:
        return len(self.values)

    @property
    def array(self) -> np.ndarray:
        return np.asarray(self.values, dtype=np.float64)


def linear_sweep(name: str, start: float, step: float, points: int, unit: str = "s") -> Sweep:
    """The sweep an `increment` produces — `start + n * step`."""
    if points < 1:
        raise SequenceError(f"A sweep needs at least one point, got {points}")
    return Sweep(name, tuple(start + n * step for n in range(points)), unit)


def log_sweep(name: str, start: float, stop: float, points: int, unit: str = "s") -> Sweep:
    """Logarithmically spaced — how T1 is measured, since the decay spans
    decades and linear spacing wastes almost every point."""
    if points < 1:
        raise SequenceError(f"A sweep needs at least one point, got {points}")
    if start <= 0 or stop <= 0:
        raise SequenceError("A logarithmic sweep needs positive endpoints")
    return Sweep(name, tuple(np.geomspace(start, stop, points)), unit)


@dataclass(frozen=True, slots=True)
class PulseElement:
    """One interval, and what every channel does during it.

    A digital channel is a `bool` — high or low for the whole element. An
    analog channel is a `Shape`. A channel absent from `channels` is low
    (or idle) by omission, so an element only names what it actually does.
    """

    duration: float
    """Seconds, at repetition zero."""
    channels: Mapping[str, bool | Shape] = field(default_factory=dict)
    increment: float = 0.0
    """Added once per repetition of the containing block. This is the
    whole sweep mechanism."""
    name: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "channels", dict(self.channels))
        if self.duration < 0:
            raise SequenceError(
                f"Element {self.name or '<unnamed>'} has a negative duration "
                f"({self.duration} s)"
            )
        for channel, value in self.channels.items():
            if not isinstance(value, (bool, np.bool_)) and not isinstance(value, Shape):
                raise SequenceError(
                    f"Channel {channel!r} in element {self.name or '<unnamed>'} "
                    f"is a {type(value).__name__}; it must be a bool (digital) "
                    f"or a Shape (analog)"
                )

    def duration_at(self, repetition: int) -> float:
        """This element's length on the n-th repetition."""
        return self.duration + repetition * self.increment

    def is_high(self, channel: str) -> bool:
        """Whether a *digital* channel is asserted during this element."""
        return bool(self.channels.get(channel) is True)

    @property
    def analog_channels(self) -> frozenset[str]:
        return frozenset(
            name for name, value in self.channels.items() if isinstance(value, Shape)
        )

    @property
    def digital_channels(self) -> frozenset[str]:
        return frozenset(
            name for name, value in self.channels.items()
            if isinstance(value, (bool, np.bool_))
        )


@dataclass(frozen=True, slots=True)
class PulseBlock:
    """An ordered run of elements, played `repetitions` times.

    On repetition *n* every element is `duration + n * increment` long,
    which is how one block expresses a whole swept experiment.
    """

    name: str
    elements: tuple[PulseElement, ...] = ()
    repetitions: int = 1
    """How many times this block plays. Exactly this many — see the module
    docstring on Qudi's off-by-one."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "elements", tuple(self.elements))
        if self.repetitions < 1:
            raise SequenceError(
                f"Block {self.name!r} would play {self.repetitions} times; "
                f"a block that never plays should be removed instead"
            )

    def __len__(self) -> int:
        return len(self.elements)

    def duration_at(self, repetition: int) -> float:
        return sum(e.duration_at(repetition) for e in self.elements)

    @property
    def duration(self) -> float:
        """Total played time, over every repetition."""
        return sum(self.duration_at(n) for n in range(self.repetitions))

    @property
    def channels(self) -> frozenset[str]:
        return frozenset().union(*(frozenset(e.channels) for e in self.elements)) \
            if self.elements else frozenset()

    @property
    def sweeps(self) -> bool:
        """Whether anything in this block varies with repetition."""
        return any(e.increment for e in self.elements)


@dataclass(frozen=True, slots=True)
class PulseSequence:
    """A complete, playable experiment description.

    Symbolic channels throughout; `ChannelMap` resolves them to a
    particular pulser's physical channels at upload time.
    """

    name: str
    blocks: tuple[PulseBlock, ...] = ()
    sweep: Sweep | None = None
    rotating_frame: bool = True
    """Whether analog phase is continuous across element boundaries.
    Ramsey and Hahn echo measure a phase difference, so they are simply
    wrong without it."""
    alternating: bool = False
    """Whether consecutive readouts alternate signal and reference. Doubles
    the laser-pulse count, and the analysis de-interleaves [::2]/[1::2]."""
    laser_channel: str = "laser"
    gate_channel: str | None = "gate"
    ignore_lasers: tuple[int, ...] = ()
    """Readouts to drop from the analysis — a calibration pulse at the
    front, typically."""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocks", tuple(self.blocks))
        object.__setattr__(self, "ignore_lasers", tuple(self.ignore_lasers))
        if not self.name:
            raise SequenceError("A sequence needs a name")

    # --- Derived facts ----------------------------------------------------

    @property
    def duration(self) -> float:
        """Total played time in seconds."""
        return sum(block.duration for block in self.blocks)

    @property
    def channels(self) -> frozenset[str]:
        """Every symbolic channel this sequence uses."""
        return frozenset().union(*(b.channels for b in self.blocks)) \
            if self.blocks else frozenset()

    @property
    def readout_channel(self) -> str:
        """The channel whose rising edges mark a readout.

        The **gate**, when the sequence has one: not every laser pulse is
        a measurement. T1 polarises with the laser, waits, and only then
        reads out — counting laser edges would score that as two readouts
        per point and silently halve the sweep. The gated counter counts
        gates, so the sequence counts gates too, and the two cannot
        disagree.

        An ungated rig has no such channel and its laser pulses *are* its
        readouts, which is the fallback.
        """
        if self.gate_channel and self.gate_channel in self.channels:
            return self.gate_channel
        return self.laser_channel

    def readouts(self) -> int:
        """How many readout windows this sequence produces, counted as
        rising edges of `readout_channel` across every repetition."""
        channel = self.readout_channel
        count = 0
        previous = False
        for block in self.blocks:
            for _ in range(block.repetitions):
                for element in block.elements:
                    high = element.is_high(channel)
                    if high and not previous:
                        count += 1
                    previous = high
        return count

    def readout_window(self) -> float:
        """How long a single readout window stays open, in seconds.

        The longest contiguous run of `readout_channel` across the whole
        sequence — longest rather than first because a T1's readouts are
        all the same length but its *initialisation* laser pulse is not,
        and a counter armed for the shorter of the two records half a
        readout.

        This is what a gated counter's record length is derived from, so
        it lives on the sequence: the sequence already knows how many
        readouts it produces, and how long each one is comes from exactly
        the same walk.
        """
        channel = self.readout_channel
        longest = 0.0
        current = 0.0
        for block in self.blocks:
            for repetition in range(block.repetitions):
                for element in block.elements:
                    if element.is_high(channel):
                        current += element.duration_at(repetition)
                        longest = max(longest, current)
                    else:
                        current = 0.0
        return longest

    @property
    def points(self) -> int:
        """How many swept points, from the sweep if declared, else from
        the readouts (halved when alternating, since a reference readout
        is not its own point)."""
        if self.sweep is not None:
            return len(self.sweep)
        windows = self.readouts()
        return windows // 2 if self.alternating else windows

    # --- Validation -------------------------------------------------------

    def validate(self) -> None:
        """Check the sequence is internally consistent.

        Raises `SequenceError` describing the first problem found. Called
        by the editor before saving and by the pulser before uploading, so
        a malformed sequence never reaches hardware.
        """
        if not self.blocks:
            raise SequenceError(f"Sequence {self.name!r} has no blocks")
        if not any(block.elements for block in self.blocks):
            raise SequenceError(f"Sequence {self.name!r} has no elements")

        if self.laser_channel not in self.channels:
            raise SequenceError(
                f"Sequence {self.name!r} declares its laser channel as "
                f"{self.laser_channel!r}, which no element uses — its "
                f"channels are {sorted(self.channels)}"
            )

        windows = self.readouts()
        if windows == 0:
            raise SequenceError(
                f"Sequence {self.name!r} never raises "
                f"{self.readout_channel!r}, so it produces no readout"
            )
        if self.alternating and windows % 2:
            raise SequenceError(
                f"Sequence {self.name!r} is alternating but has {windows} "
                f"readouts; signal and reference must pair up"
            )

        if self.sweep is not None:
            expected = len(self.sweep)
            produced = windows // 2 if self.alternating else windows
            if expected != produced:
                raise SequenceError(
                    f"Sequence {self.name!r} sweeps {expected} point(s) but "
                    f"produces {produced} readout(s) — the sweep and the "
                    f"block repetitions disagree"
                )

        for index in self.ignore_lasers:
            if not 0 <= index < windows:
                raise SequenceError(
                    f"Sequence {self.name!r} ignores readout {index}, but it "
                    f"has only {windows}"
                )

    # --- Serialisation ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "rotating_frame": self.rotating_frame,
            "alternating": self.alternating,
            "laser_channel": self.laser_channel,
            "gate_channel": self.gate_channel,
            "ignore_lasers": list(self.ignore_lasers),
            "sweep": (
                None if self.sweep is None
                else {
                    "name": self.sweep.name,
                    "values": list(self.sweep.values),
                    "unit": self.sweep.unit,
                    "label": self.sweep.label,
                }
            ),
            "blocks": [
                {
                    "name": block.name,
                    "repetitions": block.repetitions,
                    "elements": [
                        {
                            "name": element.name,
                            "duration": element.duration,
                            "increment": element.increment,
                            "channels": {
                                channel: (
                                    value if isinstance(value, (bool, np.bool_))
                                    else shape_to_dict(value)
                                )
                                for channel, value in element.channels.items()
                            },
                        }
                        for element in block.elements
                    ],
                }
                for block in self.blocks
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PulseSequence:
        sweep_data = data.get("sweep")
        sweep = (
            Sweep(
                name=sweep_data.get("name", "tau"),
                values=tuple(sweep_data.get("values") or ()),
                unit=sweep_data.get("unit", "s"),
                label=sweep_data.get("label", ""),
            )
            if sweep_data else None
        )
        blocks = tuple(
            PulseBlock(
                name=block.get("name", ""),
                repetitions=int(block.get("repetitions", 1)),
                elements=tuple(
                    PulseElement(
                        duration=float(element["duration"]),
                        increment=float(element.get("increment", 0.0)),
                        name=element.get("name", ""),
                        channels={
                            channel: (
                                bool(value) if isinstance(value, bool)
                                else shape_from_dict(value)
                            )
                            for channel, value in (element.get("channels") or {}).items()
                        },
                    )
                    for element in block.get("elements") or ()
                ),
            )
            for block in data.get("blocks") or ()
        )
        return cls(
            name=data["name"],
            blocks=blocks,
            sweep=sweep,
            rotating_frame=bool(data.get("rotating_frame", True)),
            alternating=bool(data.get("alternating", False)),
            laser_channel=data.get("laser_channel", "laser"),
            gate_channel=data.get("gate_channel", "gate"),
            ignore_lasers=tuple(data.get("ignore_lasers") or ()),
            description=data.get("description", ""),
        )

    def evolve(self, **changes: Any) -> PulseSequence:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class ChannelMap:
    """Symbolic channel -> this pulser's physical channel.

    The one piece that is genuinely rig-specific, so it lives with the
    measurement workflow's bindings rather than in the saved sequence.
    """

    mapping: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping", dict(self.mapping))

    def __getitem__(self, symbolic: str) -> str:
        try:
            return self.mapping[symbolic]
        except KeyError:
            raise SequenceError(
                f"No physical channel is bound to {symbolic!r} — bound: "
                f"{', '.join(sorted(self.mapping)) or 'nothing'}"
            ) from None

    def __contains__(self, symbolic: object) -> bool:
        return symbolic in self.mapping

    def resolve(self, sequence: PulseSequence) -> None:
        """Check every channel this sequence uses has somewhere to go."""
        missing = sorted(set(sequence.channels) - set(self.mapping))
        if missing:
            raise SequenceError(
                f"Sequence {sequence.name!r} uses channel(s) "
                f"{', '.join(missing)} with no physical channel bound"
            )
