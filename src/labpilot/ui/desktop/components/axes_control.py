"""Axes Control — qudi's own `axes_control_dockwidget.py`-style
always-visible dock, plus an on-demand dialog for what's genuinely
infrequent to touch:

- `AxesControlWidget` — one row per axis, laid out target-first
  ("the current target position should be on the left side of the
  sliders, in front of the x, y, z labels") then range/resolution last
  ("the scanning range min/max + number of points should be on the right
  side of the axes"): [target | axis label | slider | min | max |
  points]. Built from an `AxisSliderRow` per axis for the target/slider/
  min/max relationship (dragging the slider still updates the target,
  etc.) — but that row's own container widget is never shown; its child
  widgets are pulled out and placed directly into this dock's own grid,
  in the order above, alongside a Points spinbox `AxisSliderRow` doesn't
  have. Min/Max/Points here commit straight to AXIS_RANGES; which-axes-
  scan still only lives in `AxisRangeSettingsDialog`.

- `AxisRangeSettingsDialog` — a QDialog opened on demand (Settings menu,
  see workflow_window.py): per-axis Scan checkbox, resolution (# points),
  and Min/Max range with hardware-limits-aware "Full Range" — what you
  set up less often, matching qudi's own `ScannerSettingDialog`'s
  OK/Cancel/Apply pattern. Its Min/Max/Points duplicate what the row
  above now also allows, since either surface can be the quicker one
  depending on whether you're eyeballing a live view or setting up cold.

- `OptimizerSettingsDialog` — the same on-demand-dialog shape, for the
  optimizer capability instead of the main scan: per-axis Optimize
  checkbox ("select if you want to optimize along one dimension or
  multiple dimensions"), search Range, and Points. Its Range is
  bidirectionally linked with the corresponding scan panel's own green
  crosshair box (`NDScanResultView.axis_box_full_width`/
  `set_axis_box_full_width`, see workflow_window.py's
  `_open_optimizer_settings`) — pre-filled from whatever the box
  currently shows each time it's opened, and pushing a typed-in value
  straight back into that same box.
"""

from __future__ import annotations

from typing import Callable, Optional

from components.widgets import AxisSliderRow, ProfessionalSpinBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

__all__ = ["AxesControlWidget", "AxisRangeSettingsDialog", "OptimizerSettingsDialog"]


class AxesControlWidget(QWidget):
    def __init__(
        self,
        axis_ranges: dict[str, tuple],
        scan_axes: list,
        hold_positions: dict[str, float],
        units: dict[str, str],
        on_move: Callable[[str, float], None],
        on_hold_changed: Callable[[dict], None],
        on_range_changed: Optional[Callable[[str, float, float], None]] = None,
        on_points_changed: Optional[Callable[[str, int], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """`on_move(axis, value)` is called (debounced, live while
        dragging) whenever an axis's slider/target moves — a live
        actuator write, independent of whether that axis happens to be
        currently scanned. `on_hold_changed(hold_positions)` is called
        with the *complete* updated HOLD_POSITIONS dict whenever a HELD
        (not currently scanned) axis's target commits. `on_range_changed
        (axis, lo, hi)`/`on_points_changed(axis, n)` fire whenever that
        axis's Min/Max or Points spinboxes commit a new value —
        which-axes-scan still only lives in AxisRangeSettingsDialog."""
        super().__init__(parent)
        self._axis_names = list(axis_ranges.keys())
        self._on_move = on_move
        self._on_hold_changed = on_hold_changed
        self._on_range_changed = on_range_changed
        self._on_points_changed = on_points_changed
        self._scanning_axes: set[str] = set(scan_axes)
        self._hold_positions: dict[str, float] = dict(hold_positions)
        self._rows: dict[str, AxisSliderRow] = {}
        self._points_boxes: dict[str, ProfessionalSpinBox] = {}
        self._pending_moves: dict[str, float] = {}

        self._live_write_timer = QTimer()
        self._live_write_timer.setSingleShot(True)
        self._live_write_timer.setInterval(30)
        self._live_write_timer.timeout.connect(self._commit_pending_moves)

        layout = QGridLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        bold = QFont()
        bold.setBold(True)

        # Column order: target | axis | slider | min | max | points — see
        # class docstring.
        for col, text in enumerate(["Target", "Axis", "", "Min", "Max", "Points"]):
            if not text:
                continue
            header = QLabel(text)
            header.setFont(bold)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(header, 0, col)

        for row, name in enumerate(self._axis_names, start=1):
            lo, hi, n = axis_ranges[name]
            hold = hold_positions.get(name, (lo + hi) / 2)

            axis_label = QLabel(name)
            axis_label.setFont(bold)
            axis_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # AxisSliderRow still owns the target/slider/min/max
            # relationship (dragging the slider updates the target, its
            # range spinboxes narrow the slider's mapping, etc.) — its own
            # container widget/layout is just never shown; its child
            # widgets are pulled out below and placed directly into this
            # dock's own grid, in this dock's own column order. Their
            # signal wiring (made against each other in AxisSliderRow's
            # own __init__) doesn't depend on which layout they're
            # visually parented under, so this reparenting is safe.
            slider_row = AxisSliderRow(lo, hi, 4, units.get(name, ""))
            slider_row.range_min_spinbox.setValue(lo)
            slider_row.range_max_spinbox.setValue(hi)
            slider_row.set_value(hold)
            for w in (
                slider_row.target_spinbox, slider_row.slider,
                slider_row.range_min_spinbox, slider_row.range_max_spinbox,
            ):
                slider_row.layout().removeWidget(w)

            points_box = ProfessionalSpinBox(1, 100000, 0, "pts")
            points_box.setValue(n)
            points_box.editingFinished.connect(lambda name=name: self._on_points_committed(name))

            layout.addWidget(slider_row.target_spinbox, row, 0)
            layout.addWidget(axis_label, row, 1)
            layout.addWidget(slider_row.slider, row, 2)
            layout.addWidget(slider_row.range_min_spinbox, row, 3)
            layout.addWidget(slider_row.range_max_spinbox, row, 4)
            layout.addWidget(points_box, row, 5)

            self._rows[name] = slider_row
            self._points_boxes[name] = points_box

            slider_row.valueChangedLive.connect(lambda v, name=name: self._schedule_move(name, v))
            slider_row.valueCommitted.connect(lambda v, name=name: self._on_target_committed(name, v))
            slider_row.rangeChanged.connect(lambda lo, hi, name=name: self._on_range_committed(name, lo, hi))

        layout.setColumnStretch(2, 1)

    # ---- live jog (debounced) ----

    def _schedule_move(self, name: str, value: float) -> None:
        self._pending_moves[name] = value
        self._live_write_timer.start()

    def _commit_pending_moves(self) -> None:
        pending, self._pending_moves = self._pending_moves, {}
        for name, value in pending.items():
            self._on_move(name, value)

    def _on_target_committed(self, name: str, value: float) -> None:
        self._schedule_move(name, value)
        if name not in self._scanning_axes:
            # A held axis's target IS its HOLD_POSITIONS entry — persist it
            # alongside the live move so the next run holds at the new spot.
            self._hold_positions[name] = value
            self._on_hold_changed(dict(self._hold_positions))

    def _on_range_committed(self, name: str, lo: float, hi: float) -> None:
        if self._on_range_changed is not None:
            self._on_range_changed(name, lo, hi)

    def _on_points_committed(self, name: str) -> None:
        if self._on_points_changed is not None:
            self._on_points_changed(name, int(self._points_boxes[name].value()))

    # ---- kept in sync with AxisRangeSettingsDialog's last commit ----

    def set_scanning_axes(self, scan_axes: list) -> None:
        """Which axes currently count as "scanned" (their target is
        informational, updated from live polling) vs "held" (their
        target IS the write-through hold position) — updated after
        AxisRangeSettingsDialog commits a new SCAN_AXES."""
        self._scanning_axes = set(scan_axes)

    def set_range(self, name: str, lo: float, hi: float) -> None:
        """Updates one axis's row after AxisRangeSettingsDialog commits a
        new Min/Max (or its "Full Range" button widens past this row's
        current bounds) — uses AxisSliderRow.set_range_bounds() rather
        than poking its spinboxes' values directly, since those
        spinboxes' own min/max are otherwise fixed at construction to the
        *original* range, so a plain .setValue() to a wider value would
        just get silently clamped back."""
        slider_row = self._rows.get(name)
        if slider_row is None:
            return
        slider_row.set_range_bounds(lo, hi)

    def set_points(self, name: str, n: int) -> None:
        """Updates one axis's Points spinbox after AxisRangeSettingsDialog
        commits a new resolution — kept in sync since both surfaces edit
        the same AXIS_RANGES entry now."""
        box = self._points_boxes.get(name)
        if box is None:
            return
        box.blockSignals(True)
        box.setValue(n)
        box.blockSignals(False)

    def set_target(self, name: str, value: float) -> None:
        """External target update for one axis — e.g. the crosshair on a
        scan panel being dragged (workflow_window.py wires the two
        together bidirectionally: both this row's target spinbox/slider
        and the crosshair display the same commanded target, so dragging
        either one updates the other — "you move the crosshair and [it]
        should reflect into the slider position... and the opposite").
        NOT a live/current position readback — see class docstring; uses
        AxisSliderRow.set_value(), which already blocks its own signals,
        so this can't feed back into a write it's only meant to display."""
        slider_row = self._rows.get(name)
        if slider_row is not None:
            slider_row.set_value(value)

    def set_locked(self, locked: bool) -> None:
        """Disabled while the workflow is running — same reasoning as
        qudi disabling its axes-control spinboxes during an active scan.
        Each sub-widget is disabled individually (not via slider_row
        itself — its child widgets were reparented out into this dock's
        own layout at construction, see __init__, so slider_row is no
        longer their effective container)."""
        for name, slider_row in self._rows.items():
            slider_row.target_spinbox.setEnabled(not locked)
            slider_row.slider.setEnabled(not locked)
            slider_row.range_min_spinbox.setEnabled(not locked)
            slider_row.range_max_spinbox.setEnabled(not locked)
            self._points_boxes[name].setEnabled(not locked)


class AxisRangeSettingsDialog(QDialog):
    """qudi `ScannerSettingDialog`-style on-demand settings window (see
    module docstring) — per-axis Scan checkbox, resolution (# points),
    and Min/Max range, with an OK/Cancel/Apply button row matching qudi's
    own dialog exactly. Opened fresh each time from workflow_window.py's
    Settings menu, pre-filled with this workflow's current AXIS_RANGES/
    SCAN_AXES/HOLD_POSITIONS — not kept alive/updated in the background.
    """

    def __init__(
        self,
        axis_ranges: dict[str, tuple],
        scan_axes: list,
        hold_positions: dict[str, float],
        units: dict[str, str],
        on_change: Callable[[list, dict, dict], None],
        parent: Optional[QWidget] = None,
        hardware_limits: Optional[dict[str, tuple]] = None,
    ) -> None:
        """`on_change(scan_axes, axis_ranges, hold_positions)` is called
        with the complete recomputed values on both Apply (dialog stays
        open) and OK (dialog then closes) — never on Cancel.

        `hardware_limits` (the bound actuator's own `DeviceSchema.limits`,
        e.g. `{"x": (-5.0, 5.0)}`) backs a "Full Range" button per axis —
        qudi's own `ScannerAxis` carries real per-axis hardware min/max
        separate from whatever a given scan chooses to sweep (see
        ARCHITECTURE_NOTES.md §4.1); this is that same distinction, using
        `limits` (already on every DeviceSchema, previously unused for
        this). An axis with no declared limit just gets no button."""
        super().__init__(parent)
        self.setWindowTitle("Axis Range Settings")
        self._on_change = on_change
        self._axis_names = list(axis_ranges.keys())
        self._hold_positions = dict(hold_positions)
        self._hardware_limits = hardware_limits or {}
        self._rows: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        grid = QGridLayout()

        bold = QFont()
        bold.setBold(True)
        for col, text in enumerate(["Scan", "Axis", "Points", "Min", "Max", ""]):
            label = QLabel(text)
            label.setFont(bold)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, col)

        for row, name in enumerate(self._axis_names, start=1):
            lo, hi, n = axis_ranges[name]

            check = QCheckBox()
            check.setChecked(name in scan_axes)
            grid.addWidget(check, row, 0, Qt.AlignmentFlag.AlignCenter)

            axis_label = QLabel(name)
            axis_label.setFont(bold)
            axis_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(axis_label, row, 1)

            points = ProfessionalSpinBox(1, 100000, 0, "pts")
            points.setValue(n)
            grid.addWidget(points, row, 2)

            min_box = ProfessionalSpinBox(-1e9, 1e9, 4, units.get(name, ""))
            min_box.setValue(lo)
            grid.addWidget(min_box, row, 3)

            max_box = ProfessionalSpinBox(-1e9, 1e9, 4, units.get(name, ""))
            max_box.setValue(hi)
            grid.addWidget(max_box, row, 4)

            self._rows[name] = {"check": check, "points": points, "min": min_box, "max": max_box}

            if name in self._hardware_limits:
                full_range_button = QPushButton("Full Range")
                full_range_button.setToolTip(
                    f"Set to this axis's real hardware limits: {self._hardware_limits[name]}"
                )
                full_range_button.clicked.connect(lambda _checked=False, name=name: self._on_full_range(name))
                grid.addWidget(full_range_button, row, 5)

        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(4, 1)
        layout.addLayout(grid)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self._on_ok)
        button_box.rejected.connect(self.reject)
        apply_button = button_box.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.clicked.connect(self._on_apply)
        layout.addWidget(button_box)

    def _values(self) -> tuple[list, dict, dict]:
        scan_axes: list[str] = []
        axis_ranges: dict[str, tuple] = {}
        hold_positions: dict[str, float] = {}
        for name, row in self._rows.items():
            lo = row["min"].value()
            hi = row["max"].value()
            n = int(row["points"].value())
            axis_ranges[name] = (lo, hi, n)
            if row["check"].isChecked():
                scan_axes.append(name)
            else:
                hold_positions[name] = self._hold_positions.get(name, (lo + hi) / 2)
        return scan_axes, axis_ranges, hold_positions

    def _on_apply(self) -> None:
        self._on_change(*self._values())

    def _on_ok(self) -> None:
        self._on_change(*self._values())
        self.accept()

    def _on_full_range(self, name: str) -> None:
        lo, hi = self._hardware_limits[name]
        row = self._rows[name]
        row["min"].setValue(lo)
        row["max"].setValue(hi)


class OptimizerSettingsDialog(QDialog):
    """On-demand settings window for the optimizer capability (see module
    docstring) — per-axis Optimize checkbox, search Range, and Points,
    with an OK/Cancel/Apply button row matching `AxisRangeSettingsDialog`'s
    own pattern exactly. Opened fresh each time from workflow_window.py's
    Settings menu, pre-filled with whatever each axis's crosshair box
    currently shows plus the workflow window's own last-used axis
    selection/points — not kept alive/updated in the background.
    """

    def __init__(
        self,
        axis_names: list[str],
        selected_axes: list[str],
        ranges: dict[str, float],
        points: dict[str, int],
        units: dict[str, str],
        on_change: Callable[[list, dict, dict], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        """`on_change(selected_axes, ranges, points)` is called with the
        complete recomputed values on both Apply (dialog stays open) and
        OK (dialog then closes) — never on Cancel."""
        super().__init__(parent)
        self.setWindowTitle("Optimizer Settings")
        self._on_change = on_change
        self._axis_names = list(axis_names)
        self._rows: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        grid = QGridLayout()

        bold = QFont()
        bold.setBold(True)
        for col, text in enumerate(["Optimize", "Axis", "Range", "Points"]):
            label = QLabel(text)
            label.setFont(bold)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, col)

        for row, name in enumerate(self._axis_names, start=1):
            check = QCheckBox()
            check.setChecked(name in selected_axes)
            grid.addWidget(check, row, 0, Qt.AlignmentFlag.AlignCenter)

            axis_label = QLabel(name)
            axis_label.setFont(bold)
            axis_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(axis_label, row, 1)

            range_box = ProfessionalSpinBox(1e-9, 1e9, 4, units.get(name, ""))
            range_box.setValue(ranges.get(name, 1.0))
            grid.addWidget(range_box, row, 2)

            points_box = ProfessionalSpinBox(2, 100000, 0, "pts")
            points_box.setValue(points.get(name, 5))
            grid.addWidget(points_box, row, 3)

            self._rows[name] = {"check": check, "range": range_box, "points": points_box}

        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self._on_ok)
        button_box.rejected.connect(self.reject)
        apply_button = button_box.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.clicked.connect(self._on_apply)
        layout.addWidget(button_box)

    def _values(self) -> tuple[list, dict, dict]:
        selected = [name for name, row in self._rows.items() if row["check"].isChecked()]
        ranges = {name: row["range"].value() for name, row in self._rows.items()}
        points = {name: int(row["points"].value()) for name, row in self._rows.items()}
        return selected, ranges, points

    def _on_apply(self) -> None:
        self._on_change(*self._values())

    def _on_ok(self) -> None:
        self._on_change(*self._values())
        self.accept()
