"""ODMR sweep — step a source's frequency, count photons, fit the dip.

Qudi's signature workflow. Sweep a microwave source across a resonance,
read a detector at every point, average several passes, and fit a single
dip in the result: optically-detected magnetic resonance.

Each pass is kept separately as one row of an accumulation matrix — the
2-D image Qudi's own ODMR GUI shows under the averaged spectrum, and the
reason it does: a resonance that drifts and one that is merely noisy look
identical once averaged, and obviously different the moment the passes
are laid side by side.

## What changed, and why it is shorter

This used to hand-roll its loop, pre-allocate its own arrays, count its
own progress and publish its own frames — sixty lines of scaffolding
around ten lines of measurement. It is now a `ScanPlan` with `repeats`,
so the buffer, the counters, the progress event, the per-point patch
streaming, pause, abort and the automatic HDF5 save all come from `Run`.
The accumulation matrix is not assembled here either: it is the result's
own leading `repeat` axis.

## Which parameter gets swept is declared, not guessed

It used to be found like this:

    sweep_key = next(k for k, dt in settable.items()
                     if dt != "bool" and "power" not in k.lower())

— the first settable whose name does not contain "power". A source with a
settable phase, modulation depth or reference level silently gets that
wrong, and getting it wrong means sweeping the wrong quantity and fitting
a resonance in it. Nothing raises; the plot just looks odd.

So a source now *declares* which parameter is its frequency and which is
its level, with the `FREQUENCY` and `POWER` tags
(`core/device/parameter.py`), and this asks. `SWEEP_PARAMETER` and
`POWER_PARAMETER` below name them explicitly for a source that has not
been tagged yet — an override, not a guess, and the error says which to
set.

References its instruments by *role*: bind "source" and "detector" to
whichever connected instruments should play each part. Rebind either at
any time; the script itself never needs editing.
"""

import numpy as np

from labpilot.core.analysis.fits import evaluate_dip, fit_dip
from labpilot.core.device.parameter import FREQUENCY, POWER
from labpilot.core.run import ScanAxis, ScanPlan
from labpilot.script import bind, execute

REQUIRED_INSTRUMENTS = {
    "source": {"kind": "source", "dimensionality": "SOURCE"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}

# Read by the native desktop window to render a live spectrum + matrix
# view that grows as the sweep runs. fit_* are only populated in the final
# result, once the fit itself has run.
RESULT_UI = {
    "type": "odmr",
    "x_key": "sweep_values",
    "y_key": "counts",
    "matrix_key": "matrix",
    "repeat_key": "repeats_done",
    "x_label": "Frequency (Hz)",
    "y_label": "Detector reading",
    "fit_x_key": "fit_curve_x",
    "fit_y_key": "fit_curve_y",
    "fit_center_key": "fit_center",
}

# Sweep range, in whatever unit the bound source reports for its frequency
# parameter (Hz for mock_microwave_source's cw_frequency).
SWEEP_START = 2.82e9  # Hz
SWEEP_STOP = 2.86e9  # Hz
SWEEP_POINTS = 21

# Parked once, before the sweep starts, on the source's level parameter.
SWEEP_POWER = -10.0  # dBm

# Full sweeps to repeat — Qudi's "Scans to Average". Each becomes one row
# of the accumulation matrix.
AVERAGES = 5

# "lorentzian" matches a real ODMR dip's physical lineshape best;
# "gaussian" is also supported by core.analysis.fits.fit_dip.
FIT_SHAPE = "lorentzian"

# Empty means "ask the source which parameter is which", via the FREQUENCY
# and POWER tags. Name one here for a source that has not declared them —
# an override rather than a guess.
SWEEP_PARAMETER = ""
POWER_PARAMETER = ""


def _named(schema, override: str, tag: str, what: str) -> str:
    """Which parameter to sweep or park: the override, or the tagged one.

    Raises rather than falling back to a name heuristic. The failure mode
    a heuristic has here is silent and expensive — sweeping a modulation
    depth and fitting a resonance in it — so an error that names both the
    tag and the override is the cheaper outcome by a wide margin.
    """
    if override:
        if override not in schema.settable:
            raise KeyError(
                f"{schema.name} has no settable {override!r} — it offers "
                f"{', '.join(sorted(schema.settable)) or 'nothing'}"
            )
        return override

    found = schema.first(settable=True, tags={tag})
    if found is None:
        raise KeyError(
            f"{schema.name} does not declare which of its parameters is its "
            f"{what} (no parameter tagged {tag!r}), so this sweep cannot "
            f"know what to {'step' if tag == FREQUENCY else 'park'}. Set "
            f"{'SWEEP_PARAMETER' if tag == FREQUENCY else 'POWER_PARAMETER'} "
            f"to its name — one of {', '.join(sorted(schema.settable))} — or "
            f"tag it in the adapter's schema."
        )
    return found.name


source = bind("source")
bind("detector")
schema = source.schema

swept = _named(schema, SWEEP_PARAMETER, FREQUENCY, "frequency")
level = ""
try:
    level = _named(schema, POWER_PARAMETER, POWER, "level")
except KeyError:
    # A source with no level setpoint is a real source. Only an explicitly
    # named POWER_PARAMETER that does not exist is an error worth raising.
    if POWER_PARAMETER:
        raise

# A sweep against a source whose RF output is off measures a flat line,
# and `hold` cannot switch it on: on most real sources the output is an
# action (`cw_on`/`off`), not a settable. So switch it on here when the
# source says it can, and off again whatever happens — an abort would
# otherwise leave the RF on with nobody watching.
actions = set(schema.action_names)
if "cw_on" in actions:
    source.cw_on()
try:
    result = execute(
        ScanPlan(
            axes=[
                ScanAxis(
                    swept, "source", float(SWEEP_START), float(SWEEP_STOP),
                    int(SWEEP_POINTS), unit=schema.units.get(swept, ""),
                )
            ],
            detector="detector",
            repeats=int(AVERAGES),
            # `hold` parks a parameter once before the grid starts, which is
            # exactly what a power setpoint is.
            hold={level: float(SWEEP_POWER)} if level else {},
            hold_device="source",
            name="odmr_sweep",
        )
    )
finally:
    if "off" in actions:
        source.off()

# The result is (repeats, points) when averaging and (points,) when not —
# `repeat` is a real axis, so the matrix the ODMR view draws is a reshape
# rather than something assembled by hand.
passes = max(int(AVERAGES), 1)
sweep_values = np.linspace(SWEEP_START, SWEEP_STOP, int(SWEEP_POINTS)).tolist()
measured = np.asarray(
    [np.nan if v is None else v for v in result["data"]], dtype=float
).reshape(passes, len(sweep_values))

# Untaken points are NaN — an aborted run keeps what it measured, and
# averaging a partial pass in with the complete ones would pull the curve
# towards whichever points happened to be measured twice.
with np.errstate(invalid="ignore"):
    counts = np.nanmean(measured, axis=0)
complete = [row for row in measured.tolist() if not any(np.isnan(row))]

fit = fit_dip(sweep_values, counts.tolist(), FIT_SHAPE)
fit_curve_x: list = []
fit_curve_y: list = []
fit_center = None
if fit is not None:
    fit_curve_x = np.linspace(min(sweep_values), max(sweep_values), 200).tolist()
    fit_curve_y = evaluate_dip(fit, fit_curve_x, FIT_SHAPE)
    fit_center = fit["center"]

RESULT = {
    **result,
    "source": "source",
    "detector": "detector",
    "swept_parameter": swept,
    "power_parameter": level,
    "sweep_values": sweep_values,
    "counts": counts.tolist(),
    "matrix": complete,  # one row per completed pass, raw (unaveraged)
    "repeats_done": len(complete),
    "fit": fit,  # {center, amplitude, fwhm, baseline}, or None if it did not converge
    "fit_curve_x": fit_curve_x,  # dense curve for the result view's overlay
    "fit_curve_y": fit_curve_y,
    "fit_center": fit_center,
}
