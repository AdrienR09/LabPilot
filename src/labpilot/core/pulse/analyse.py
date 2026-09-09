"""Turning extracted readout windows into one number per swept point.

`extract.py` says *where* the laser pulse is; this says *what to do with
it*. The output is the measurement itself — the curve that gets fitted,
saved and plotted — so its conventions matter more than its arithmetic.

## Every method returns one value per swept point

Not one per readout. An alternating sequence takes two readouts per
point (signal, then reference), and a method that returned one value per
readout would hand the run twice as many numbers as its sweep has
points, leaving the caller to guess which convention was used. So the
de-interleaving happens here, once, where `alternating` is known — it is
a property the sequence carries, not something an analysis has to be
told separately.

## Errors are Poisson, and they are not decoration

Photon counting is Poisson: the uncertainty on `N` counts is `sqrt(N)`,
which is the only error bar available without repeating the whole
measurement. A ratio propagates both terms. Carrying it means a fit can
weight its points and a plot can show whether a wiggle is real — the
usual reason a Rabi looks like it has a second frequency is that nobody
drew the error bars.

## Windows are times, not fractions

`signal_start` and friends are seconds measured from the start of the
laser pulse, because that is how a rig is characterised: "the first 300
nanoseconds" is a statement about NV physics and stays true when the
counter's bin width changes. A window that falls outside the extracted
pulse is an error naming both numbers rather than a silent clamp — the
alternative is a normalisation window that quietly became one bin wide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.device.parameter import Parameter, ParamRole

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "ANALYSES",
    "Analysis",
    "AnalysisError",
    "analyse",
    "analysis",
    "analysis_parameters",
    "analysis_units",
    "default_analysis",
    "mean",
    "mean_norm",
    "mean_reference",
]


class AnalysisError(Exception):
    """Data an analysis method cannot honestly reduce, and why."""


@dataclass(frozen=True, slots=True)
class Analysis:
    """One value per swept point, with what it means and how sure it is."""

    values: np.ndarray
    errors: np.ndarray
    label: str = "signal"
    unit: str = ""
    method: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    signal_window: tuple[int, int] = (0, 0)
    """Bins within the extracted pulse the signal was averaged over."""
    reference_window: tuple[int, int] | None = None
    """The second window, for a method that uses one."""

    @property
    def points(self) -> int:
        return int(self.values.size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "params": dict(self.params),
            "label": self.label,
            "unit": self.unit,
            "values": np.asarray(self.values, dtype=float).tolist(),
            "errors": np.asarray(self.errors, dtype=float).tolist(),
            "signal_window": list(self.signal_window),
            "reference_window": (
                list(self.reference_window) if self.reference_window else None
            ),
        }


#: Every registered analysis method, by name.
ANALYSES: dict[str, Callable[..., Analysis]] = {}
_PARAMETERS: dict[str, tuple[Parameter, ...]] = {}
_UNITS: dict[str, tuple[str, str]] = {}


def analysis(
    *params: Parameter, label: str = "signal", unit: str = ""
) -> Callable[[Callable[..., Analysis]], Callable[..., Analysis]]:
    """Register an analysis method, its parameters, and what it produces.

    `label` and `unit` are declared rather than returned so a run can
    state its value name and unit in `describe()` — before the first
    readout exists to be analysed.
    """

    def decorate(fn: Callable[..., Analysis]) -> Callable[..., Analysis]:
        ANALYSES[fn.__name__] = fn
        _PARAMETERS[fn.__name__] = params
        _UNITS[fn.__name__] = (label, unit)
        return fn

    return decorate


def analysis_parameters(name: str) -> tuple[Parameter, ...]:
    """What this method can be configured with. Per method, never shared
    — see `extract.py`'s module docstring for why that matters."""
    if name not in _PARAMETERS:
        raise AnalysisError(
            f"No analysis method named {name!r} — known: "
            f"{', '.join(sorted(ANALYSES)) or 'none'}"
        )
    return _PARAMETERS[name]


def analysis_units(name: str) -> tuple[str, str]:
    """`(label, unit)` this method produces, knowable before it runs."""
    if name not in _UNITS:
        raise AnalysisError(
            f"No analysis method named {name!r} — known: "
            f"{', '.join(sorted(ANALYSES)) or 'none'}"
        )
    return _UNITS[name]


def default_analysis(alternating: bool) -> str:
    """The method that makes use of everything an alternating sequence
    measured, or the best single-arm one when there is no reference.

    A real decision made from something the sequence already knows, which
    is why `PulsedMeasurementPlan` defaults to `"auto"` rather than to a
    method name that is wrong for half the experiments.
    """
    return "mean_reference" if alternating else "mean_norm"


def _window(name: str, description: str) -> Parameter:
    return Parameter(
        name, unit="s", role=ParamRole.SETTING, settable=True, readable=False,
        limits=(0.0, None), description=description,
    )


_SIGNAL = (
    _window("signal_start", "Start of the signal window, from the start of "
                            "the laser pulse"),
    _window("signal_length", "How much of the readout transient carries the "
                             "spin state. Longer than the transient adds "
                             "repolarised photons and costs contrast."),
)
_NORM = (
    _window("norm_start", "Start of the normalisation window — late enough "
                          "that the laser has repolarised the spin, so the "
                          "count rate there measures the laser, not the state"),
    _window("norm_length", "How much of the tail to average"),
)


# --- The methods ------------------------------------------------------------


@analysis(*_SIGNAL, label="counts", unit="counts/bin")
def mean(
    pulses: np.ndarray,
    bin_width_s: float,
    alternating: bool = False,
    signal_start: float = 0.0,
    signal_length: float = 300e-9,
) -> Analysis:
    """Mean counts per bin in the signal window. Raw, unnormalised.

    The one to reach for when something looks wrong: it has no
    denominator to hide a problem in, so a drifting laser or a dead
    channel shows up as a drifting curve rather than as a flat one.

    On an alternating sequence this uses the signal arm only, discarding
    the reference readouts. `mean_reference` is what makes use of them.
    """
    counts = _signal_arm(pulses, alternating)
    window = _bins(counts, bin_width_s, signal_start, signal_length, "signal")
    values, errors = _mean_counts(counts, window)
    return Analysis(
        values=values, errors=errors, label="counts", unit="counts/bin",
        method="mean", signal_window=window,
        params={"signal_start": signal_start, "signal_length": signal_length},
    )


@analysis(*_SIGNAL, *_NORM, label="normalised fluorescence", unit="")
def mean_norm(
    pulses: np.ndarray,
    bin_width_s: float,
    alternating: bool = False,
    signal_start: float = 0.0,
    signal_length: float = 300e-9,
    norm_start: float = 1.5e-6,
    norm_length: float = 1e-6,
) -> Analysis:
    """Signal window divided by the tail of the *same* readout.

    Every readout carries its own reference, so laser-power drift,
    collection-efficiency drift and a sample that bleaches over an hour
    divide out rather than appearing as physics. That is the whole
    argument for recording longer than the laser pulse.

    What it cannot correct is anything that changes *within* a readout,
    which is why `mean_reference` exists for sequences that can afford a
    second readout per point.
    """
    counts = _signal_arm(pulses, alternating)
    signal = _bins(counts, bin_width_s, signal_start, signal_length, "signal")
    norm = _bins(counts, bin_width_s, norm_start, norm_length, "normalisation")

    top, top_error = _mean_counts(counts, signal)
    bottom, bottom_error = _mean_counts(counts, norm)
    values, errors = _ratio(top, top_error, bottom, bottom_error)
    return Analysis(
        values=values, errors=errors, label="normalised fluorescence", unit="",
        method="mean_norm", signal_window=signal, reference_window=norm,
        params={
            "signal_start": signal_start, "signal_length": signal_length,
            "norm_start": norm_start, "norm_length": norm_length,
        },
    )


@analysis(*_SIGNAL, label="signal / reference", unit="")
def mean_reference(
    pulses: np.ndarray,
    bin_width_s: float,
    alternating: bool = True,
    signal_start: float = 0.0,
    signal_length: float = 300e-9,
) -> Analysis:
    """Signal readout divided by the reference readout beside it.

    The measurement an alternating sequence exists to make: the same
    point measured twice, once with the final pulse that projects the
    accumulated phase and once without, so everything common to the two
    — laser power, collection, charge state, the NV's own drift over the
    minutes between the first point and the last — cancels point by
    point rather than being corrected for afterwards.

    Refuses non-alternating data instead of quietly pairing unrelated
    readouts, which would produce a plausible curve of nothing.
    """
    if not alternating:
        raise AnalysisError(
            "mean_reference needs an alternating sequence: it pairs each "
            "signal readout with the reference readout recorded beside it, "
            "and this sequence has one readout per point. Use "
            "'mean_norm' (per-readout normalisation) or 'mean'."
        )
    rows = _pairs(pulses)
    window = _bins(rows[0::2], bin_width_s, signal_start, signal_length, "signal")

    signal, signal_error = _mean_counts(rows[0::2], window)
    reference, reference_error = _mean_counts(rows[1::2], window)
    values, errors = _ratio(signal, signal_error, reference, reference_error)
    return Analysis(
        values=values, errors=errors, label="signal / reference", unit="",
        method="mean_reference", signal_window=window,
        params={"signal_start": signal_start, "signal_length": signal_length},
    )


# --- The one entry point ----------------------------------------------------


def analyse(
    pulses: Any,
    bin_width_s: float,
    method: str = "auto",
    *,
    alternating: bool = False,
    **params: Any,
) -> Analysis:
    """Reduce extracted readout windows to one value per swept point.

    `pulses` is an `Extraction` or its `(readout, bin)` array. `"auto"`
    picks the method that uses everything the sequence measured — see
    `default_analysis`.
    """
    if method == "auto":
        method = default_analysis(alternating)
    if method not in ANALYSES:
        raise AnalysisError(
            f"No analysis method named {method!r} — known: "
            f"{', '.join(sorted(ANALYSES))}, or 'auto'"
        )
    if bin_width_s <= 0:
        raise AnalysisError(f"A bin width must be positive, got {bin_width_s!r}")

    counts = np.asarray(getattr(pulses, "pulses", pulses), dtype=float)
    if counts.ndim != 2:
        raise AnalysisError(
            f"Extracted readouts are 2-D (readout, time_bin); got shape "
            f"{counts.shape}"
        )

    declared = {p.name for p in analysis_parameters(method)}
    unknown = set(params) - declared
    if unknown:
        raise AnalysisError(
            f"{method} takes no parameter(s) {', '.join(sorted(unknown))} — "
            f"it declares: {', '.join(sorted(declared)) or 'none'}"
        )
    validated = {
        p.name: p.validate(params[p.name])
        for p in analysis_parameters(method)
        if p.name in params
    }
    return ANALYSES[method](counts, bin_width_s, alternating, **validated)


# --- Shared arithmetic ------------------------------------------------------


def _signal_arm(pulses: np.ndarray, alternating: bool) -> np.ndarray:
    """The readouts that carry the measurement, one per swept point."""
    return _pairs(pulses)[0::2] if alternating else np.asarray(pulses, dtype=float)


def _pairs(pulses: np.ndarray) -> np.ndarray:
    """`pulses` truncated to a whole number of signal/reference pairs.

    A run polled mid-sweep can hold an odd number of readouts, and
    pairing the last one with nothing would put a spurious final point on
    the curve.
    """
    counts = np.asarray(pulses, dtype=float)
    if counts.shape[0] % 2:
        counts = counts[:-1]
    if counts.shape[0] == 0:
        raise AnalysisError(
            "An alternating measurement needs at least one signal/reference "
            "pair, and this trace has fewer than two readouts"
        )
    return counts


def _bins(
    counts: np.ndarray, bin_width_s: float, start: float, length: float, what: str
) -> tuple[int, int]:
    """A time window as a `[start, stop)` bin range, or a stated error."""
    available = int(counts.shape[1])
    first = round(start / bin_width_s)
    last = round((start + length) / bin_width_s)
    if first >= available or last <= first:
        raise AnalysisError(
            f"The {what} window ({start * 1e9:.0f}-{(start + length) * 1e9:.0f} ns) "
            f"falls outside the extracted readout, which is "
            f"{available * bin_width_s * 1e9:.0f} ns long ({available} bins of "
            f"{bin_width_s * 1e9:.3g} ns). Shorten the window, or record a "
            f"longer trace."
        )
    return first, min(last, available)


def _mean_counts(counts: np.ndarray, window: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Mean counts per bin over `window`, with its Poisson error.

    The error is taken from the *total*, not from the mean: `sqrt(N)/n`,
    where averaging over more bins genuinely reduces the uncertainty.
    """
    start, stop = window
    totals = counts[:, start:stop].sum(axis=1)
    width = max(stop - start, 1)
    return totals / width, np.sqrt(np.maximum(totals, 0.0)) / width


def _ratio(
    top: np.ndarray, top_error: np.ndarray, bottom: np.ndarray, bottom_error: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """`top / bottom` with both uncertainties propagated.

    A zero denominator gives NaN rather than an exception: the first poll
    of a run has counted nothing anywhere, and a run that refused to
    report its own first frame would be worse than one that reports a gap.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        values = np.where(bottom != 0, top / bottom, np.nan)
        relative = np.sqrt(
            np.where(top != 0, (top_error / top) ** 2, 0.0)
            + np.where(bottom != 0, (bottom_error / bottom) ** 2, 0.0)
        )
        errors = np.abs(values) * relative
    return values, errors
