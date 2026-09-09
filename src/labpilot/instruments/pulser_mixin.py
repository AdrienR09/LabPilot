"""The pulser contract — a device that plays a pulse sequence.

Follows `hardware_scan_mixin.py` exactly, which is this repo's one example
of a device contract that is neither read nor write and is nonetheless
fully wired: a mixin declaring real methods, a `CAPABILITY` string that
`core/device/capabilities.py` composes off the MRO, a typed wrapper in
`core/device/kinds.py`, and a plan that drives it.

## The adapter owns its own format

`upload_sequence` takes the **abstract** `PulseSequence`, not pre-sampled
arrays. This is the one deliberate departure from Qudi, whose
`write_waveform(analog_samples, digital_samples)` makes the logic layer
sample everything to dense arrays and leaves the driver to upload them.

That design is wrong for digital sequencers, and Qudi's own PulseStreamer
driver documents the symptom: it notes `waveform_length` is ill-defined
for that device because the hardware run-length-encodes identical
consecutive samples. A 20-point T1 is 120 instructions to a PulseStreamer
and 17.5 million booleans at 1 GS/s, five million of them one idle, which
the driver would then compress back into one instruction.

So each driver realises the sequence however its hardware wants:

- a PulseStreamer or PulseBlaster walks `expand()` and emits
  `(level, duration)` instructions, never building an array;
- a Tektronix AWG calls `sample()`, because its memory genuinely holds
  samples.

`core/pulse/sampling.py` is a library an adapter *may* use, not a step
imposed on everything upstream.

## Negotiation happens where the constraints live

`upload_sequence` returns a `SequenceReport` carrying what the device
actually did — the quantisation adjustments, the compiled length, the
padding. The same sequence file played on a 1 GS/s PulseStreamer and a
12 GS/s AWG quantises differently, and each says so rather than silently
differing.

## Channels are resolved at upload, not at authoring

A `ChannelMap` maps the sequence's symbolic channels (`"laser"`, `"mw"`,
`"gate"`) onto this pulser's physical ones. It comes from the measurement
workflow's bindings, which is what keeps a saved sequence independent of
any one rig's wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from labpilot.core.device.capabilities import PULSER
from labpilot.core.device.constraints import (
    Adjustment,
    Constraints,
    Quantised,
    ScalarConstraint,
)
from labpilot.core.pulse.sampling import (
    ELEMENT_LENGTH,
    SAMPLE_RATE,
    WAVEFORM_LENGTH,
    check_activation,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from labpilot.core.pulse.sequence import ChannelMap, PulseSequence

__all__ = [
    "PulserConstraints",
    "PulserMixin",
    "SequenceReport",
    "pulser_constraints",
    "quantise_elements",
]


@dataclass(frozen=True, slots=True)
class PulserConstraints:
    """What one pulser can actually play.

    The scalar half is a plain `Constraints` keyed by the names
    `core/pulse/sampling.py` consults, so a driver that fills this in gets
    rate quantisation, granularity padding and minimum-element checking
    for free.

    The structural half is what a scalar range cannot express, and
    `activation_configs` is the load-bearing one: which channels may be
    enabled *at the same time*. A PulseBlaster's channel count depends on
    its clock configuration and an AWG trades analog channels for markers,
    so a sequence must fit inside one of the sets the device offers. It is
    the constraint a naive model always omits — a mock never punishes you
    for it and real hardware will.
    """

    scalars: Constraints = field(default_factory=Constraints)
    analog_channels: tuple[str, ...] = ()
    digital_channels: tuple[str, ...] = ()
    activation_configs: tuple[frozenset[str], ...] = ()
    """Channel sets the device can have active together. Empty means
    "every channel, always", which is what a device with no such limit
    should say."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "analog_channels", tuple(self.analog_channels))
        object.__setattr__(self, "digital_channels", tuple(self.digital_channels))
        object.__setattr__(
            self, "activation_configs",
            tuple(frozenset(config) for config in self.activation_configs),
        )
        overlap = set(self.analog_channels) & set(self.digital_channels)
        if overlap:
            raise ValueError(
                f"Channel(s) {', '.join(sorted(overlap))} declared both analog "
                f"and digital"
            )
        unknown: set[str] = set()
        for config in self.activation_configs:
            unknown |= config - set(self.channels)
        if unknown:
            raise ValueError(
                f"Activation config names channel(s) {', '.join(sorted(unknown))} "
                f"this pulser does not have"
            )

    @property
    def channels(self) -> tuple[str, ...]:
        return (*self.analog_channels, *self.digital_channels)

    @property
    def sample_rate(self) -> float | None:
        """The highest rate this device supports, which is what a driver
        samples at unless told otherwise."""
        constraint = self.scalars.get(SAMPLE_RATE)
        if constraint is None:
            return None
        if constraint.allowed:
            return float(max(constraint.allowed))
        return constraint.bounds[1]

    def configs(self) -> tuple[frozenset[str], ...]:
        """`activation_configs`, with the "everything" default made
        explicit — so a caller never has to special-case the empty case."""
        return self.activation_configs or (frozenset(self.channels),)

    def check(self, sequence: PulseSequence, channels: ChannelMap) -> frozenset[str]:
        """The activation config this sequence can run in, or raise.

        Called by a driver before it compiles anything, so an impossible
        sequence fails with a message naming the channels rather than
        part-way through an upload.
        """
        return check_activation(sequence, channels, self.configs())

    def to_dict(self) -> dict[str, Any]:
        """For the REST payload and the sequence editor's channel list."""
        return {
            "analog_channels": list(self.analog_channels),
            "digital_channels": list(self.digital_channels),
            "activation_configs": [sorted(c) for c in self.configs()],
            "scalars": {
                constraint.name: {
                    "bounds": list(constraint.bounds),
                    "step": constraint.step,
                    "allowed": list(constraint.allowed) if constraint.allowed else None,
                    "unit": constraint.unit,
                }
                for constraint in self.scalars.scalars
            },
        }


def pulser_constraints(
    *,
    sample_rate: float | Iterable[float],
    analog_channels: Iterable[str] = (),
    digital_channels: Iterable[str] = (),
    granularity: int = 1,
    min_samples: int = 1,
    max_samples: int | None = None,
    min_element: float = 0.0,
    element_step: float = 0.0,
    activation_configs: Iterable[Iterable[str]] = (),
    extra: Iterable[ScalarConstraint] = (),
) -> PulserConstraints:
    """The common case, spelled once.

    `sample_rate` takes either a single fixed rate or the set a device can
    synthesise — a discrete set, which is what real hardware has and what
    Qudi's own `ScalarConstraint` (min/max/step only) cannot express.
    """
    rates = (
        (float(sample_rate),)
        if isinstance(sample_rate, (int, float))
        else tuple(float(r) for r in sample_rate)
    )
    scalars = [ScalarConstraint(SAMPLE_RATE, allowed=rates, unit="Hz"), *extra]

    # Only a device whose memory holds samples has a waveform length. An
    # instruction-based sequencer that advertised one would report
    # adjustments corresponding to nothing it actually does.
    if granularity > 1 or max_samples is not None or min_samples > 1:
        scalars.append(
            ScalarConstraint(
                WAVEFORM_LENGTH,
                bounds=(min_samples, max_samples),
                step=granularity if granularity > 1 else None,
            )
        )
    if min_element > 0 or element_step > 0:
        scalars.append(
            ScalarConstraint(
                ELEMENT_LENGTH,
                bounds=(min_element or None, None),
                step=element_step or None,
                unit="s",
            )
        )
    return PulserConstraints(
        scalars=Constraints(scalars=tuple(scalars)),
        analog_channels=tuple(analog_channels),
        digital_channels=tuple(digital_channels),
        activation_configs=tuple(activation_configs),
    )


def quantise_elements(
    intervals: Iterable[Any],
    constraints: PulserConstraints,
    minimum: float = 0.0,
) -> Quantised:
    """Snap each element's duration to this device's timing grid.

    For a sequencer that emits `(level, duration)` instructions, *this* is
    where quantisation happens — per element, against the clock — not
    against a waveform length it never allocates. It is also where the
    same sequence file legitimately differs between devices: an 8 ns grid
    and a 1 ns grid round a 20 ns pi/2 pulse differently, and each device
    says so instead of silently disagreeing.

    An element below the device's minimum is refused rather than rounded:
    a granularity mismatch is negotiable and a pulse the hardware cannot
    express is not.
    """
    from labpilot.core.pulse.sampling import SamplingError

    constraint = constraints.scalars.get(ELEMENT_LENGTH)
    adjustments: list[Adjustment] = []
    snapped = 0
    requested = 0.0
    total = 0.0

    for interval in intervals:
        duration = float(interval.duration)
        if duration <= 0:
            continue
        if minimum and duration < minimum:
            raise SamplingError(
                f"Element {interval.describe()} is {duration * 1e9:.3g} ns, "
                f"below this pulser's minimum of {minimum * 1e9:.3g} ns"
            )
        requested += duration
        if constraint is not None:
            actual, reasons = constraint.quantise(duration)
            if reasons:
                snapped += 1
            duration = float(actual)
        total += duration

    if snapped:
        step = (constraint.step if constraint else 0.0) or 0.0
        adjustments.append(
            Adjustment(
                "sequence_duration",
                f"{requested * 1e9:.6g} ns",
                f"{total * 1e9:.6g} ns",
                f"{snapped} element(s) snapped to this device's "
                f"{step * 1e9:.3g} ns timing grid",
            )
        )
    return Quantised({ELEMENT_LENGTH: total}, tuple(adjustments))


@dataclass(frozen=True, slots=True)
class SequenceReport:
    """What the device actually did with the sequence it was handed.

    Qudi's pulser interface returns a bare int or a name string, so a
    caller learns nothing about what was rounded. The whole point of
    handing over an abstract sequence is that each device may realise it
    differently, which is only useful if each device says how.
    """

    name: str
    channels: Mapping[str, str] = field(default_factory=dict)
    """Symbolic -> physical, as actually resolved for this upload."""
    points: int = 0
    readouts: int = 0
    """How many gates the counter should expect. The sequence knows this
    before it runs, which is what lets the counter be configured from it
    rather than by hand."""
    duration: float = 0.0
    quantised: Quantised = field(default_factory=lambda: Quantised({}))
    instructions: int = 0
    """Non-zero for a device that plays instructions — the honest measure
    of a digital sequencer's memory use."""
    samples: int = 0
    """Non-zero for a device whose memory holds samples."""
    activation: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "channels", dict(self.channels))

    @property
    def exact(self) -> bool:
        """Whether the device plays exactly what was asked."""
        return self.quantised.exact

    def report(self) -> str:
        """One line per adjustment, for a status bar or a log — empty when
        nothing was changed."""
        return self.quantised.report()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "channels": dict(self.channels),
            "points": self.points,
            "readouts": self.readouts,
            "duration": self.duration,
            "instructions": self.instructions,
            "samples": self.samples,
            "activation": sorted(self.activation),
            "exact": self.exact,
            "adjustments": [str(a) for a in self.quantised.adjustments],
        }


class PulserMixin:
    """A device that plays pulse sequences on named channels.

    Opt in by inheritance, the same convention `HardwareScanMixin` uses:

        class MyPulser(PulserMixin, AdapterBase): ...
    """

    CAPABILITY = PULSER

    def pulser_constraints(self) -> PulserConstraints:
        """What this device can play.

        Synchronous and answerable without hardware present, so it reaches
        the catalogue listing and the editor's channel list rather than
        only a live instrument — the same property `describe()` has.
        """
        raise NotImplementedError

    async def upload_sequence(
        self, sequence: PulseSequence, channels: ChannelMap
    ) -> SequenceReport:
        """Compile and load `sequence`, and report what was really loaded.

        Takes the abstract sequence: how it becomes instructions or
        samples is this driver's business. Does not start playing — see
        `pulser_on`, mirroring `HardwareScanMixin`'s configure/start split
        and Qudi's own non-blocking `pulser_on`.
        """
        raise NotImplementedError

    async def pulser_on(self) -> None:
        """Start playing the loaded sequence. Returns immediately."""
        raise NotImplementedError

    async def pulser_off(self) -> None:
        """Stop playing and put every channel in its idle state.

        Must be safe to call when nothing is playing: it is what an
        aborted run calls, and an abort has no way to know how far the
        run got.
        """
        raise NotImplementedError
