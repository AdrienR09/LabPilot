"""Turning a sequence into dense arrays — for the drivers that need them.

This is **a library an adapter may use, not a step imposed on everything
upstream**, and that is the one real departure from Qudi's architecture in
the pulsed subsystem.

Qudi's pulser interface is `write_waveform(analog_samples,
digital_samples)`, so its logic layer samples every sequence to dense
arrays and leaves each driver to upload them. For a true AWG that is
exactly right. For a digital sequencer it is badly wrong, and Qudi's own
PulseStreamer driver documents the symptom: it notes that
`waveform_length` is ill-defined for that device because the hardware
run-length-encodes identical consecutive samples. A 5 ms idle at 1 GS/s
becomes five million booleans that the driver then compresses back into
one instruction.

So `PulserMixin.upload_sequence` takes the *abstract* sequence, and a
driver reaches for whichever of these it needs:

- `expand()` — the sequence flattened into absolute-timed intervals.
  A PulseStreamer or PulseBlaster emits `(level, duration)` straight from
  this and never samples anything.
- `sample()` — dense float arrays per analog channel and bool arrays per
  digital one. A Tektronix AWG needs these because its memory holds
  samples.

## Absolute-time rounding

Bin edges come from `round(cumulative_time * sample_rate)`, never from
accumulating rounded per-element lengths. With thousands of elements the
naive version drifts: an element whose length is 2.5 samples rounds to 3
every time, and a Rabi's last point ends up a microsecond late. Rounding
the *cumulative* time bounds the error at half a sample for the whole
sequence, however long it is.

## Where the shapes get their time

`rotating_frame` decides. When true — the default, and required for
Ramsey and Hahn echo — a shape is sampled at absolute time, so a sine's
phase is continuous across element boundaries and two pi/2 pulses
separated by an idle stay coherent. When false, each element restarts at
zero, which is what you want when the drive is phase-locked to the pulse
rather than to the lab clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.device.constraints import Adjustment, Quantised
from labpilot.core.pulse.sequence import SequenceError
from labpilot.core.pulse.shapes import Shape

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    from labpilot.core.device.constraints import Constraints
    from labpilot.core.pulse.sequence import ChannelMap, PulseSequence

__all__ = [
    "ELEMENT_LENGTH",
    "SAMPLE_RATE",
    "WAVEFORM_LENGTH",
    "Interval",
    "Sampled",
    "SamplingError",
    "Segment",
    "check_activation",
    "expand",
    "sample",
    "shots",
    "timing_diagram",
]

#: The constraint names `sample()` consults. A driver that names its
#: constraints these gets quantisation and padding for free; one that does
#: not simply gets no adjustments reported.
SAMPLE_RATE = "sample_rate"
WAVEFORM_LENGTH = "waveform_length"
"""In *samples*: `bounds` are the minimum and maximum a waveform may be,
`step` is the memory granularity it must be a multiple of."""
ELEMENT_LENGTH = "element_length"
"""In *seconds*: `bounds[0]` is the shortest interval the device can hold.
Below it, the hardware cannot express the sequence at all."""


class SamplingError(SequenceError):
    """A sequence this device cannot play, however it is rounded.

    Distinct from an adjustment: a granularity mismatch is negotiable and
    gets reported, but an element shorter than the hardware's minimum
    instruction is not.
    """


@dataclass(frozen=True, slots=True)
class Interval:
    """One element, resolved to absolute time on one repetition.

    `expand()` produces these in play order. Everything a driver needs to
    emit an instruction is here, with the block/repetition provenance kept
    so an error can say *which* play of which block was the problem.
    """

    start: float
    """Seconds from the start of the sequence."""
    duration: float
    channels: Mapping[str, bool | Shape] = field(default_factory=dict)
    name: str = ""
    block: str = ""
    repetition: int = 0

    @property
    def end(self) -> float:
        return self.start + self.duration

    def level(self, channel: str) -> bool:
        """Whether a digital channel is high during this interval."""
        return self.channels.get(channel) is True

    def shape(self, channel: str) -> Shape | None:
        value = self.channels.get(channel)
        return value if isinstance(value, Shape) else None

    def describe(self) -> str:
        """For an error message — where in the sequence this interval is."""
        where = f"{self.block}[{self.repetition}]" if self.block else "sequence"
        return f"{self.name or '<unnamed>'} in {where}"


@dataclass(frozen=True, slots=True)
class Segment:
    """One channel doing one thing over one interval — a box on a diagram."""

    channel: str
    start: float
    stop: float
    level: float
    """1.0 for a digital high; the shape's amplitude in volts for analog."""
    shape: str = ""
    """The shape's class name, empty for a digital channel."""
    name: str = ""
    """The element's name — what the diagram labels the box with."""

    @property
    def duration(self) -> float:
        return self.stop - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "start": self.start,
            "stop": self.stop,
            "level": self.level,
            "shape": self.shape,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class Sampled:
    """A sequence as arrays, plus what the device had to change to hold it."""

    analog: Mapping[str, np.ndarray]
    """Volts per sample, per analog channel. Normalising against a
    channel's Vpp is the driver's job — only the driver knows its own."""
    digital: Mapping[str, np.ndarray]
    """One bool per sample, per digital channel."""
    sample_rate: float
    """What was actually used, after quantisation — not what was asked."""
    quantised: Quantised = field(default_factory=lambda: Quantised({}))
    padding: int = 0
    """Samples appended to satisfy the memory granularity, all idle."""
    readouts: tuple[tuple[int, int], ...] = ()
    """`(start, stop)` sample index of each readout window, in play order.
    The gated counter's gates, in the sampled sequence's own coordinates."""

    @property
    def length(self) -> int:
        """Total samples, padding included."""
        for array in (*self.analog.values(), *self.digital.values()):
            return len(array)
        return 0

    @property
    def duration(self) -> float:
        return self.length / self.sample_rate if self.sample_rate else 0.0

    @property
    def channels(self) -> frozenset[str]:
        return frozenset(self.analog) | frozenset(self.digital)

    def report(self) -> str:
        return self.quantised.report()


def expand(sequence: PulseSequence) -> Iterator[Interval]:
    """Flatten a sequence into absolute-timed intervals, in play order.

    This is where `increment` is finally applied: on repetition *n* of a
    block, every element lasts `duration + n * increment`. A driver that
    emits instructions rather than samples needs nothing else.

    A generator, because a long T1 expands to a great many intervals and
    a driver streams them out one at a time anyway.
    """
    time = 0.0
    for block in sequence.blocks:
        for repetition in range(block.repetitions):
            for element in block.elements:
                duration = element.duration_at(repetition)
                yield Interval(
                    start=time,
                    duration=duration,
                    channels=element.channels,
                    name=element.name,
                    block=block.name,
                    repetition=repetition,
                )
                time += duration


def shots(sequence: PulseSequence) -> Iterator[list[Interval]]:
    """One pass through the sequence per swept point, times from zero.

    A "shot" is what happens at one point of the sweep: for a Rabi, one
    repetition of its single block; for a T1, one of its twenty blocks.
    Both are the *n*-th thing the experiment does, which is the unit an
    editor previews and a diagram draws — a whole 50-point Rabi as one
    picture shows nothing.
    """
    for block in sequence.blocks:
        for repetition in range(block.repetitions):
            time = 0.0
            shot: list[Interval] = []
            for element in block.elements:
                duration = element.duration_at(repetition)
                shot.append(
                    Interval(
                        start=time,
                        duration=duration,
                        channels=element.channels,
                        name=element.name,
                        block=block.name,
                        repetition=repetition,
                    )
                )
                time += duration
            yield shot


def timing_diagram(sequence: PulseSequence, point: int = 0) -> list[Segment]:
    """One point of the sweep as drawable segments, one list per channel.

    Boxes, not samples. A 2.87 GHz carrier inside a 100 ns pulse is 287
    cycles — sampling it for a diagram either aliases into nonsense or
    costs more points than a plot can carry, and neither tells the author
    anything they were looking for. What a sequence editor needs to show
    is *when each channel is doing something and how hard*, which is
    exactly a box per element. Qudi's editor draws the same picture.

    So this stays exact at any zoom, costs two numbers per element, and
    survives a JSON round trip to a browser.
    """
    every = list(shots(sequence))
    if not every:
        return []
    if not 0 <= point < len(every):
        raise SamplingError(
            f"Sequence {sequence.name!r} has {len(every)} point(s); there is "
            f"no point {point}"
        )

    segments: list[Segment] = []
    for interval in every[point]:
        for channel, value in sorted(interval.channels.items()):
            if isinstance(value, Shape):
                level = float(
                    getattr(value, "amplitude", getattr(value, "voltage", 1.0))
                )
                shape = type(value).__name__
            elif value:
                level, shape = 1.0, ""
            else:
                continue  # A channel that is low draws nothing.
            segments.append(
                Segment(
                    channel=channel,
                    start=interval.start,
                    stop=interval.end,
                    level=level,
                    shape=shape,
                    name=interval.name,
                )
            )
    return segments


def sample(
    sequence: PulseSequence,
    sample_rate: float,
    constraints: Constraints | None = None,
) -> Sampled:
    """The sequence as dense arrays at `sample_rate`.

    Only for drivers whose hardware genuinely holds samples. A digital
    sequencer should use `expand()` instead and never build these arrays.

    Constraints are optional and consulted by name (`sample_rate`,
    `element_length`, `waveform_length`). The rate is quantised first,
    since every bin edge depends on it; the total is then padded up to the
    memory granularity with idle samples — Qudi's trick, and the reason
    padding is appended rather than distributed.
    """
    sequence.validate()

    rate, adjustments = _rate(sample_rate, constraints)
    minimum = _minimum_element(constraints)

    intervals = list(expand(sequence))
    total_bins = round(sequence.duration * rate)
    length, padding, pad_adjustments = _pad(total_bins, constraints)
    adjustments.extend(pad_adjustments)

    analog_names = sorted({c for i in intervals for c in i.channels if i.shape(c)})
    digital_names = sorted(
        {
            channel
            for interval in intervals
            for channel, value in interval.channels.items()
            if not isinstance(value, Shape)
        }
    )
    analog = {name: np.zeros(length, dtype=np.float64) for name in analog_names}
    digital = {name: np.zeros(length, dtype=bool) for name in digital_names}

    for interval in intervals:
        start = round(interval.start * rate)
        stop = round(interval.end * rate)
        if interval.duration > 0:
            if minimum is not None and interval.duration < minimum:
                raise SamplingError(
                    f"Element {interval.describe()} is {interval.duration * 1e9:.3g} ns, "
                    f"below this device's minimum of {minimum * 1e9:.3g} ns"
                )
            if stop == start:
                raise SamplingError(
                    f"Element {interval.describe()} is {interval.duration * 1e9:.3g} ns, "
                    f"shorter than one sample at {rate / 1e9:.4g} GS/s"
                )
        if stop <= start:
            continue

        for channel, value in interval.channels.items():
            if isinstance(value, Shape):
                # Absolute time in a rotating frame, element-local otherwise
                # — the difference between a coherent Ramsey and a wrong one.
                base = start if sequence.rotating_frame else 0
                t = (np.arange(stop - start, dtype=np.float64) + base) / rate
                analog[channel][start:stop] = value.sample(t, interval.duration)
            else:
                digital[channel][start:stop] = bool(value)

    return Sampled(
        analog=analog,
        digital=digital,
        sample_rate=rate,
        quantised=Quantised({SAMPLE_RATE: rate}, tuple(adjustments)),
        padding=padding,
        readouts=_windows(digital.get(sequence.readout_channel)),
    )


def check_activation(
    sequence: PulseSequence,
    channels: ChannelMap,
    activation_configs: Iterable[Iterable[str]],
) -> frozenset[str]:
    """The activation config this sequence can run in, or raise.

    A pulser does not expose every channel at once: a PulseBlaster's
    channel count depends on its clock configuration, and an AWG trades
    analog channels for markers. `activation_configs` is the list of
    channel sets the device supports simultaneously, and a sequence must
    fit inside one of them.

    Qudi's most load-bearing constraint, and the one a naive model always
    omits — a mock will never punish you for it and a PulseBlaster will.
    Returns the first config that fits, so a driver can select it.
    """
    channels.resolve(sequence)
    needed = frozenset(channels[symbolic] for symbolic in sequence.channels)

    configs = [frozenset(config) for config in activation_configs]
    for config in configs:
        if needed <= config:
            return config

    offered = " | ".join(sorted(", ".join(sorted(c)) for c in configs)) or "none"
    raise SamplingError(
        f"Sequence {sequence.name!r} needs channels "
        f"{', '.join(sorted(needed))} active together; this device offers: "
        f"{offered}"
    )


# --- Internals -------------------------------------------------------------


def _rate(requested: float, constraints: Constraints | None) -> tuple[float, list[Adjustment]]:
    """The sample rate the device will really run at.

    Quantised before anything else, because every bin edge is computed
    from it — sampling at the requested rate and fixing it up afterwards
    would put every element in the wrong place.
    """
    if requested <= 0:
        raise SamplingError(f"Sample rate must be positive, got {requested}")
    constraint = constraints.get(SAMPLE_RATE) if constraints else None
    if constraint is None:
        return float(requested), []
    actual, reasons = constraint.quantise(requested)
    return float(actual), [
        Adjustment(SAMPLE_RATE, requested, actual, reason) for reason in reasons
    ]


def _minimum_element(constraints: Constraints | None) -> float | None:
    constraint = constraints.get(ELEMENT_LENGTH) if constraints else None
    return None if constraint is None else constraint.bounds[0]


def _pad(bins: int, constraints: Constraints | None) -> tuple[int, int, list[Adjustment]]:
    """Total length after padding up to the memory granularity.

    Rounds *up*, never to the nearest: snapping down would truncate the
    last element, and a sequence whose final readout is half a window long
    fails in a way that looks like a physics result.
    """
    constraint = constraints.get(WAVEFORM_LENGTH) if constraints else None
    if constraint is None:
        return bins, 0, []

    low, high = constraint.bounds
    length = bins
    if low is not None and length < low:
        length = int(low)
    if constraint.step:
        step = int(constraint.step)
        if step > 1 and length % step:
            length += step - (length % step)
    if high is not None and length > high:
        raise SamplingError(
            f"Sequence needs {length} samples; this device holds {int(high)}"
        )

    padding = length - bins
    adjustments = (
        [
            Adjustment(
                WAVEFORM_LENGTH, bins, length,
                f"padded with {padding} idle sample(s) for this device's "
                f"memory granularity",
            )
        ]
        if padding
        else []
    )
    return length, padding, adjustments


def _windows(trace: Any) -> tuple[tuple[int, int], ...]:
    """Every high run in a digital trace, as `(start, stop)` sample indices."""
    if trace is None or len(trace) == 0:
        return ()
    edges = np.diff(np.concatenate(([False], trace, [False])).astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1)
    return tuple(zip(starts.tolist(), stops.tolist(), strict=True))
