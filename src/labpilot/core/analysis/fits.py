"""Single-peak/dip fit models — Qudi's own `fit_models` concept (a named
model fit against x/y data, returning physically-meaningful parameters).

The one implementation. Workflow scripts doing programmatic fitting
(odmr_sweep, peak_fit_series) import it, and so do the desktop app's
spectrometer fit button and its ODMR fit dock.

The desktop app used to carry two independent copies of these formulas,
on the stated grounds that it "is a separate process with no shared Python
path to core/". The first half is true and is why it reaches instruments
over HTTP; the second half was not — it is the same installed package, and
the same file already imported `core.api_client`. A pure function of
numbers has no process to be on the wrong side of.
"""

from __future__ import annotations

import numpy as np

__all__ = ["fit_peak", "fit_dip", "fit_peak_2d", "evaluate_dip"]


def fit_peak(x, y, shape: str = "gaussian") -> dict | None:
    """Single-peak fit over x/y data (typically an already-sliced
    region-of-interest trace). `shape` is "gaussian" or "lorentzian".

    Returns {center, amplitude, fwhm, baseline} in x's units, or None if
    the fit didn't converge (too few points, no real peak, ...).
    """
    from scipy.optimize import curve_fit

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 4:
        return None

    baseline = float(np.median(y))
    amplitude0 = float(np.max(y) - baseline)
    center0 = float(x[np.argmax(y)])
    width0 = max((x[-1] - x[0]) / 4, 1e-9)

    if shape == "lorentzian":
        def model(xx, amp, x0, gamma, base):
            return base + amp * gamma**2 / ((xx - x0) ** 2 + gamma**2)
    else:
        def model(xx, amp, x0, sigma, base):
            return base + amp * np.exp(-((xx - x0) ** 2) / (2 * sigma**2))

    try:
        popt, _ = curve_fit(
            model, x, y, p0=[amplitude0, center0, width0, baseline], maxfev=5000,
        )
    except Exception:
        return None

    amp, x0, w, base = popt
    fwhm = abs(w) * (2.3548 if shape == "gaussian" else 2.0)
    return {"center": float(x0), "amplitude": float(amp), "fwhm": float(fwhm), "baseline": float(base)}


def fit_peak_2d(x, y, z) -> dict | None:
    """2D single-peak Gaussian fit over a grid — `x`/`y` are the two axes'
    1D coordinate arrays, `z` a 2D array of shape `(len(x), len(y))`. Used
    by `core/workflow/capabilities.py`'s `OptimizerCapability` for each 2D
    step of an optimize sequence — qudi's own confocal optimizer
    (`scanning_optimize_logic.py`'s `_get_pos_from_2d_gauss_fit`,
    `LOGIC_LIBRARY_NOTES.md` §2.1) fits the same shape of data; this is an
    independent re-implementation using this module's own `curve_fit`
    convention rather than qudi's `lmfit`-based `Gaussian2D` model.

    Returns {center_x, center_y, amplitude, sigma_x, sigma_y, baseline}, or
    None if the fit didn't converge (too few points, no real peak, ...).
    """
    from scipy.optimize import curve_fit

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    if z.size < 6 or x.size < 2 or y.size < 2:
        return None

    xx, yy = np.meshgrid(x, y, indexing="ij")
    baseline = float(np.median(z))
    amplitude0 = float(np.max(z) - baseline)
    peak_i, peak_j = np.unravel_index(np.argmax(z), z.shape)
    x0_0, y0_0 = float(x[peak_i]), float(y[peak_j])
    sigma_x0 = max((x[-1] - x[0]) / 4, 1e-9)
    sigma_y0 = max((y[-1] - y[0]) / 4, 1e-9)

    def model(xy, amp, x0, y0, sx, sy, base):
        xf, yf = xy
        return (
            base + amp * np.exp(-(((xf - x0) ** 2) / (2 * sx**2) + ((yf - y0) ** 2) / (2 * sy**2)))
        ).ravel()

    try:
        popt, _ = curve_fit(
            model, (xx, yy), z.ravel(),
            p0=[amplitude0, x0_0, y0_0, sigma_x0, sigma_y0, baseline], maxfev=5000,
        )
    except Exception:
        return None

    amp, x0, y0, sx, sy, base = popt
    return {
        "center_x": float(x0), "center_y": float(y0), "amplitude": float(amp),
        "sigma_x": float(sx), "sigma_y": float(sy), "baseline": float(base),
    }


def fit_dip(x, y, shape: str = "lorentzian") -> dict | None:
    """Single-DIP fit (e.g. an ODMR resonance, an absorption line) — same
    models as `fit_peak`, fit against the data inverted about zero (curve_fit's
    initial-guess heuristics in `fit_peak` assume a positive peak, not a dip).

    Returns {center, amplitude, fwhm, baseline}, with `amplitude` the
    (positive) depth of the dip below `baseline` and `baseline` corrected
    back to the real (non-inverted) y-scale, or None if the fit didn't
    converge.
    """
    inverted = [-v for v in np.asarray(y, dtype=float)]
    result = fit_peak(x, inverted, shape)
    if result is None:
        return None
    result["baseline"] = -result["baseline"]
    return result


def evaluate_dip(fit: dict, x, shape: str = "lorentzian") -> list[float]:
    """Reconstructs a `fit_dip()` result's curve over `x` — for a UI fit
    overlay (see workflow_result.py's SpectrumResultView), not further
    analysis. Same Lorentzian/Gaussian shapes as `fit_peak`'s inner
    `model`, inverted about `baseline` to match fit_dip's own convention.
    """
    x = np.asarray(x, dtype=float)
    amp, x0, base = fit["amplitude"], fit["center"], fit["baseline"]
    if shape == "lorentzian":
        gamma = fit["fwhm"] / 2.0
        y = base - amp * gamma**2 / ((x - x0) ** 2 + gamma**2)
    else:
        sigma = fit["fwhm"] / 2.3548
        y = base - amp * np.exp(-((x - x0) ** 2) / (2 * sigma**2))
    return y.tolist()
