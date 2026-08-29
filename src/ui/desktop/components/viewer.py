"""Detector data-display component: embeds a real scientific viewer widget
(Viewer0D/1D/2D/ND, dimensionality-selected) in a dock and feeds it from
each poll. This is the generalized form of what used to be three separate
hand-written `_apply_data` methods on Detector0D/1D/2DWindow.

For a 1D detector, `spectrometer_controls = true` adds a qudi
spectrometer_gui.py-style compact control row above the plot: background
acquire/subtract, and a fit-region (reusing the viewer's own built-in
linear ROI selector) with a one-click Gaussian/Lorentzian peak fit —
without needing a second component to coordinate writes to the same
viewer.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox
from PyQt6.QtCore import Qt

from pymodaq_gui.plotting.data_viewers.viewer0D import Viewer0D
from pymodaq_gui.plotting.data_viewers.viewer1D import Viewer1D
from pymodaq_gui.plotting.data_viewers.viewer2D import Viewer2D
from pymodaq_gui.plotting.data_viewers.viewerND import ViewerND
from pymodaq_data.data import DataRaw, Axis

from components.base import UIComponent
from components.widgets import IconButton, dock

_VIEWER_CLASSES = {"0D": Viewer0D, "1D": Viewer1D, "2D": Viewer2D, "ND": ViewerND}


def _fit_peak(x: np.ndarray, y: np.ndarray, shape: str) -> "dict | None":
    """Single-peak fit over an already-sliced (region-of-interest) trace.
    Returns {center, amplitude, fwhm} in x's units, or None if the fit
    didn't converge (too few points, no real peak, ...)."""
    from scipy.optimize import curve_fit

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

    amp, x0, w, _base = popt
    fwhm = abs(w) * (2.3548 if shape == "gaussian" else 2.0)
    return {"center": float(x0), "amplitude": float(amp), "fwhm": float(fwhm)}


class ViewerComponent(UIComponent):
    component_type = "viewer"
    default_params = {"dock_title": "Data", "spectrometer_controls": False}

    def build(self) -> None:
        window = self.window
        ctx = self.ctx
        dimensionality = self.params.get("dimensionality", ctx.instrument.dimensionality)
        viewer_cls = _VIEWER_CLASSES.get(dimensionality, Viewer0D)

        self.dimensionality = dimensionality
        self._background: dict | None = None  # {"x": ..., "y": ...}, set by "Acquire Background"
        self._subtract_background = False
        self._fit_region: tuple | None = None  # (x_min, x_max), set by dragging the viewer's own ROI
        self._last_trace: tuple | None = None  # (x, y) of the most recent raw read

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        show_spectrometer_controls = dimensionality == "1D" and self.params.get("spectrometer_controls")
        if show_spectrometer_controls:
            layout.addLayout(self._build_spectrometer_controls())

        plot_content = QWidget()
        self.viewer = viewer_cls(plot_content)
        layout.addWidget(plot_content, 1)

        if show_spectrometer_controls:
            self.viewer.roi_select_signal.connect(self._on_roi_selected)

        d = dock(self.params["dock_title"], window)
        d.setWidget(content)
        window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, d)

        ctx.viewer = self.viewer  # convenience back-reference (tests, other components)

    # ---- spectrometer controls (1D only, opt-in) ----

    def _build_spectrometer_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.background_checkbox = QCheckBox("Subtract background")
        self.background_checkbox.toggled.connect(self._on_subtract_toggled)
        row.addWidget(self.background_checkbox)

        acquire_bg_btn = IconButton("Acquire Background", "trace-snapshot")
        acquire_bg_btn.clicked.connect(self._on_acquire_background)
        row.addWidget(acquire_bg_btn)

        row.addStretch()

        self.fit_shape_combo = QComboBox()
        self.fit_shape_combo.addItems(["gaussian", "lorentzian"])
        row.addWidget(self.fit_shape_combo)

        fit_btn = IconButton("Fit Region", "trace-snapshot")
        fit_btn.setToolTip("Drag the viewer's own region-select tool over the peak, then click Fit.")
        fit_btn.clicked.connect(self._on_fit_clicked)
        row.addWidget(fit_btn)

        self.fit_result_label = QLabel("")
        self.fit_result_label.setProperty("class", "muted")
        row.addWidget(self.fit_result_label)

        return row

    def _on_subtract_toggled(self, checked: bool) -> None:
        self._subtract_background = checked

    def _on_acquire_background(self) -> None:
        if self._last_trace is None:
            self.ctx.set_status("No spectrum acquired yet to use as background")
            return
        x, y = self._last_trace
        self._background = {"x": x.copy(), "y": y.copy()}
        self.ctx.set_status("Background acquired")

    def _on_roi_selected(self, roi_info) -> None:
        origin = roi_info.origin[0]
        size = roi_info.size[0]
        self._fit_region = (origin, origin + size) if size >= 0 else (origin + size, origin)

    def _on_fit_clicked(self) -> None:
        ctx = self.ctx
        if self._last_trace is None:
            ctx.set_status("No spectrum acquired yet to fit")
            return
        x, y = self._last_trace
        if self._fit_region is not None:
            lo, hi = self._fit_region
            mask = (x >= lo) & (x <= hi)
            x, y = x[mask], y[mask]
        result = _fit_peak(x, y, self.fit_shape_combo.currentText())
        if result is None:
            self.fit_result_label.setText("Fit failed")
            return
        unit_suffix = f" {ctx.axis_units}" if ctx.axis_units else ""
        self.fit_result_label.setText(
            f"center={result['center']:.4g}{unit_suffix} · "
            f"FWHM={result['fwhm']:.4g}{unit_suffix} · amp={result['amplitude']:.3g}"
        )

    # ---- data dispatch ----

    def on_data(self, data: dict) -> None:
        ctx = self.ctx
        if ctx.value_key is None:
            return

        if self.dimensionality == "0D":
            value = float(data.get(ctx.value_key, 0.0))
            self.viewer.show_data(
                DataRaw(ctx.value_key, data=[np.array([value])], units=ctx.units)
            )
            ctx.set_info(f"{value:.3f} {ctx.units}")

        elif self.dimensionality == "1D":
            trace = np.asarray(data.get(ctx.value_key, []), dtype=float)
            if ctx.axis_key and ctx.axis_key in data:
                x = np.asarray(data[ctx.axis_key], dtype=float)
                if len(x) != len(trace):
                    x = np.arange(len(trace))
            else:
                x = np.arange(len(trace))
            self._last_trace = (x, trace)

            display_trace = trace
            if (
                self.params.get("spectrometer_controls")
                and self._subtract_background
                and self._background is not None
                and len(self._background["y"]) == len(trace)
            ):
                display_trace = trace - self._background["y"]

            axes = [Axis(ctx.axis_key, units=ctx.axis_units, data=x)] if ctx.axis_key else []
            self.viewer.show_data(
                DataRaw(ctx.value_key, data=[display_trace], axes=axes, units=ctx.units)
            )
            if len(trace) > 0:
                ctx.set_info(f"{ctx.value_key} · {len(trace)} points · Max: {np.max(display_trace):.3g}")

        elif self.dimensionality == "2D":
            image = np.asarray(data.get(ctx.value_key, []), dtype=float)
            if image.size == 0:
                return
            self.viewer.show_data(DataRaw(ctx.value_key, data=[image], units=ctx.units))
            h, w = image.shape
            ctx.set_info(f"{w}×{h} · Max: {np.max(image):.0f}")

        else:  # ND — best effort: no real ND detector adapter exists yet in
            # this codebase to validate against (today's ND instruments are
            # all actuators, handled by MoveControlComponent instead), but
            # ViewerND is standalone-embeddable the same way as 0D/1D/2D, so
            # any future ND detector adapter is already supported here.
            arr = np.asarray(data.get(ctx.value_key, []), dtype=float)
            if arr.size == 0:
                return
            nav_indexes = tuple(range(arr.ndim - 2)) if arr.ndim > 2 else ()
            self.viewer.show_data(
                DataRaw(ctx.value_key, data=[arr], nav_indexes=nav_indexes, units=ctx.units)
            )
            ctx.set_info(f"shape {arr.shape}")
