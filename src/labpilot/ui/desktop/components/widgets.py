"""Small reusable Qt widgets/helpers shared by several components.

Relocated from instrument_windows.py unchanged — these aren't UIComponent
subclasses themselves (they're plain Qt widgets/functions components build
with), just moved here as part of splitting the old monolithic file up.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDockWidget,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QWidget,
)

from labpilot.ui.desktop.main import LabPilotStyle


class ProfessionalSpinBox(QDoubleSpinBox):
    """Styled spin box for numeric parameter entry"""

    def __init__(self, minimum=0, maximum=9999, decimals=3, suffix="", parent=None):
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setDecimals(decimals)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setMinimumHeight(32)


class IconButton(QPushButton):
    """Button using a real Oxygen-set icon (see styles/icons/) instead of
    an emoji glyph — matches how Qudi's own toolbars/buttons look."""

    def __init__(self, text: str, icon_name: str = "", checkable: bool = False, parent=None):
        super().__init__(text, parent)
        if icon_name:
            self.setIcon(LabPilotStyle.icon(icon_name))
            self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(36)
        if checkable:
            self.setCheckable(True)


def toggle_icon(off_name: str, on_name: str) -> QIcon:
    """Build a QIcon whose pixmap swaps automatically with a checkable
    QAction's checked state — Qt handles the Off/On pixmap selection
    itself, no manual setIcon() calls needed on toggle. Matches Qudi's own
    start/stop-counter icon-swap toolbar buttons."""
    icon = QIcon()
    off_path = LabPilotStyle.ICONS_DIR / f"{off_name}.png"
    on_path = LabPilotStyle.ICONS_DIR / f"{on_name}.png"
    if off_path.exists():
        icon.addFile(str(off_path), QSize(22, 22), QIcon.Mode.Normal, QIcon.State.Off)
    if on_path.exists():
        icon.addFile(str(on_path), QSize(22, 22), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def dock(title: str, parent: QMainWindow) -> QDockWidget:
    d = QDockWidget(title, parent)
    d.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetMovable
        | QDockWidget.DockWidgetFeature.DockWidgetFloatable
    )
    return d


class ToggleSwitch(QWidget):
    """Animated on/off toggle switch. Qudi's real switch GUI uses a
    third-party `qtwidgets.ToggleSwitch` widget we don't depend on here —
    this is a compact from-scratch equivalent with the same look and feel:
    a rounded track and a sliding thumb that animates between states."""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._pos = 0.0
        self.setFixedSize(52, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"pos_frac", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animate: bool = True) -> None:
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        target = 1.0 if checked else 0.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._pos = target
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setChecked(not self._checked)
            self.toggled.emit(self._checked)
        super().mouseReleaseEvent(event)

    def _get_pos_frac(self) -> float:
        return self._pos

    def _set_pos_frac(self, value: float) -> None:
        self._pos = value
        self.update()

    pos_frac = pyqtProperty(float, _get_pos_frac, _set_pos_frac)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2

        off_color = QColor(LabPilotStyle.BG_TERTIARY)
        on_color = QColor(LabPilotStyle.PRIMARY)
        t = self._pos
        track_color = QColor(
            int(off_color.red() + (on_color.red() - off_color.red()) * t),
            int(off_color.green() + (on_color.green() - off_color.green()) * t),
            int(off_color.blue() + (on_color.blue() - off_color.blue()) * t),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)

        d = rect.height() - 6
        x = rect.left() + 3 + t * (rect.width() - d - 6)
        painter.setBrush(QColor('#ffffff'))
        painter.drawEllipse(QRectF(x, rect.top() + 3, d, d))


class AxisSliderRow(QWidget):
    """Qudi-style axis slider row — range-min spinbox | slider (expands) |
    range-max spinbox | target spinbox. The "molecule" behind
    `MoveControlComponent`'s slider mode (components/move_controls.py),
    extracted so any component needing a live-draggable numeric control
    (not just an actuator's move/home/scan panel) can reuse the same row
    instead of rebuilding it inline.

    The two range spinboxes narrow the slider's own value mapping (a
    sub-range for finer control), separate from the target spinbox's real
    min/max — same behavior as qudi-sclab's own
    scanner/axes_control_dockwidget.py this was modeled on.
    """

    valueChangedLive = pyqtSignal(float)  # fires continuously while dragging
    valueCommitted = pyqtSignal(float)  # fires once, on release / Enter
    rangeChanged = pyqtSignal(float, float)  # fires when range min/max spinboxes commit a valid new range

    def __init__(self, lo: float, hi: float, decimals: int = 3, units: str = "", parent=None):
        super().__init__(parent)
        self._range = (lo, hi)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.range_min_spinbox = ProfessionalSpinBox(lo, hi, decimals, units)
        self.range_min_spinbox.setValue(lo)
        self.range_min_spinbox.valueChanged.connect(self._on_range_changed)
        layout.addWidget(self.range_min_spinbox)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(500)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        layout.addWidget(self.slider, 1)

        self.range_max_spinbox = ProfessionalSpinBox(lo, hi, decimals, units)
        self.range_max_spinbox.setValue(hi)
        self.range_max_spinbox.valueChanged.connect(self._on_range_changed)
        layout.addWidget(self.range_max_spinbox)

        self.target_spinbox = ProfessionalSpinBox(lo, hi, decimals, units)
        self.target_spinbox.setValue((lo + hi) / 2)
        self.target_spinbox.editingFinished.connect(self._on_target_entered)
        layout.addWidget(self.target_spinbox)

    def _on_range_changed(self, _value=None) -> None:
        lo = self.range_min_spinbox.value()
        hi = self.range_max_spinbox.value()
        if hi <= lo:
            return  # ignore invalid ranges, same intent as qudi's own validation
        self._range = (lo, hi)
        self.rangeChanged.emit(lo, hi)

    def set_range_bounds(self, lo: float, hi: float) -> None:
        """Widens/narrows the slider's real range — unlike just calling
        range_min_spinbox/range_max_spinbox's own .setValue(), which
        silently clamps to each spinbox's OWN min/max (fixed at
        construction to the *initial* range and never otherwise
        revisited), this actually updates those bounds too, plus
        target_spinbox's (so a later set_value() with a value in the
        new, wider range isn't clamped either). For a caller that edited
        the range somewhere else (e.g. workflow_window.py's Axes Control
        dock reflecting AxisRangeSettingsDialog's last commit)."""
        for spinbox in (self.range_min_spinbox, self.range_max_spinbox, self.target_spinbox):
            spinbox.setRange(lo, hi)
        self.range_min_spinbox.blockSignals(True)
        self.range_max_spinbox.blockSignals(True)
        self.range_min_spinbox.setValue(lo)
        self.range_max_spinbox.setValue(hi)
        self.range_min_spinbox.blockSignals(False)
        self.range_max_spinbox.blockSignals(False)
        self._range = (lo, hi)

    def _slider_to_value(self, slider_value: int) -> float:
        lo, hi = self._range
        return lo + (hi - lo) * slider_value / 1000.0

    def _value_to_slider(self, value: float) -> int:
        lo, hi = self._range
        if hi == lo:
            return 0
        return int(max(0.0, min(1.0, (value - lo) / (hi - lo))) * 1000)

    def _on_slider_changed(self, value: int) -> None:
        target = self._slider_to_value(value)
        self.target_spinbox.blockSignals(True)
        self.target_spinbox.setValue(target)
        self.target_spinbox.blockSignals(False)
        self.valueChangedLive.emit(target)

    def _on_slider_released(self) -> None:
        self.valueCommitted.emit(self.value())

    def _on_target_entered(self) -> None:
        target = self.target_spinbox.value()
        self.slider.blockSignals(True)
        self.slider.setValue(self._value_to_slider(target))
        self.slider.blockSignals(False)
        self.valueCommitted.emit(target)

    def value(self) -> float:
        return self.target_spinbox.value()

    def set_value(self, value: float) -> None:
        """Programmatic update (e.g. from live poll data) — does not emit
        valueChangedLive/valueCommitted, so it can't feedback-loop into a
        write triggered by the same reading it's displaying."""
        self.target_spinbox.blockSignals(True)
        self.target_spinbox.setValue(value)
        self.target_spinbox.blockSignals(False)
        self.slider.blockSignals(True)
        self.slider.setValue(self._value_to_slider(value))
        self.slider.blockSignals(False)


class ValueReadout(QWidget):
    """Big colored numeric readout + unit label — the qudi-style "current
    value" display shared by `MoveControlComponent`'s single-axis dock and
    `TimeSeriesComponent`'s trend header (previously duplicated inline,
    identical except for font size)."""

    def __init__(
        self,
        units: str = "",
        font_size: int = 40,
        unit_font_size: Optional[int] = None,
        center: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if center:
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel("--")
        self.value_label.setFont(QFont("", font_size, QFont.Weight.Bold))
        self.value_label.setStyleSheet(
            f"color: {LabPilotStyle.PRIMARY}; font-family: 'Consolas', monospace;"
        )
        layout.addWidget(self.value_label)

        self.unit_label = QLabel(units)
        if unit_font_size is not None:
            self.unit_label.setFont(QFont("", unit_font_size))
        self.unit_label.setProperty("class", "muted")
        layout.addWidget(self.unit_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)

    def set_units(self, units: str) -> None:
        self.unit_label.setText(units)


class StatusLabel(QLabel):
    """Color-coded status text — the qudi-style "Ready"/"Moving"/"Error"
    (or "On"/"Off") indicator shared by `MoveControlComponent`'s
    single-axis status label and its switch-mode state text (previously
    duplicated setText()+setStyleSheet(color) call pairs in each)."""

    def __init__(
        self,
        text: str = "",
        color: str = "",
        font: Optional[QFont] = None,
        center: bool = True,
        parent=None,
    ):
        super().__init__(text, parent)
        if center:
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if font is not None:
            self.setFont(font)
        if color:
            self.setStyleSheet(f"color: {color};")

    def set_status(self, text: str, color: str) -> None:
        self.setText(text)
        self.setStyleSheet(f"color: {color};")


class MultiStateSwitch(QWidget):
    """Segmented-button switch for a discrete-valued axis with more than
    two states (e.g. a 4-position filter wheel) — the general case
    `ToggleSwitch` doesn't cover. Also used for a 2-state axis whose dtype
    isn't literally `"bool"` (e.g. an int32 state with limits (0, 1)),
    where `ToggleSwitch`'s look is kept only for genuine bool axes so
    existing switches don't change appearance."""

    stateChanged = pyqtSignal(object)  # emits the selected state's value

    def __init__(self, states: dict, parent=None):
        """`states`: ordered {value: label} — value is whatever should be
        written back (int/bool/str), label is what the button shows."""
        super().__init__(parent)
        self._values = list(states.keys())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        for value, label in states.items():
            btn = QPushButton(str(label))
            btn.setCheckable(True)
            btn.setMinimumHeight(32)
            self._group.addButton(btn)
            layout.addWidget(btn)
            self._buttons.append(btn)
        self._group.buttonClicked.connect(self._on_clicked)

    def _on_clicked(self, button: QPushButton) -> None:
        index = self._buttons.index(button)
        self.stateChanged.emit(self._values[index])

    def setCurrentValue(self, value) -> None:
        if value not in self._values:
            return
        index = self._values.index(value)
        self._buttons[index].setChecked(True)


