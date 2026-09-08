"""What the hardware will actually do with what you asked for.

`Parameter.validate` answers "is this a legal request?" and raises if not.
That is the right behaviour for a setpoint: asking a stage to travel past
its end stop is a mistake, not a negotiation.

Configuring an instrument is a different question. Hardware quantises — a
counter's bin width comes from a discrete list its clock can divide down
to, a pulser's waveform length must be a multiple of its memory
granularity, a sample rate snaps to whatever the PLL can synthesise. A
request of 1.4 ns is not illegal; it is simply going to become 1 ns. The
established answer is qudi's, whose `FastCounterInterface.configure()`
returns the binwidth, record length and gate count it *actually* set, with
the whole interface documented as "the caller MUST use the return value".

So the two are separate calls with separate jobs:

    validate  — is this legal?          raises
    quantise  — what will really happen?  reports

`quantise` never raises. It clips, snaps, and hands back every adjustment
it made, so a caller can show the user what the device did rather than
what they typed. A silently ignored request is the failure mode this
exists to prevent: it is how someone spends an afternoon wondering why a
50 ns π-pulse behaves like 48 ns.

One thing qudi's own constraints could not express, added here: a genuine
**discrete set** of allowed values. Their `ScalarConstraint` has only
min/max/step, so a device with a fixed list (a bin-width table) fakes it
with `min == max` and `step = 0`, and a device with two allowed sample
rates cannot say so at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "Adjustment",
    "Constraints",
    "Quantised",
    "ScalarConstraint",
    "scalars_from",
]


@dataclass(frozen=True, slots=True)
class Adjustment:
    """One thing the hardware could not do exactly as asked."""

    parameter: str
    requested: Any
    actual: Any
    reason: str

    def __str__(self) -> str:
        return (
            f"{self.parameter}: asked {self.requested}, got {self.actual} "
            f"({self.reason})"
        )


@dataclass(frozen=True, slots=True)
class Quantised:
    """What a configure call will really apply, and where it differs."""

    values: dict[str, Any]
    adjustments: tuple[Adjustment, ...] = ()

    @property
    def exact(self) -> bool:
        """True when the hardware can do exactly what was asked."""
        return not self.adjustments

    def __getitem__(self, name: str) -> Any:
        return self.values[name]

    def report(self) -> str:
        """One line per adjustment, for a status bar or a log."""
        return "; ".join(str(a) for a in self.adjustments)


@dataclass(frozen=True, slots=True)
class ScalarConstraint:
    """What one numeric setting may be on this particular device.

    `allowed` wins over `step` when both are given: a device that
    enumerates its legal values has already answered the question a
    granularity approximates.
    """

    name: str
    bounds: tuple[float | None, float | None] = (None, None)
    step: float | None = None
    """Granularity. The value is snapped to the nearest multiple of this,
    measured from the lower bound where there is one — a pulser's memory
    granularity, an AWG's waveform-length divisor."""
    allowed: tuple[float, ...] | None = None
    """The complete set of legal values, if the device has one. The value
    snaps to the nearest."""
    unit: str = ""
    enforce_int: bool = False

    def __post_init__(self) -> None:
        low, high = self.bounds
        if low is not None and high is not None and low > high:
            raise ValueError(
                f"Constraint {self.name!r} has inverted bounds ({low} > {high})"
            )
        if self.step is not None and self.step <= 0:
            raise ValueError(
                f"Constraint {self.name!r} has a non-positive step ({self.step})"
            )
        if self.allowed is not None:
            object.__setattr__(self, "allowed", tuple(sorted(self.allowed)))
            if not self.allowed:
                raise ValueError(
                    f"Constraint {self.name!r} allows no values at all"
                )

    def quantise(self, value: float) -> tuple[Any, list[str]]:
        """This value as the device will hold it, plus why it changed."""
        reasons: list[str] = []
        result: float = float(value)

        if self.allowed is not None:
            nearest = min(self.allowed, key=lambda candidate: abs(candidate - result))
            if nearest != result:
                reasons.append(
                    f"nearest of {len(self.allowed)} supported value(s)"
                )
            result = nearest
        else:
            low, high = self.bounds
            if low is not None and result < low:
                reasons.append(f"clipped to minimum {low}{self._suffix}")
                result = float(low)
            if high is not None and result > high:
                reasons.append(f"clipped to maximum {high}{self._suffix}")
                result = float(high)

            if self.step is not None:
                origin = float(low) if low is not None else 0.0
                steps = round((result - origin) / self.step)
                snapped = origin + steps * self.step
                # Guard the edge case where snapping leaves the bounds.
                if high is not None and snapped > high:
                    snapped -= self.step
                if low is not None and snapped < low:
                    snapped += self.step
                if not _close(snapped, result):
                    reasons.append(f"snapped to a multiple of {self.step}{self._suffix}")
                result = snapped

        if self.enforce_int:
            as_int = round(result)
            if not _close(as_int, result):
                reasons.append("rounded to a whole number")
            return as_int, reasons

        return result, reasons

    @property
    def _suffix(self) -> str:
        return f" {self.unit}" if self.unit else ""


@dataclass(frozen=True, slots=True)
class Constraints:
    """Every constraint a device places on one configure call.

    Deliberately not a `DeviceSchema`: a schema says what a parameter *is*,
    and this says what this particular unit can do with it. The same
    `bin_width_s` parameter has one meaning and a different constraint on
    every counter model.
    """

    scalars: tuple[ScalarConstraint, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)
    """Anything not expressible as a scalar range — a pulser's activation
    configs, an AWG's channel map. Carried verbatim."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "scalars", tuple(self.scalars))
        object.__setattr__(self, "extra", dict(self.extra))
        seen: set[str] = set()
        for constraint in self.scalars:
            if constraint.name in seen:
                raise ValueError(f"Constrained {constraint.name!r} twice")
            seen.add(constraint.name)

    def get(self, name: str) -> ScalarConstraint | None:
        return next((c for c in self.scalars if c.name == name), None)

    def quantise(self, request: Mapping[str, Any]) -> Quantised:
        """What this device will really apply for `request`.

        A name with no constraint passes through untouched — this reports
        what it knows about and does not pretend to police the rest.
        """
        values: dict[str, Any] = {}
        adjustments: list[Adjustment] = []

        for name, requested in request.items():
            constraint = self.get(name)
            if constraint is None:
                values[name] = requested
                continue
            actual, reasons = constraint.quantise(requested)
            values[name] = actual
            adjustments.extend(
                Adjustment(name, requested, actual, reason) for reason in reasons
            )

        return Quantised(values, tuple(adjustments))

    def names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.scalars)


def _close(a: float, b: float) -> bool:
    """Floating-point equality for values that came from arithmetic on a
    grid — without this, snapping 1e-9 to a 1e-12 step reports an
    adjustment every time purely from binary representation."""
    return abs(a - b) <= 1e-12 * max(1.0, abs(a), abs(b))


def scalars_from(constraints: Iterable[ScalarConstraint]) -> Constraints:
    """Small convenience for the common all-scalar case."""
    return Constraints(scalars=tuple(constraints))
