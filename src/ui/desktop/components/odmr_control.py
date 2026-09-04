"""ODMR-specific workflow control docks — qudi's own `odmrgui.py` shape
(`OdmrScanControlDockWidget` + `OdmrCwControlDockWidget` + `OdmrFitDockWidget`,
read directly from github.com/Ulm-IQO/qudi-iqo-modules), adapted to
LabPilot's own tunable-workflow-param mechanism (`odmr_sweep.py`'s
SWEEP_START/SWEEP_STOP/SWEEP_POINTS/SWEEP_POWER/AVERAGES/FIT_SHAPE
constants, edited via PUT /api/workflows/{id}/params/{name}).

Dumb-view widgets, same convention as `components/axes_control.py`'s
`AxesControlWidget`: they only emit signals and hold no `self.client` of
their own — `workflow_window.py`'s `_add_odmr_sweep_control` wires those
signals to the actual PUT/write/action calls, same separation the axes
control already uses.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QSpinBox, QComboBox, QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal
import pyqtgraph as pg

from components.widgets import IconButton


def _freq_spinbox(value: float, bounds: tuple = (1e5, 20e9)) -> pg.SpinBox:
    return pg.SpinBox(value=value, bounds=bounds, suffix="Hz", siPrefix=True, step=1e6, dec=True, minStep=1.0)


def fit_dip(x, y, shape: str = "lorentzian") -> "dict | None":
    """Independent copy of `core/analysis/fits.py`'s `fit_dip`/`fit_peak`
    (same formulas — keep in sync if that model ever changes), matching
    this project's existing convention (`components/viewer.py`'s
    `_fit_peak` docstring) of the desktop app keeping its own fit code
    rather than importing `core.analysis.fits` — this one exists so the
    ODMR Fit dock can re-fit instantly against whatever the result view
    currently shows, with no backend round-trip and no hardware re-run.
    Returns {center, amplitude, fwhm, baseline}, or None if it didn't
    converge."""
    import numpy as np
    from scipy.optimize import curve_fit

    x = np.asarray(x, dtype=float)
    y = -np.asarray(y, dtype=float)  # invert about zero — dip becomes a peak
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
        popt, _ = curve_fit(model, x, y, p0=[amplitude0, center0, width0, baseline], maxfev=5000)
    except Exception:
        return None

    amp, x0, w, base = popt
    fwhm = abs(w) * (2.3548 if shape == "gaussian" else 2.0)
    return {"center": float(x0), "amplitude": float(amp), "fwhm": float(fwhm), "baseline": -float(base)}


def evaluate_dip(fit: dict, x, shape: str = "lorentzian") -> list:
    """Reconstructs a `fit_dip()` result's curve over `x`, for the result
    view's overlay — same formula as `core/analysis/fits.py`'s
    `evaluate_dip`."""
    import numpy as np

    x = np.asarray(x, dtype=float)
    amp, x0, base = fit["amplitude"], fit["center"], fit["baseline"]
    if shape == "lorentzian":
        gamma = fit["fwhm"] / 2.0
        y = base - amp * gamma**2 / ((x - x0) ** 2 + gamma**2)
    else:
        sigma = fit["fwhm"] / 2.3548
        y = base - amp * np.exp(-((x - x0) ** 2) / (2 * sigma**2))
    return y.tolist()


def _power_spinbox(value: float, bounds: tuple = (-60.0, 20.0)) -> pg.SpinBox:
    return pg.SpinBox(value=value, bounds=bounds, suffix="dBm", step=0.5)


class OdmrSweepControlWidget(QWidget):
    """Qudi's "Scan Parameters" group (start/stop/points/power) plus
    "Runtime Parameters"' averaging count, folded into one compact
    column — LabPilot's `odmr_sweep.py` supports exactly one frequency
    range (see that template's docstring), so this skips qudi's Add/
    Remove-range table entirely rather than building UI for a capability
    that doesn't exist yet. Also hosts a compact CW "park" mini-section
    (qudi's separate `OdmrCwControlDockWidget`) — folded in here rather
    than a second dock, since it's only two spinboxes and two buttons.
    """

    sigStartChanged = pyqtSignal(float)
    sigStopChanged = pyqtSignal(float)
    sigPointsChanged = pyqtSignal(int)
    sigPowerChanged = pyqtSignal(float)
    sigAveragesChanged = pyqtSignal(int)
    sigCwFrequencyChanged = pyqtSignal(float)
    sigCwPowerChanged = pyqtSignal(float)
    sigCwOnRequested = pyqtSignal()
    sigCwOffRequested = pyqtSignal()

    def __init__(
        self,
        start: float, stop: float, points: int, power: float, averages: int,
        has_cw: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        sweep_group = QGroupBox("Sweep")
        sweep_form = QFormLayout(sweep_group)
        self.start_spin = _freq_spinbox(start)
        self.stop_spin = _freq_spinbox(stop)
        self.points_spin = QSpinBox()
        self.points_spin.setRange(2, 10001)
        self.points_spin.setValue(int(points))
        self.power_spin = _power_spinbox(power)
        self.averages_spin = QSpinBox()
        self.averages_spin.setRange(1, 1000)
        self.averages_spin.setValue(int(averages))
        sweep_form.addRow("Start:", self.start_spin)
        sweep_form.addRow("Stop:", self.stop_spin)
        sweep_form.addRow("Points:", self.points_spin)
        sweep_form.addRow("Power:", self.power_spin)
        sweep_form.addRow("Averages:", self.averages_spin)
        layout.addWidget(sweep_group)

        self.start_spin.sigValueChanged.connect(lambda sb: self.sigStartChanged.emit(sb.value()))
        self.stop_spin.sigValueChanged.connect(lambda sb: self.sigStopChanged.emit(sb.value()))
        self.points_spin.editingFinished.connect(lambda: self.sigPointsChanged.emit(self.points_spin.value()))
        self.power_spin.sigValueChanged.connect(lambda sb: self.sigPowerChanged.emit(sb.value()))
        self.averages_spin.editingFinished.connect(lambda: self.sigAveragesChanged.emit(self.averages_spin.value()))

        self._cw_group: Optional[QGroupBox] = None
        if has_cw:
            cw_group = QGroupBox("MW CW Park")
            cw_form = QFormLayout(cw_group)
            self.cw_freq_spin = _freq_spinbox(start)
            self.cw_power_spin = _power_spinbox(power)
            cw_form.addRow("Frequency:", self.cw_freq_spin)
            cw_form.addRow("Power:", self.cw_power_spin)
            btn_row = QHBoxLayout()
            self.cw_on_button = IconButton("CW On", "media-playback-start")
            self.cw_off_button = IconButton("CW Off", "media-playback-stop")
            btn_row.addWidget(self.cw_on_button)
            btn_row.addWidget(self.cw_off_button)
            cw_form.addRow(btn_row)
            layout.addWidget(cw_group)
            self._cw_group = cw_group

            self.cw_freq_spin.sigValueChanged.connect(lambda sb: self.sigCwFrequencyChanged.emit(sb.value()))
            self.cw_power_spin.sigValueChanged.connect(lambda sb: self.sigCwPowerChanged.emit(sb.value()))
            self.cw_on_button.clicked.connect(lambda _checked=False: self.sigCwOnRequested.emit())
            self.cw_off_button.clicked.connect(lambda _checked=False: self.sigCwOffRequested.emit())

        layout.addStretch()

    def set_locked(self, locked: bool) -> None:
        """Sweep parameters are disabled while the workflow is running
        (qudi's `scan_parameters_set_enabled`) — editing the range mid-run
        wouldn't change anything already in flight. The CW park section
        stays enabled regardless; it drives the source directly, not the
        workflow's own params."""
        for w in (self.start_spin, self.stop_spin, self.points_spin, self.power_spin, self.averages_spin):
            w.setEnabled(not locked)


class OdmrFitControlWidget(QWidget):
    """Qudi's `OdmrFitDockWidget` (`FitWidget`) shape: a shape combobox,
    a Fit button, and a formatted result readout — scoped to LabPilot's
    two actually-supported dip shapes (`core/analysis/fits.py`'s
    `fit_dip`), not qudi's full pluggable model registry. Re-fitting is
    client-side and instant (see workflow_window.py's
    `_add_odmr_sweep_control` — reuses `components/viewer.py`'s
    `_fit_peak`), so this never touches the network; it's independent of
    whatever `FIT_SHAPE` the *next* run will use (as its own combobox
    write to that param) versus what's just being previewed here now."""

    sigFitRequested = pyqtSignal(str)  # shape
    sigShapeChanged = pyqtSignal(str)  # persisted as FIT_SHAPE for the next run

    _SHAPES = ["lorentzian", "gaussian"]

    def __init__(self, shape: str = "lorentzian", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        self.shape_combo = QComboBox()
        self.shape_combo.addItems([s.title() for s in self._SHAPES])
        if shape in self._SHAPES:
            self.shape_combo.setCurrentIndex(self._SHAPES.index(shape))
        self.fit_button = IconButton("Fit")
        row.addWidget(self.shape_combo, 1)
        row.addWidget(self.fit_button)
        layout.addLayout(row)

        self.result_label = QLabel("No fit yet")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_label)
        layout.addStretch()

        self.shape_combo.currentIndexChanged.connect(
            lambda _i: self.sigShapeChanged.emit(self._SHAPES[self.shape_combo.currentIndex()])
        )
        self.fit_button.clicked.connect(
            lambda _checked=False: self.sigFitRequested.emit(self._SHAPES[self.shape_combo.currentIndex()])
        )

    def set_result_text(self, text: str) -> None:
        self.result_label.setText(text)
