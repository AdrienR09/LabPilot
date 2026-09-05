"""ODMR sweep.

Qudi's signature workflow: step a source's output (canonically a
microwave source's frequency, but works against any settable numeric
source output) through a series of values, averaging `AVERAGES` repeats
of the sweep, and fit a single dip in the resulting averaged trace — the
standard optically-detected magnetic resonance (ODMR) measurement pattern
(core/analysis/fits.py's `fit_dip`, same Lorentzian/Gaussian models qudi's
own fit_logic uses for this). Each repeat's raw trace is also kept as one
row of a growing `matrix` — qudi's own ODMR GUI shows this as a 2D
accumulation image below the averaged spectrum, since it's the easiest
way to see drift or a bad average visually instead of only in the final
number.

References its instruments by *role*, not a specific instrument id — bind
"source" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

import numpy as np

from labpilot.core.analysis.fits import evaluate_dip, fit_dip
from labpilot.core.session import Session

REQUIRED_INSTRUMENTS = {
    "source": {"kind": "source", "dimensionality": "SOURCE"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
SOURCE_ID = "source"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live
# spectrum+matrix view that grows as the sweep runs — see
# session.report_progress() below. fit_x_key/fit_y_key/fit_center_key are
# optional — only populated in the final last_results, once the fit
# itself has run.
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

# Sweep range, in whatever unit the bound source's own schema reports for
# its settable frequency-like output (Hz for mock_microwave_source's
# cw_frequency). Edit via PUT /api/workflows/{id}/params/SWEEP_START etc.,
# or the native Sweep Control dock.
SWEEP_START = 2.82e9  # Hz
SWEEP_STOP = 2.86e9  # Hz
SWEEP_POINTS = 21

# Written once, before sweeping, to whichever settable key's name contains
# "power" (if any) — most microwave sources separate a power setpoint from
# the frequency being swept.
SWEEP_POWER = -10.0  # dBm

# Number of full sweeps to repeat and average — qudi's "Scans to Average".
# Each repeat's raw (unaveraged) trace becomes one row of RESULT_UI's
# matrix view.
AVERAGES = 5

# "lorentzian" matches a real ODMR dip's physical lineshape best; "gaussian"
# is also supported by core.analysis.fits.fit_dip if preferred.
FIT_SHAPE = "lorentzian"


async def run(session: Session) -> dict:
    # source.write({...}) stays generic dict-based (below) rather than a
    # typed method: which settable key is "the swept axis" vs. "the power
    # setpoint" is genuinely instrument-specific business logic (see
    # sweep_key/power_key detection below) — a generic Source wrapper
    # (core/device/kinds.py) can't honestly guess that for an arbitrary
    # microwave source, so this stays hand-written. detector.read_value()
    # (below) DOES generalize cleanly — a 0D detector's reading is always
    # "the one scalar value" regardless of manufacturer.
    source = session.get(SOURCE_ID)
    detector = session.get(DETECTOR_ID)
    settable = source.schema.settable
    # The frequency-like sweep axis is the one non-bool, non-power settable
    # key (a source's other settable keys, if any, are typically a power
    # setpoint and/or an on/off enable flag — see MoveControlComponent's
    # identical enable_key convention on the native UI side).
    sweep_key = next(k for k, dt in settable.items() if dt != "bool" and "power" not in k.lower())
    power_key = next((k for k, dt in settable.items() if "power" in k.lower()), None)

    sweep_values = np.linspace(SWEEP_START, SWEEP_STOP, int(SWEEP_POINTS)).tolist()
    matrix: list[list[float]] = []
    sums = [0.0] * len(sweep_values)
    total_points = AVERAGES * len(sweep_values)

    if power_key:
        await source.write({power_key: SWEEP_POWER})

    await detector.stage()
    try:
        for repeat in range(int(AVERAGES)):
            row: list[float] = []
            for i, target in enumerate(sweep_values):
                await source.write({sweep_key: target})

                value = await detector.read_value()
                row.append(value)
                completed = repeat * len(sweep_values) + i + 1
                if repeat == 0:
                    # No repeat has completed yet — show this first pass's
                    # raw trace growing point by point (same as before
                    # averaging existed), rather than a running average
                    # that would need to divide by zero.
                    live_x, live_counts = sweep_values[: i + 1], row
                else:
                    live_x, live_counts = sweep_values, [s / repeat for s in sums]
                await session.report_progress({
                    "sweep_values": live_x,
                    "counts": live_counts,
                    "matrix": matrix,  # only completed rows — the in-progress row joins once finished
                    "repeats_done": repeat,
                    "completed": completed,
                    "total": total_points,
                })
            for i, value in enumerate(row):
                sums[i] += value
            matrix.append(row)
    finally:
        await detector.unstage()

    counts = [s / AVERAGES for s in sums]

    fit = fit_dip(sweep_values, counts, FIT_SHAPE)
    fit_curve_x: list[float] = []
    fit_curve_y: list[float] = []
    fit_center = None
    if fit is not None:
        fit_curve_x = np.linspace(min(sweep_values), max(sweep_values), 200).tolist()
        fit_curve_y = evaluate_dip(fit, fit_curve_x, FIT_SHAPE)
        fit_center = fit["center"]

    return {
        "source": SOURCE_ID,
        "detector": DETECTOR_ID,
        "sweep_values": sweep_values,
        "counts": counts,
        "matrix": matrix,  # one row per repeat, raw (unaveraged) trace
        "repeats_done": AVERAGES,
        "fit": fit,  # {center, amplitude, fwhm, baseline} in sweep_values' units, or None if the fit didn't converge
        "fit_curve_x": fit_curve_x,  # dense curve for the result view's fit overlay — see RESULT_UI above
        "fit_curve_y": fit_curve_y,
        "fit_center": fit_center,
    }
