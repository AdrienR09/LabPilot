"""ODMR sweep.

Qudi's signature workflow: step a source's output (canonically a
microwave source's frequency, but works against any settable numeric
source output) through a series of values and record a 0D detector's
reading at each one, then fit a single dip in the resulting trace — the
standard optically-detected magnetic resonance (ODMR) measurement pattern
(core/analysis/fits.py's `fit_dip`, same Lorentzian/Gaussian models qudi's
own fit_logic uses for this).

References its instruments by *role*, not a specific instrument id — bind
"source" and "detector" (via the flowchart, or
PUT /api/workflows/{id}/bindings/{role}) to whichever real connected
instruments should play each part before running. Rebind either role at
any time; the script itself never needs editing.
"""

from core.analysis.fits import fit_dip
from core.session import Session

REQUIRED_INSTRUMENTS = {
    "source": {"kind": "source", "dimensionality": "SOURCE"},
    "detector": {"kind": "detector", "dimensionality": "0D"},
}
SOURCE_ID = "source"
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live
# curve that grows as the sweep runs — see session.report_progress() below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "sweep_values",
    "y_key": "counts",
    "x_label": "Source output",
    "y_label": "Detector reading",
}

# Sweep values — units are whatever the bound source's own schema reports
# for its settable output (e.g. MHz for a microwave source's frequency).
SWEEP_VALUES = [2820.0 + 2.0 * i for i in range(21)]  # e.g. a 40 MHz span around 2870 MHz (NV center)

# "lorentzian" matches a real ODMR dip's physical lineshape best; "gaussian"
# is also supported by core.analysis.fits.fit_dip if preferred.
FIT_SHAPE = "lorentzian"


async def run(session: Session) -> dict:
    source = session.get(SOURCE_ID)
    detector = session.get(DETECTOR_ID)
    # The one settable, non-boolean key is the sweep axis (a source's other
    # settable key, if any, is typically an on/off enable flag — see
    # MoveControlComponent's identical enable_key convention on the native
    # UI side).
    sweep_key = next(k for k, dt in source.schema.settable.items() if dt != "bool")
    value_key = next(iter(detector.schema.readable.keys()))

    sweep_values: list[float] = []
    counts: list[float] = []
    total = len(SWEEP_VALUES)
    await detector.stage()
    try:
        for target in SWEEP_VALUES:
            await source.write({sweep_key: target})

            data = await detector.read()
            sweep_values.append(target)
            counts.append(float(data[value_key]))
            await session.report_progress({
                "sweep_values": sweep_values,
                "counts": counts,
                "completed": len(sweep_values),
                "total": total,
            })
    finally:
        await detector.unstage()

    fit = fit_dip(sweep_values, counts, FIT_SHAPE)

    return {
        "source": SOURCE_ID,
        "detector": DETECTOR_ID,
        "sweep_values": sweep_values,
        "counts": counts,
        "fit": fit,  # {center, amplitude, fwhm, baseline} in sweep_values' units, or None if the fit didn't converge
    }
