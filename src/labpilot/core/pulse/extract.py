"""Finding the readout window inside a raw gated trace.

A gated counter hands back a 2-D `(readout, time_bin)` record. Somewhere
inside each record is the laser pulse — a few hundred nanoseconds of
bright fluorescence decaying towards a repolarised steady state — and
everything outside it is dark counts. Extraction is the step that says
*where*, so analysis can average the right bins.

## Why this is not just "sum the record"

The photons that carry the spin state arrive in the **leading edge** of
the readout. Averaging the whole record dilutes a 25% contrast into
single digits, and averaging a window that starts before the laser does
mixes in dark counts that shift with the counter's own background rate.
The window has to be found from the data, per measurement, because the
laser delay is a property of the rig's cabling and shifts when anyone
moves an AOM.

## One window, not one per readout

The window is found once, on the record summed over every readout, and
then applied to all of them. That is a physical statement rather than a
shortcut: every gate is raised by the same pulser edge, so the laser
pulse sits at the same offset in every record. Summing first is what
makes the edge findable at all in the first seconds of a run, when a
single readout holds a handful of photons.

## Parameters are per method, not shared

Each extractor declares its own `Parameter` objects and sees only those.
Qudi merges every extraction method's keyword defaults into one flat
dict shared by all of them, which forces the rule — documented in its own
source — that no two methods may share a keyword argument of different
default type, and a type-based `type(a) == type(b)` check to enforce it.
That rule does not exist here because the dict is not shared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.device.parameter import Parameter, ParamRole

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "EXTRACTORS",
    "Extraction",
    "ExtractionError",
    "conv_deriv",
    "extract",
    "extractor",
    "extractor_parameters",
    "threshold",
]


class ExtractionError(Exception):
    """A trace that cannot be extracted from, and why."""


@dataclass(frozen=True, slots=True)
class Extraction:
    """The readout windows cut out of a raw record.

    `pulses` is what analysis works on: one row per readout, one column
    per time bin *inside* the laser pulse, so a signal window measured
    from bin zero means "from the start of the laser pulse" regardless of
    where in the record that turned out to be.
    """

    pulses: np.ndarray
    """`(readouts, window_bins)` counts inside the laser pulse."""
    window: tuple[int, int]
    """Where the pulse was found in the raw record, as `[start, stop)`."""
    bin_width_s: float
    profile: np.ndarray
    """The record summed over every readout — what the window was found
    in, and what a view draws the window over."""
    found: bool = True
    """False when there was nothing to find (an all-dark trace on the
    first poll of a run), in which case the window is the whole record."""
    method: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def readouts(self) -> int:
        return int(self.pulses.shape[0]) if self.pulses.ndim == 2 else 0

    @property
    def bins(self) -> int:
        return int(self.pulses.shape[1]) if self.pulses.ndim == 2 else 0

    @property
    def duration(self) -> float:
        """How long the extracted window is, in seconds."""
        return self.bins * self.bin_width_s

    @property
    def times(self) -> np.ndarray:
        """Time of each column, measured from the start of the pulse."""
        return np.arange(self.bins, dtype=float) * self.bin_width_s

    def to_dict(self) -> dict[str, Any]:
        """The wire form a result view reads. `pulses` is deliberately not
        in it — that is the whole raw record and belongs in HDF5, not in a
        progress frame."""
        return {
            "method": self.method,
            "params": dict(self.params),
            "window": list(self.window),
            "window_s": [
                self.window[0] * self.bin_width_s,
                self.window[1] * self.bin_width_s,
            ],
            "bin_width_s": self.bin_width_s,
            "readouts": self.readouts,
            "bins": self.bins,
            "found": self.found,
            "profile": self.profile.tolist(),
        }


#: Every registered extraction method, by name.
EXTRACTORS: dict[str, Callable[..., tuple[int, int]]] = {}
_PARAMETERS: dict[str, tuple[Parameter, ...]] = {}


def extractor(
    *params: Parameter,
) -> Callable[[Callable[..., tuple[int, int]]], Callable[..., tuple[int, int]]]:
    """Register a window finder and declare *its own* parameters.

    A finder takes the summed profile and the bin width and returns the
    `[start, stop)` bin range of the laser pulse. Everything else —
    slicing the readouts out, handling an empty trace, reporting what was
    used — is shared, so a new method is one function.
    """

    def decorate(fn: Callable[..., tuple[int, int]]) -> Callable[..., tuple[int, int]]:
        EXTRACTORS[fn.__name__] = fn
        _PARAMETERS[fn.__name__] = params
        return fn

    return decorate


def extractor_parameters(name: str) -> tuple[Parameter, ...]:
    """What this method can be configured with — the UI builds its
    controls from exactly this, as it does for a sequence generator."""
    if name not in _PARAMETERS:
        raise ExtractionError(
            f"No extraction method named {name!r} — known: "
            f"{', '.join(sorted(EXTRACTORS)) or 'none'}"
        )
    return _PARAMETERS[name]


def _seconds(name: str, description: str, default_limit: float = 0.0) -> Parameter:
    return Parameter(
        name, unit="s", role=ParamRole.SETTING, settable=True, readable=False,
        limits=(default_limit, None), description=description,
    )


# --- The methods ------------------------------------------------------------


@extractor(
    _seconds(
        "smoothing",
        "Width of the Gaussian the record is smoothed with before "
        "differentiating. Too small and shot noise wins; too large and a "
        "short laser pulse is smeared into its own background.",
    ),
)
def conv_deriv(profile: np.ndarray, bin_width_s: float, smoothing: float = 20e-9) -> tuple[int, int]:
    """Edges as the extrema of a Gaussian-smoothed derivative.

    Convolving with the derivative of a Gaussian smooths and
    differentiates in one pass, so the largest positive response is the
    laser turning on and the largest negative one is it turning off. It
    finds an edge rather than a level, which is why it survives a
    background rate that drifts during a run — a threshold at a fixed
    fraction of the maximum does not.

    Standard signal processing, implemented from that description; Qudi's
    equivalent is LGPL and was not consulted line by line.
    """
    sigma = max(smoothing / bin_width_s, 1.0)
    half = max(round(4 * sigma), 1)
    x = np.arange(-half, half + 1, dtype=float)
    # d/dx of exp(-x^2 / 2 sigma^2), normalised so the response scales
    # with the step height rather than with sigma.
    kernel = -x / (sigma**2) * np.exp(-(x**2) / (2 * sigma**2))
    kernel /= np.abs(kernel).sum() or 1.0

    derivative = np.convolve(profile.astype(float), kernel, mode="same")
    rise = int(np.argmax(derivative))
    fall = int(np.argmin(derivative))
    if fall <= rise:
        # Only one edge in the record: the pulse runs to the end of it.
        # A gate that closes with the laser still on is a real rig, not a
        # broken one.
        fall = len(profile)
    return rise, fall


@extractor(
    Parameter(
        "level", role=ParamRole.SETTING, settable=True, readable=False,
        limits=(0.0, 1.0),
        description="How far from dark to bright counts as 'laser on'. "
                    "Below the repolarised floor, not at half maximum — see "
                    "the function's own note.",
    ),
)
def threshold(profile: np.ndarray, bin_width_s: float, level: float = 0.2) -> tuple[int, int]:
    """The longest run of bins above a fraction of the record's range.

    Simpler and more brittle than `conv_deriv`, and worth keeping for
    exactly that reason: on a clean square readout it gives the same
    answer with nothing to tune, and when the two disagree the
    disagreement is informative.

    Two details that are not the obvious choices, both because an NV
    readout is a *decaying* transient rather than a rectangle:

    - **The default level is 0.2, not half maximum.** The window wanted
      here is where the laser is on, and by the end of it the pulse has
      fallen to roughly a third of its peak. A half-maximum threshold
      finds the bright leading edge and calls the laser off well before
      it is — which looks like a short readout window and quietly costs
      most of the reference.
    - **The range comes from percentiles, not from min and max.** One hot
      bin — an afterpulse, a cosmic ray, a stray reflection — moves the
      maximum far more than it moves the record, and with it the level.

    The *longest* run rather than the first, for the same reason.
    """
    del bin_width_s  # A level test has no timescale.
    values = profile.astype(float)
    low, high = (float(v) for v in np.percentile(values, (2, 98)))
    above = values >= low + level * (high - low)

    best = (0, len(values))
    start: int | None = None
    longest = 0
    for index, hot in enumerate([*above.tolist(), False]):
        if hot and start is None:
            start = index
        elif not hot and start is not None:
            if index - start > longest:
                longest = index - start
                best = (start, index)
            start = None
    return best


# --- The one entry point ----------------------------------------------------


def extract(
    trace: Any, bin_width_s: float, method: str = "conv_deriv", **params: Any
) -> Extraction:
    """Cut the laser pulse out of a raw gated trace.

    `trace` is a 2-D `(readout, time_bin)` array or the `Dataset` a
    gated counter's `get_trace()` returns — both, because the console
    hands over whatever the counter gave it and should not have to unwrap
    it first.
    """
    if method not in EXTRACTORS:
        raise ExtractionError(
            f"No extraction method named {method!r} — known: "
            f"{', '.join(sorted(EXTRACTORS)) or 'none'}"
        )
    if bin_width_s <= 0:
        raise ExtractionError(f"A bin width must be positive, got {bin_width_s!r}")

    counts = _as_array(trace)
    declared = {p.name for p in extractor_parameters(method)}
    unknown = set(params) - declared
    if unknown:
        raise ExtractionError(
            f"{method} takes no parameter(s) {', '.join(sorted(unknown))} — "
            f"it declares: {', '.join(sorted(declared)) or 'none'}"
        )
    validated = {
        p.name: p.validate(params[p.name])
        for p in extractor_parameters(method)
        if p.name in params
    }

    profile = counts.sum(axis=0)
    # Nothing has been counted yet — the first poll of a run always looks
    # like this. Take the whole record and say so, rather than reporting
    # an edge found in shot noise.
    if profile.size == 0 or float(profile.max()) <= float(profile.min()):
        return Extraction(
            pulses=counts, window=(0, int(counts.shape[1])), bin_width_s=bin_width_s,
            profile=profile, found=False, method=method, params=validated,
        )

    start, stop = EXTRACTORS[method](profile, bin_width_s, **validated)
    start = max(int(start), 0)
    stop = min(int(stop), int(counts.shape[1]))
    if stop - start < 1:
        raise ExtractionError(
            f"{method} found an empty readout window ([{start}, {stop}) of "
            f"{counts.shape[1]} bins). The record may be shorter than the "
            f"laser pulse, or the smoothing wider than the pulse itself."
        )
    return Extraction(
        pulses=counts[:, start:stop], window=(start, stop), bin_width_s=bin_width_s,
        profile=profile, found=True, method=method, params=validated,
    )


def _as_array(trace: Any) -> np.ndarray:
    """A `Dataset`, a `DataArray` or a plain 2-D array, as counts."""
    for attribute in ("primary", "values"):
        if hasattr(trace, attribute):
            member = getattr(trace, attribute)
            trace = member() if callable(member) else member

    counts = np.asarray(trace)
    if counts.ndim == 1:
        counts = counts.reshape(1, -1)
    if counts.ndim != 2:
        raise ExtractionError(
            f"A gated trace is 2-D (readout, time_bin); got shape {counts.shape}"
        )
    return counts
