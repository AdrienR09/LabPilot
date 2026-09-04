"""Generic actuator/source control component.

Covers what used to be three separate classes (Motor0DWindow,
Motor1DWindow, MotorMultiAxisWindow) plus SourceWindow's output control,
branching on what the schema actually declares rather than which
hand-written class got instantiated:

- A discrete-valued settable axis (a boolean, or a small-range integer
  like a 2-4 position switch/filter wheel) renders a Qudi
  switch_gui.py-style control — a two-state `ToggleSwitch` for a real
  bool, or a segmented `MultiStateSwitch` for anything with more than two
  states. No numeric target/move/scan makes sense for a discrete device.
- One numeric axis renders a qudi actuator_gui.py-style panel: current
  value in large text, a set-value spinbox with an Absolute/Relative
  mode choice, and Move To + Home buttons — everything in one compact
  dock (see `_build_single_axis`). Deliberately just this one, simplest
  control surface — no slider mode, no continuous-scan section — basic
  control over the instrument is the whole point of this window (a
  workflow's own scan/continuous-acquisition behavior belongs to that
  workflow's own UI, not duplicated here per instrument).
- Several numeric axes render one dock per axis (each built by its own
  `MoveControlComponent` sub-instance — no separate code path to keep in
  sync), tabified together via `QMainWindow.tabifyDockWidget` — real
  native Qt docking, matching qudi-sclab's actuator_gui.py/scanner.py
  dock-based layout. (A position-only 2D crosshair map was tried here in
  an earlier pass and dropped — it doesn't mean much without a real
  scanner+detector pairing, which is what a workflow's combined window is
  already for.)

A source's output (settable+readable "output", plus an optional separate
"enable" boolean) is just the single-numeric-axis case with an extra
enable toggle bolted on, so `SourceWindow` doesn't need to exist as its
own class either — `create_instrument_window` maps kind="source" to this
same component with the schema doing the rest of the work.
"""

from __future__ import annotations

from typing import Optional

import httpx
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from components.base import UIComponent
from components.widgets import (
    ProfessionalSpinBox, IconButton, ToggleSwitch, MultiStateSwitch,
    ValueReadout, StatusLabel, dock,
)
from components.schema_utils import move_axes
from main import LabPilotStyle


def _discrete_states(dtype: str, limits: Optional[tuple]) -> Optional[list]:
    """States list for a switch-like axis, or None if `axis` is really a
    continuous numeric value. A real bool axis is always 2-state
    ([False, True]); a small-range integer axis (e.g. limits (0, 3) for a
    4-position filter wheel) is treated the same way, capped at 8 states
    so the segmented switch stays usable."""
    if dtype == "bool":
        return [False, True]
    if limits and dtype in ("int32", "int64", "int", "uint8", "uint16"):
        lo, hi = int(limits[0]), int(limits[1])
        if 0 <= hi - lo <= 7:
            return list(range(lo, hi + 1))
    return None


class MoveControlComponent(UIComponent):
    component_type = "move_control"
    default_params = {
        "axis": None,  # force a specific axis (used by per-axis docks below)
    }

    def build(self) -> None:
        window = self.window
        ctx = self.ctx
        schema = ctx.schema
        settable = schema.get("settable", {})
        forced_axis = self.params.get("axis")
        axes = [forced_axis] if forced_axis else move_axes(schema, ctx.instrument.kind)
        ctx.axes = axes

        if not axes and forced_axis is None:
            # A source with no genuine move-able axis (e.g. a microwave
            # source whose settable cw_*/scan_* keys don't overlap its
            # readable status fields, by design — see move_axes) — nothing
            # sensible to show here; settings_tree/actions cover its real
            # control surface instead.
            self.mode = "none"
            return

        axis0 = axes[0] if axes else None
        dtype = settable.get(axis0, "float64") if axis0 else "float64"
        limits = schema.get("limits", {}).get(axis0) if axis0 else None
        states = _discrete_states(dtype, limits)

        if states is not None:
            self.mode = "switch"
            self._build_switch(axis0, states)
        elif len(axes) <= 1:
            self.mode = "single"
            # A forced `axis` param means this instance is one of
            # _build_axis_tabs's per-axis sub-components — that method
            # adds and tabifies self._own_dock itself, once all sibling
            # axes' docks exist. Otherwise (a genuine standalone 1D
            # actuator) this is the only dock, so add it directly here.
            d = self._build_single_axis(axis0)
            if forced_axis is None:
                window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, d)
        else:
            self.mode = "tabs"
            self._build_axis_tabs(axes)

        # Sources separate an enable/output-on line from the setpoint —
        # Qudi's laser GUIs always show these as two distinct controls.
        # Only meaningful alongside the single-axis layout (a source has
        # exactly one output), and only if the schema actually has one.
        self.enable_key = None
        if ctx.instrument.kind == "source" and self.mode == "single":
            self.enable_key = next(
                (k for k, dt in settable.items() if dt == "bool" and k != axis0),
                None,
            )
            if self.enable_key:
                self._add_enable_toggle()

    # ---- discrete switch (Motor0D / switch_gui.py style) ----

    def _build_switch(self, axis: Optional[str], states: list) -> None:
        window = self.window
        ctx = self.ctx
        self.axis = axis
        self.states = states
        self.current_state = states[0]

        central = QWidget()
        layout = QGridLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setHorizontalSpacing(12)
        layout.setSizeConstraint(QGridLayout.SizeConstraint.SetFixedSize)

        name_label = QLabel(ctx.instrument.name)
        name_label.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(name_label, 0, 0, 1, 3)

        label = QLabel(f"{axis or 'state'}:")
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        label.setFont(font)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label, 1, 0)

        # NOTE: `states == [False, True]` would also match `[0, 1]` in
        # Python (0 == False, 1 == True) — an isinstance check is needed to
        # actually tell a real bool axis apart from a 2-state int one.
        is_bool = all(isinstance(s, bool) for s in states)
        if is_bool:
            # Genuine bool axis — keep the existing animated toggle look
            # unchanged for every actuator that already used it.
            self._state_labels = {False: "OFF", True: "ON"}
            self._switch_widget = ToggleSwitch()
            self._switch_widget.toggled.connect(self._write_switch)
        else:
            self._state_labels = (
                {0: "Off", 1: "On"} if states == [0, 1] else {v: f"State {v}" for v in states}
            )
            self._switch_widget = MultiStateSwitch(self._state_labels)
            self._switch_widget.stateChanged.connect(self._write_switch)
        layout.addWidget(self._switch_widget, 1, 1)

        self.state_text = StatusLabel(self._state_labels[self.current_state], font=font, center=False)
        layout.addWidget(self.state_text, 1, 2)

        d = dock("Switch", window)
        d.setWidget(central)
        window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, d)

        if axis is not None:
            try:
                data = ctx.client.read(ctx.instrument.id)
                if axis in data:
                    self._sync_switch(data[axis])
            except Exception as e:
                ctx.set_status(f"Read failed: {e}")

    def _write_switch(self, value) -> None:
        ctx = self.ctx
        if self.axis is None:
            return
        previous = self.current_state
        try:
            ctx.client.write(ctx.instrument.id, {self.axis: value})
            self._sync_switch(value)
            ctx.set_status(f"{self.axis} set to {self._state_labels.get(value, value)}")
        except httpx.HTTPStatusError as e:
            ctx.set_status(f"Write failed: {e.response.status_code} {e.response.text}")
            self._sync_switch(previous)
        except Exception as e:
            ctx.set_status(f"Write failed: {e}")
            self._sync_switch(previous)

    def _sync_switch(self, value) -> None:
        self.current_state = value
        if isinstance(self._switch_widget, ToggleSwitch):
            self._switch_widget.setChecked(bool(value), animate=False)
        else:
            self._switch_widget.setCurrentValue(value)
        is_on = value not in (0, False, None)
        color = LabPilotStyle.SUCCESS if is_on else LabPilotStyle.TEXT_MUTED
        self.state_text.set_status(self._state_labels.get(value, str(value)), color)

    # ---- single numeric axis (qudi actuator_gui.py style) ----

    def _build_single_axis(self, axis: Optional[str]) -> "QDockWidget":
        window = self.window
        ctx = self.ctx
        self.axis = axis
        self.current_value = 0.0
        self._last_commanded_target: Optional[float] = None
        units = ctx.schema.get("units", {}).get(axis, "") if axis else ""
        limits = ctx.schema.get("limits", {}).get(axis) if axis else None
        self.limits = tuple(limits) if limits else (-1000.0, 1000.0)
        self.units = units
        lo, hi = self.limits

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        name_label = QLabel(f"{ctx.instrument.name}" + (f" — {axis.upper()}" if axis else ""))
        name_label.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(name_label)

        # ---- current value: large ----
        pos_label = QLabel(f"Current {axis or 'Value'}")
        pos_label.setProperty("class", "subtitle")
        pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_display = ValueReadout(units, font_size=40, unit_font_size=14, center=True)
        self.status_label = StatusLabel("Ready")

        layout.addWidget(pos_label)
        layout.addWidget(self.value_display)
        layout.addWidget(self.status_label)
        self._content_layout = layout

        # ---- set value: spinbox + abs/rel + Move To/Home ----
        set_row = QHBoxLayout()
        set_row.addWidget(QLabel("Set value:"))
        self.displacement_spinbox = ProfessionalSpinBox(lo, hi, 3, units)
        self.displacement_spinbox.setValue(0.0)
        set_row.addWidget(self.displacement_spinbox)
        layout.addLayout(set_row)

        mode_row = QHBoxLayout()
        self.abs_radio = QRadioButton("Absolute")
        self.rel_radio = QRadioButton("Relative")
        self.abs_radio.setChecked(True)
        self._mode_group = QButtonGroup(content)
        self._mode_group.addButton(self.abs_radio)
        self._mode_group.addButton(self.rel_radio)
        self.abs_radio.toggled.connect(self._on_mode_toggled)
        mode_row.addWidget(self.abs_radio)
        mode_row.addWidget(self.rel_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        btn_row = QHBoxLayout()
        move_btn = IconButton("Move To", "go-next")
        move_btn.clicked.connect(self.move_to_target)
        home_btn = IconButton("Home", "go-home")
        home_btn.clicked.connect(self.home)
        btn_row.addWidget(move_btn)
        btn_row.addWidget(home_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        d = dock(f"{(axis or ctx.instrument.name).upper()}", window)
        d.setWidget(content)
        d.setMaximumHeight(320)  # bounded, fixed content — don't let the
        # dock area stretch it beyond what it actually needs.
        self._own_dock = d
        return d

    def _add_enable_toggle(self) -> None:
        """Only reached for sources with a separate enable/output-on line —
        inserted directly into the main single-axis dock, right below the
        status line (Qudi's simple_laser_gui.py convention: the ON/OFF
        toggle sits next to the power display, not in its own floating
        dock for a single switch)."""
        row = QHBoxLayout()
        row.addWidget(QLabel(f"{self.enable_key}:"))
        self.enable_toggle = ToggleSwitch()
        self.enable_toggle.toggled.connect(self._write_enable)
        row.addWidget(self.enable_toggle)
        row.addStretch()
        self._content_layout.insertLayout(4, row)

    def _write_enable(self, state: bool) -> None:
        ctx = self.ctx
        try:
            ctx.client.write(ctx.instrument.id, {self.enable_key: state})
            ctx.set_status(f"{self.enable_key} set to {'ON' if state else 'OFF'}")
        except httpx.HTTPStatusError as e:
            ctx.set_status(f"Set failed: {e.response.status_code} {e.response.text}")
            self.enable_toggle.setChecked(not state, animate=False)
        except Exception as e:
            ctx.set_status(f"Set failed: {e}")
            self.enable_toggle.setChecked(not state, animate=False)

    def _on_mode_toggled(self, _checked: bool) -> None:
        # Re-center the spinbox's meaning when switching abs/rel: absolute
        # shows/edits the real target, relative starts back at 0 (an
        # offset from wherever the axis is right now).
        if self.abs_radio.isChecked():
            self.displacement_spinbox.setValue(self.current_value)
        else:
            self.displacement_spinbox.setValue(0.0)

    def home(self) -> None:
        ctx = self.ctx
        if self.axis is None:
            return
        try:
            ctx.client.write(ctx.instrument.id, {self.axis: 0.0})
            self._last_commanded_target = 0.0
            self.status_label.set_status("Moving...", LabPilotStyle.PRIMARY)
            ctx.set_status(f"Homing {self.axis}")
        except httpx.HTTPStatusError as e:
            ctx.set_status(f"Home failed: {e.response.status_code} {e.response.text}")
        except Exception as e:
            ctx.set_status(f"Home failed: {e}")

    def move_to_target(self) -> None:
        ctx = self.ctx
        if self.axis is None:
            return
        value = self.displacement_spinbox.value()
        target = value if self.abs_radio.isChecked() else self.current_value + value
        try:
            ctx.client.write(ctx.instrument.id, {self.axis: target})
            self._last_commanded_target = target
            self.status_label.set_status("Moving...", LabPilotStyle.PRIMARY)
            ctx.set_status(f"Moving to {target:.3f} {self.units}")
        except httpx.HTTPStatusError as e:
            ctx.set_status(f"Move failed: {e.response.status_code} {e.response.text}")
        except Exception as e:
            ctx.set_status(f"Move failed: {e}")

    # ---- multiple numeric axes: one real dock per axis, tabified ----

    def _build_axis_tabs(self, axes: list[str]) -> None:
        """One `QDockWidget` per axis (each built by its own
        `MoveControlComponent` sub-instance via `_build_single_axis`),
        tabified together via `QMainWindow.tabifyDockWidget` — real
        native Qt docking (auto-resizes/floats/rearranges correctly),
        matching qudi-sclab's actuator_gui.py dock-based layout rather
        than a hand-rolled QTabWidget shim."""
        window = self.window
        ctx = self.ctx

        self._axis_components: list[MoveControlComponent] = []
        all_docks = []
        for axis in axes:
            sub = MoveControlComponent(window, ctx, axis=axis)
            sub.build()
            ctx.components.append(sub)
            self._axis_components.append(sub)
            if sub._own_dock is not None:
                all_docks.append(sub._own_dock)

        for d in all_docks:
            window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, d)
        for other in all_docks[1:]:
            window.tabifyDockWidget(all_docks[0], other)
        if all_docks:
            all_docks[0].raise_()  # show the first axis' tab active

    # ---- data dispatch ----

    def on_data(self, data: dict) -> None:
        if self.mode == "switch":
            if self.axis is not None and self.axis in data:
                self._sync_switch(data[self.axis])
        elif self.mode == "single":
            if self.enable_key and self.enable_key in data:
                self.enable_toggle.setChecked(bool(data[self.enable_key]), animate=False)
            if self.axis is None or self.axis not in data:
                return
            self.current_value = float(data[self.axis])
            self.value_display.set_value(f"{self.current_value:.3f}")
            if (
                self._last_commanded_target is not None
                and abs(self.current_value - self._last_commanded_target) < 0.02
            ):
                self.status_label.set_status("Ready", LabPilotStyle.SUCCESS)
        # "tabs" mode: sub-components are registered directly in
        # ctx.components and handle their own on_data — nothing to do here.
