"""Single-peak/dip fit models — Qudi's own `fit_models` concept (a named
model fit against x/y data, returning physically-meaningful parameters).

The canonical implementation for backend-side code: workflow scripts doing
programmatic fitting (odmr_sweep, peak_fit_series) import this directly.
The native Qt desktop app (src/ui/desktop/) is a separate process with no
shared Python path to core/ (it only ever talks to the backend over HTTP —
see backend_client.py), so its own spectrometer-controls fit button
(components/viewer.py's `_fit_peak`) keeps an independent copy of the same
formulas rather than importing this module directly; keep the two in sync
if the fit model itself ever changes.
"""

from __future__ import annotations

import numpy as np

__all__ = ["fit_peak", "fit_dip", "fit_peak_2d"]


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
