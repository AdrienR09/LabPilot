"""Peak fit series.

Acquires `N_REPEATS` spectra from a 1D detector in sequence, fits a single
peak or dip (core/analysis/fits.py) in each one, and returns the fitted
parameters as a series vs. acquisition index — the general form qudi uses
for a repeated-experiment measurement (e.g. tracking a resonance drifting
over time, or a signal amplitude changing shot-to-shot), parametrized by
which fit model/shape to use rather than hardcoded to one specific
experiment.

References its instrument by *role*, not a specific instrument id — bind
"detector" (via the flowchart, or PUT /api/workflows/{id}/bindings/{role})
to whichever real connected instrument should play that part before
running. Rebind it at any time; the script itself never needs editing.
"""

from labpilot.core.analysis.fits import fit_dip, fit_peak
from labpilot.core.session import Session
from labpilot.core.workflow_templates._common import integration_time_key, spectrum_key

REQUIRED_INSTRUMENTS = {
    "detector": {"kind": "detector", "dimensionality": "1D"},
}
DETECTOR_ID = "detector"

# Read by the native desktop window (workflow_window.py) to render a live
# curve of the fitted center vs. acquisition index — see
# session.report_progress() below.
RESULT_UI = {
    "type": "spectrum",
    "x_key": "step_index",
    "y_key": "centers",
    "x_label": "Acquisition #",
    "y_label": "Fitted center",
}

N_REPEATS = 10
INTEGRATION_TIME_MS = 50.0

# "peak" for a positive resonance/emission line, "dip" for an absorption
# line or an ODMR-style resonance dip.
FIT_KIND = "peak"
FIT_SHAPE = "gaussian"


async def run(session: Session) -> dict:
    detector = session.get(DETECTOR_ID)

    it_key = integration_time_key(detector)
    if it_key:
        await detector.write({it_key: INTEGRATION_TIME_MS})
    value_key = spectrum_key(detector)
    fit_fn = fit_dip if FIT_KIND == "dip" else fit_peak

    spectra: list[list[float]] = []
    step_index: list[int] = []
    centers: list[float | None] = []
    amplitudes: list[float | None] = []
    fwhms: list[float | None] = []

    await detector.stage()
    try:
        for step in range(N_REPEATS):
            data = await detector.read()
            spectrum = list(data[value_key])
            x = list(range(len(spectrum)))

            fit = fit_fn(x, spectrum, FIT_SHAPE)
            spectra.append(spectrum)
            step_index.append(step)
            centers.append(fit["center"] if fit is not None else None)
            amplitudes.append(fit["amplitude"] if fit is not None else None)
            fwhms.append(fit["fwhm"] if fit is not None else None)

            await session.report_progress({
                "step_index": step_index,
                "centers": centers,
                "completed": step + 1,
                "total": N_REPEATS,
            })
    finally:
        await detector.unstage()

    return {
        "detector": DETECTOR_ID,
        "step_index": step_index,
        "spectra": spectra,  # spectra[i] = raw spectrum acquired at step_index[i]
        "centers": centers,  # fitted peak/dip center per step, or None where the fit didn't converge
        "amplitudes": amplitudes,
        "fwhms": fwhms,
    }
