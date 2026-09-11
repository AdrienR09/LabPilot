"""The standard NV pulsed experiments, as parametrised generators.

Qudi's equivalent is `predefined_generate_methods/`: methods named
`generate_*`, discovered by prefix, whose `inspect.signature` defaults
*are* the schema its GUI renders. The discovery idea is good and is kept.
The schema-by-signature part is not: Qudi's GUI has to guess each
parameter's unit from substrings of its name — `'amp' in name` gives it
volts, `'tau' in name` gives it seconds — which is the single most
awkward line in that subsystem and breaks the moment someone writes
`sweep_time`.

Here a generator declares its parameters explicitly as `Parameter`
objects, the same ones an instrument uses. Units, limits and dtypes are
stated rather than inferred, and the editor renders them with the widget
code that already exists.

## The tau convention

**`tau` is the idle time between pulse edges**, not centre-to-centre.
Stated because it is the ambiguity that quietly costs a hundred
nanoseconds everywhere: with a 200 ns Rabi period a pi pulse is 100 ns,
so the two conventions differ by half of that on every point. Qudi
carries a `tau_2_pulse_spacing` helper for exactly this conversion;
`centre_to_centre()` below is the same thing, offered explicitly rather
than applied silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.pulse.sequence import (
    PulseBlock,
    PulseElement,
    PulseSequence,
    SequenceError,
    Sweep,
    linear_sweep,
    log_sweep,
)
from labpilot.core.pulse.shapes import Sin

__all__ = [
    "GENERATORS",
    "RigProfile",
    "centre_to_centre",
    "generator",
    "generator_parameters",
    "hahn_echo",
    "pulsed_odmr",
    "rabi",
    "ramsey",
    "t1",
]


@dataclass(frozen=True, slots=True)
class RigProfile:
    """The physics and wiring conventions a sequence is written against.

    Everything here is a property of the *experiment*, not of any driver,
    which is what lets a sequence be authored with no hardware present.
    Qudi's equivalent is its `generation_parameters` StatusVar, with the
    difference that its channel entries are physical (`d_ch1`) and these
    are symbolic.
    """

    rabi_period: float = 200e-9
    """One full Rabi oscillation. Everything else derives from it: a pi
    pulse is half, a pi/2 pulse a quarter."""
    mw_frequency: float = 2.87e9
    mw_amplitude: float = 0.25
    laser_length: float = 3e-6
    laser_delay: float = 700e-9
    """Time for photons to arrive and the laser to actually shut off,
    after the readout window."""
    wait_time: float = 1e-6
    """Repolarisation before the next repetition."""

    laser_channel: str = "laser"
    mw_channel: str = "mw"
    gate_channel: str | None = "gate"
    analog_mw: bool = True
    """Whether the microwave channel carries an analog shape or simply
    gates an external source. A PulseBlaster rig is digital-only and
    switches a separate microwave generator, so this is False there — and
    the sequences below are otherwise identical."""

    @property
    def pi(self) -> float:
        return self.rabi_period / 2.0

    @property
    def pi_half(self) -> float:
        return self.rabi_period / 4.0

    def mw(self, phase: float = 0.0) -> bool | Sin:
        """What the microwave channel holds during a drive element."""
        if not self.analog_mw:
            return True
        return Sin(
            amplitude=self.mw_amplitude, frequency=self.mw_frequency, phase=phase
        )

    # --- The elements every experiment shares ----------------------------

    def drive(self, length: float, *, phase: float = 0.0, increment: float = 0.0,
              name: str = "mw") -> PulseElement:
        return PulseElement(
            length, {self.mw_channel: self.mw(phase), self.laser_channel: False},
            increment=increment, name=name,
        )

    def idle(self, length: float, *, increment: float = 0.0,
             name: str = "idle") -> PulseElement:
        return PulseElement(length, {self.laser_channel: False},
                            increment=increment, name=name)

    def readout(self, name: str = "readout") -> tuple[PulseElement, ...]:
        """Laser on with the counter gated, then the delay that lets the
        photons arrive, then repolarisation. Three elements because the
        gate must close before the laser does."""
        channels: dict[str, Any] = {self.laser_channel: True}
        if self.gate_channel:
            channels[self.gate_channel] = True
        return (
            PulseElement(self.laser_length, channels, name=name),
            self.idle(self.laser_delay, name="delay"),
            self.idle(self.wait_time, name="wait"),
        )

    def polarise(self, name: str = "init") -> PulseElement:
        """Laser on with the counter *not* gated — initialisation, not a
        measurement."""
        return PulseElement(
            self.laser_length, {self.laser_channel: True}, name=name,
        )


def centre_to_centre(tau: float, profile: RigProfile) -> float:
    """Convert a centre-to-centre pulse spacing into the idle time these
    generators take, by subtracting the pulse that sits between."""
    return max(tau - profile.pi, 0.0)


#: Every registered generator, by name — what the editor lists.
GENERATORS: dict[str, Callable[..., PulseSequence]] = {}
_PARAMETERS: dict[str, tuple[Parameter, ...]] = {}


def generator(*params: Parameter) -> Callable[[Callable[..., PulseSequence]], Callable[..., PulseSequence]]:
    """Register a sequence generator and declare its parameters.

    Explicit `Parameter`s rather than signature introspection, so a unit
    is stated rather than guessed from the parameter's name.
    """

    def decorate(fn: Callable[..., PulseSequence]) -> Callable[..., PulseSequence]:
        GENERATORS[fn.__name__] = fn
        _PARAMETERS[fn.__name__] = params
        return fn

    return decorate


def generator_parameters(name: str) -> tuple[Parameter, ...]:
    """What this generator can be configured with — the editor builds its
    controls from exactly this."""
    if name not in _PARAMETERS:
        raise SequenceError(
            f"No pulse generator named {name!r} — known: "
            f"{', '.join(sorted(GENERATORS)) or 'none'}"
        )
    return _PARAMETERS[name]


def _time(name: str, description: str = "") -> Parameter:
    return Parameter(
        name, unit="s", role=ParamRole.SETTING, settable=True, readable=False,
        limits=(0.0, None), description=description,
    )


def _points(description: str = "How many swept points") -> Parameter:
    return Parameter(
        "points", dtype="i8", role=ParamRole.SETTING, settable=True,
        readable=False, limits=(1, None), description=description,
    )


# --- The four experiments --------------------------------------------------


@generator(
    _time("tau_start", "Microwave pulse length at the first point"),
    _time("tau_step", "Added to the pulse length each point"),
    _points(),
)
def rabi(
    profile: RigProfile,
    tau_start: float = 20e-9,
    tau_step: float = 20e-9,
    points: int = 50,
) -> PulseSequence:
    """Drive for a varying time, then read out.

    The calibration every other experiment depends on: the first minimum
    gives the pi pulse, and twice that is `rabi_period`.
    """
    block = PulseBlock(
        "rabi",
        (profile.drive(tau_start, increment=tau_step), *profile.readout()),
        repetitions=points,
    )
    return PulseSequence(
        "rabi", (block,),
        sweep=linear_sweep("tau", tau_start, tau_step, points),
        rotating_frame=True,
        laser_channel=profile.laser_channel,
        gate_channel=profile.gate_channel,
        description="Rabi oscillation — calibrates the pi pulse.",
    )


@generator(
    _time("tau_start", "Free evolution at the first point"),
    _time("tau_step", "Added to the free evolution each point"),
    _points(),
)
def ramsey(
    profile: RigProfile,
    tau_start: float = 50e-9,
    tau_step: float = 100e-9,
    points: int = 50,
) -> PulseSequence:
    """pi/2 — free evolution — pi/2, reading out along +x and -x.

    Measures T2*, the inhomogeneous dephasing time. Alternating, because
    the signal is the *difference* between the two final-pulse phases; a
    single-phase Ramsey rides on a drifting readout level.
    """
    block = PulseBlock(
        "ramsey",
        (
            profile.drive(profile.pi_half, name="pi/2"),
            profile.idle(tau_start, increment=tau_step, name="tau"),
            profile.drive(profile.pi_half, phase=0.0, name="pi/2 (+x)"),
            *profile.readout("signal"),
            profile.drive(profile.pi_half, name="pi/2"),
            profile.idle(tau_start, increment=tau_step, name="tau"),
            profile.drive(profile.pi_half, phase=180.0, name="pi/2 (-x)"),
            *profile.readout("reference"),
        ),
        repetitions=points,
    )
    return PulseSequence(
        "ramsey", (block,),
        sweep=linear_sweep("tau", tau_start, tau_step, points),
        rotating_frame=True,
        alternating=True,
        laser_channel=profile.laser_channel,
        gate_channel=profile.gate_channel,
        description="Ramsey fringes — measures T2*.",
    )


@generator(
    _time("tau_start", "Half the free evolution, at the first point"),
    _time("tau_step", "Added to each half-evolution each point"),
    _points(),
)
def hahn_echo(
    profile: RigProfile,
    tau_start: float = 100e-9,
    tau_step: float = 500e-9,
    points: int = 40,
) -> PulseSequence:
    """pi/2 — tau — pi — tau — pi/2.

    The pi pulse refocuses static detuning, so this measures T2 rather
    than T2*. `tau` is each half; total free evolution is twice it, which
    is the axis to plot against if you want a decay constant that matches
    the literature.
    """
    def arm(phase: float, label: str) -> tuple[PulseElement, ...]:
        return (
            profile.drive(profile.pi_half, name="pi/2"),
            profile.idle(tau_start, increment=tau_step, name="tau"),
            profile.drive(profile.pi, name="pi"),
            profile.idle(tau_start, increment=tau_step, name="tau"),
            profile.drive(profile.pi_half, phase=phase, name=f"pi/2 ({label})"),
        )

    block = PulseBlock(
        "hahn_echo",
        (
            *arm(0.0, "+x"), *profile.readout("signal"),
            *arm(180.0, "-x"), *profile.readout("reference"),
        ),
        repetitions=points,
    )
    return PulseSequence(
        "hahn_echo", (block,),
        sweep=linear_sweep("tau", tau_start, tau_step, points),
        rotating_frame=True,
        alternating=True,
        laser_channel=profile.laser_channel,
        gate_channel=profile.gate_channel,
        description="Hahn echo — measures T2, refocusing static detuning.",
    )


@generator(
    _time("tau_start", "Shortest relaxation time"),
    _time("tau_stop", "Longest relaxation time"),
    _points("How many points, logarithmically spaced"),
)
def t1(
    profile: RigProfile,
    tau_start: float = 1e-6,
    tau_stop: float = 5e-3,
    points: int = 20,
) -> PulseSequence:
    """Polarise, wait, read out — spin-lattice relaxation.

    Logarithmically spaced, because the decay spans decades and linear
    spacing spends almost every point after the signal has gone. That
    makes this the one experiment an `increment` cannot express: each
    point needs its own block, which is also why a hardware sequencer
    earns its keep here — 5 ms of idle is one looped instruction rather
    than five million samples.
    """
    sweep = log_sweep("tau", tau_start, tau_stop, points)
    blocks = tuple(
        PulseBlock(
            f"t1_{index}",
            (
                profile.polarise(),
                profile.idle(profile.wait_time, name="settle"),
                profile.idle(tau, name="tau"),
                *profile.readout(),
            ),
        )
        for index, tau in enumerate(sweep.values)
    )
    return PulseSequence(
        "t1", blocks,
        sweep=sweep,
        rotating_frame=False,
        laser_channel=profile.laser_channel,
        gate_channel=profile.gate_channel,
        description="T1 relaxation — logarithmically spaced.",
    )


def _frequency(name: str, description: str = "") -> Parameter:
    return Parameter(
        name, unit="Hz", role=ParamRole.SETTING, settable=True, readable=False,
        limits=(0.0, None), description=description,
    )


@generator(
    _frequency("start", "Microwave frequency at the first point"),
    _frequency("stop", "Microwave frequency at the last point"),
    _points(),
)
def pulsed_odmr(
    profile: RigProfile,
    start: float = 2.82e9,
    stop: float = 2.92e9,
    points: int = 51,
) -> PulseSequence:
    """A pi pulse at a varying frequency, then read out.

    The one experiment here whose sweep the pulser does **not** play. The
    pattern is fixed — polarise, drive for a pi pulse, read out — and what
    changes between passes is the microwave source's frequency, which no
    pulse duration can encode. So the sequence declares
    `Sweep(parameter="frequency")` and `PulsedMeasurementPlan` steps a
    bound source through the values, one pass per point.

    That also makes it the reason `Sweep.parameter` exists at all: without
    it, "sweep 51 points" and "produce one readout per pass" look like a
    contradiction, and validation would refuse every pulsed ODMR.

    Pulsed rather than continuous-wave: a pi pulse at fixed power gives a
    linewidth set by the pulse, not by the drive strength, so the dip is
    narrow and its centre is the transition frequency rather than a
    power-broadened approximation of it.
    """
    if points < 1:
        raise SequenceError(f"A sweep needs at least one point, got {points}")
    block = PulseBlock(
        "pulsed_odmr",
        (
            profile.polarise(),
            profile.idle(profile.wait_time, name="settle"),
            profile.drive(profile.pi, name="pi"),
            *profile.readout(),
        ),
    )
    return PulseSequence(
        "pulsed_odmr", (block,),
        sweep=Sweep(
            "frequency",
            tuple(float(v) for v in np.linspace(start, stop, int(points))),
            unit="Hz",
            parameter="frequency",
        ),
        rotating_frame=False,
        laser_channel=profile.laser_channel,
        gate_channel=profile.gate_channel,
        description=(
            "Pulsed ODMR — a pi pulse swept in frequency. The source steps; "
            "the sequence does not change."
        ),
    )


def build(name: str, profile: RigProfile | None = None, **params: Any) -> PulseSequence:
    """Generate a sequence by name, validating it before returning.

    The one entry point the editor and a script both use, so a sequence
    can never be saved in a state the pulser would refuse.
    """
    if name not in GENERATORS:
        raise SequenceError(
            f"No pulse generator named {name!r} — known: "
            f"{', '.join(sorted(GENERATORS)) or 'none'}"
        )
    declared = {p.name for p in generator_parameters(name)}
    unknown = set(params) - declared
    if unknown:
        raise SequenceError(
            f"{name} takes no parameter(s) {', '.join(sorted(unknown))} — "
            f"it declares: {', '.join(sorted(declared)) or 'none'}"
        )
    validated = {
        p.name: p.validate(params[p.name])
        for p in generator_parameters(name)
        if p.name in params
    }
    sequence = GENERATORS[name](profile or RigProfile(), **validated)
    sequence.validate()
    return sequence
