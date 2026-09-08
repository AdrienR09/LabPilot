"""Analog pulse shapes — what an analog channel does during one element.

A digital channel is high or low for the whole element, which a `bool`
says completely. An analog channel needs a function of time, and that
function needs parameters: a sine's amplitude, frequency and phase, a
chirp's start and stop frequency.

Qudi's equivalent (`sampling_functions.py`) declares those parameters as a
class-level `dict` of dicts — `{'unit', 'init', 'min', 'max', 'type'}` per
parameter — and its GUI switches on `type` to pick a widget. The idea is
right and the shape of it is redundant here: this framework already has an
object for "a named, typed, bounded quantity with a unit", and the
settings tree already renders one. So a shape's parameters *are*
`Parameter` objects, and the same widget code that builds an instrument's
settings dock builds a shape's editor with nothing new written.

## Units and normalisation

`sample()` returns **volts**, not a normalised ±1. Qudi normalises in its
logic layer by dividing by Vpp/2 before handing samples to the driver,
which puts a device-specific fact (that channel's amplitude setting) into
the device-independent layer. Here the driver normalises, because the
driver is what knows its own Vpp — see `PulserMixin` in the plan.

## Time base

`t` is **absolute** time in seconds, so a sine's phase is continuous
across element boundaries when the sequence asks for a rotating frame.
Shapes that are inherently element-local — a chirp sweeping from one
frequency to another over *this* element — take their zero from `t[0]`,
so an element must be sampled in one call rather than in chunks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

import numpy as np

from labpilot.core.device.parameter import Parameter, ParamRole

__all__ = [
    "DC",
    "SHAPES",
    "Chirp",
    "Gauss",
    "Idle",
    "Shape",
    "Sin",
    "register_shape",
    "shape_from_dict",
    "shape_to_dict",
]


@runtime_checkable
class Shape(Protocol):
    """One analog channel's behaviour during one pulse element."""

    #: What this shape can be configured with. Declared per class.
    params: ClassVar[tuple[Parameter, ...]]

    def sample(self, t: np.ndarray, duration: float) -> np.ndarray:
        """Volts at each absolute time in `t`, for an element of
        `duration` seconds."""
        ...


#: Every registered shape, by name. A config file or a saved sequence
#: names a shape by its key here.
SHAPES: dict[str, type] = {}


def register_shape(cls: type) -> type:
    """Class decorator — registering *is* defining, as with UI components."""
    SHAPES[cls.__name__] = cls
    return cls


def _v(name: str, unit: str = "V", **kwargs: Any) -> Parameter:
    """A shape parameter. Settable and not readable: a shape is
    configuration, never a measurement."""
    return Parameter(
        name, unit=unit, role=ParamRole.SETTING, settable=True,
        readable=False, **kwargs,
    )


@register_shape
@dataclass(frozen=True, slots=True)
class Idle:
    """Nothing at all. The default for an analog channel."""

    params: ClassVar[tuple[Parameter, ...]] = ()

    def sample(self, t: np.ndarray, duration: float) -> np.ndarray:
        return np.zeros(len(t), dtype=np.float64)


@register_shape
@dataclass(frozen=True, slots=True)
class DC:
    """A constant level — a bias, or an analog trigger."""

    voltage: float = 0.0

    params: ClassVar[tuple[Parameter, ...]] = (_v("voltage"),)

    def sample(self, t: np.ndarray, duration: float) -> np.ndarray:
        return np.full(len(t), float(self.voltage), dtype=np.float64)


@register_shape
@dataclass(frozen=True, slots=True)
class Sin:
    """The workhorse: a microwave drive pulse.

    Phase is measured in absolute time, so successive pulses stay coherent
    when the sequence is in a rotating frame — which is what makes Ramsey
    and Hahn echo work at all.
    """

    amplitude: float = 0.0
    frequency: float = 2.87e9
    phase: float = 0.0
    """Degrees. The phase difference between two pi/2 pulses is how an
    alternating sequence takes its reference, so this is swept far more
    often than it is left alone."""

    params: ClassVar[tuple[Parameter, ...]] = (
        _v("amplitude", limits=(0.0, None)),
        _v("frequency", unit="Hz", limits=(0.0, None)),
        _v("phase", unit="deg"),
    )

    def sample(self, t: np.ndarray, duration: float) -> np.ndarray:
        return self.amplitude * np.sin(
            2 * np.pi * self.frequency * t + np.deg2rad(self.phase)
        )


@register_shape
@dataclass(frozen=True, slots=True)
class Gauss:
    """A Gaussian envelope on a carrier — a shaped pulse, for suppressing
    the spectral sidebands a hard rectangular pulse produces."""

    amplitude: float = 0.0
    frequency: float = 2.87e9
    phase: float = 0.0
    sigma_fraction: float = 0.25
    """Envelope width as a fraction of the element's duration, so a shape
    stays correct when the element it sits in is swept."""

    params: ClassVar[tuple[Parameter, ...]] = (
        _v("amplitude", limits=(0.0, None)),
        _v("frequency", unit="Hz", limits=(0.0, None)),
        _v("phase", unit="deg"),
        _v("sigma_fraction", unit="", limits=(0.01, 1.0)),
    )

    def sample(self, t: np.ndarray, duration: float) -> np.ndarray:
        if len(t) == 0:
            return np.zeros(0, dtype=np.float64)
        local = t - t[0]
        centre = duration / 2.0
        sigma = max(duration * self.sigma_fraction, 1e-18)
        envelope = np.exp(-0.5 * ((local - centre) / sigma) ** 2)
        carrier = np.sin(2 * np.pi * self.frequency * t + np.deg2rad(self.phase))
        return self.amplitude * envelope * carrier


@register_shape
@dataclass(frozen=True, slots=True)
class Chirp:
    """A linear frequency sweep across this element — for LZSM passage and
    broadband inversion.

    Inherently element-local: the sweep starts where the element starts,
    so this one takes its zero from `t[0]` rather than absolute time.
    """

    amplitude: float = 0.0
    start_frequency: float = 2.80e9
    stop_frequency: float = 2.94e9
    phase: float = 0.0

    params: ClassVar[tuple[Parameter, ...]] = (
        _v("amplitude", limits=(0.0, None)),
        _v("start_frequency", unit="Hz", limits=(0.0, None)),
        _v("stop_frequency", unit="Hz", limits=(0.0, None)),
        _v("phase", unit="deg"),
    )

    def sample(self, t: np.ndarray, duration: float) -> np.ndarray:
        if len(t) == 0:
            return np.zeros(0, dtype=np.float64)
        local = t - t[0]
        if duration <= 0:
            return np.zeros(len(t), dtype=np.float64)
        rate = (self.stop_frequency - self.start_frequency) / duration
        # Instantaneous phase is the integral of the instantaneous
        # frequency, which is why this is quadratic in local time rather
        # than the naive f(t)*t.
        angle = 2 * np.pi * (self.start_frequency * local + 0.5 * rate * local**2)
        return self.amplitude * np.sin(angle + np.deg2rad(self.phase))


def shape_from_dict(data: Any) -> Shape:
    """Rebuild a shape from its serialised form.

    A saved sequence is data, so a shape has to survive a round trip
    through JSON without pickle — which is what lets a sequence be
    authored on one machine and run on another.
    """
    if isinstance(data, (bool, np.bool_)):
        raise TypeError("A digital level is a bool, not a shape")
    if not isinstance(data, dict):
        raise TypeError(f"Cannot read a shape from {type(data).__name__}")
    name = data.get("shape")
    cls = SHAPES.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown pulse shape {name!r} — known shapes are "
            f"{', '.join(sorted(SHAPES))}"
        )
    declared = {p.name for p in cls.params}
    unknown = set(data) - declared - {"shape"}
    if unknown:
        raise ValueError(
            f"{name} has no parameter(s) {', '.join(sorted(unknown))} — "
            f"it declares: {', '.join(sorted(declared)) or 'none'}"
        )
    return cls(**{k: v for k, v in data.items() if k != "shape"})


def shape_to_dict(shape: Shape) -> dict[str, Any]:
    """The serialised form of a shape: its name plus its declared
    parameters, and nothing else."""
    return {
        "shape": type(shape).__name__,
        **{p.name: getattr(shape, p.name) for p in type(shape).params},
    }
