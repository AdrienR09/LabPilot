"""The pulse sequence editor's dock — a workflow control, not an instrument block.

This is the GUI of `workflow_templates/pulse_sequence_editor.py`, which
binds no instruments, so the dock never touches a device: every widget
edits one of the workflow's own parameters, and running the workflow
writes `~/.labpilot/sequences/<name>.json`.

The editor **is** the timeline (`pulse_timeline.py`): one lane per
instrument, pulses drawn on the lanes, sweep regions shaded across them.
That template declares no `RESULT_UI`, so this dock is the whole window
and the canvas gets nearly all of it — a second plot of the same picture
beside it used to take half the space, and it was the half you could not
edit. Everything here is chrome in a column to its right —

- **Sequence**: what the file will be called, and whether consecutive
  readouts alternate signal and reference.
- **Start from**: fill the canvas with one of `core/pulse/library.py`'s
  experiments. A starting point to edit, not a mode: once filled, the
  timeline is what gets saved, so a hand-moved gate stays moved.
- **Sweep**: what this sequence varies — nothing, a drawn time, or the
  microwave frequency — with its point count and spacing.
- **Rig**: the profile a sequence is written against — Rabi period, laser
  length and delay, wait time, the symbolic channel names, and whether
  the microwave channel carries an analog shape or gates an external
  source. Physics and naming conventions, not driver settings, which is
  exactly why they are editable with nothing plugged in.

## Two kinds of sweep, one control

A **time** sweep marks regions on the canvas and the pulser stretches
them: one pass plays every point. A **frequency** sweep leaves the drawn
pattern completely alone and steps the microwave source between passes,
because no pulse duration can encode a carrier frequency. Nothing else
about the two differs — same tracks, same measurement lane, same
extraction — so it is one combo box rather than a second editor, and the
regions controls simply have nothing to do in frequency mode.

## Where the lanes come from

The rig profile's symbolic channel names, never a connected pulser's
channel list. An offline editor has no pulser to ask, and a sequence that
took its channels from one is a sequence tied to one rig's wiring — the
thing the symbolic-channel decision exists to prevent.

A dumb view, the same convention `axes_control.py` follows: no client, no
network call. It emits `sigParamChanged(name, value)` and
`workflow_window.py` wires that to the PUT that stores the parameter.
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from components.pulse_timeline import PulseTimelineWidget
from components.widgets import IconButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labpilot.core.pulse.tracks import FREQUENCY, LINEAR, LOG, TIME, Timeline

__all__ = ["PulseEditorControlWidget"]

#: What "Start from" offers. Read from `core.pulse.library.GENERATORS` at
#: build time; this is only the fallback when that is unavailable, and the
#: order the well-known experiments should appear in.
_KNOWN = ("rabi", "ramsey", "hahn_echo", "t1", "pulsed_odmr")

#: How wide the settings column is. The canvas takes everything else,
#: which is the point of the split.
_PANEL_WIDTH = 380


def _sized(box: pg.SpinBox) -> pg.SpinBox:
    """Give a `pg.SpinBox` the height it actually needs.

    Its `sizeHint()` is zero high, so a form layout hands it whatever is
    left over and the text ends up clipped between the rows either side.
    Every spin box here goes through this.
    """
    box.setMinimumHeight(box.minimumSizeHint().height())
    return box


def _time_spinbox(value: float, step: float = 1e-9) -> pg.SpinBox:
    """Seconds with an SI prefix, which is the only way ns-to-ms ranges
    are readable in one control."""
    return _sized(pg.SpinBox(
        value=float(value), bounds=(0.0, None), suffix="s", siPrefix=True,
        step=step, dec=True, minStep=1e-12,
    ))


def _row(form: QFormLayout, label: str, widget: QWidget) -> tuple[QFormLayout, QWidget]:
    """Add a form row, and keep what is needed to hide the whole row.

    Hiding the field alone is not enough twice over: its label would be
    left pointing at the row below it, and `QFormLayout` keeps the empty
    row's height either way, so the rows below creep up under the ones
    above. `setRowVisible` removes the row from the layout properly.
    """
    form.addRow(label, widget)
    return (form, widget)


def _show(row: tuple[QFormLayout, QWidget], visible: bool) -> None:
    form, widget = row
    form.setRowVisible(widget, visible)


class PulseEditorControlWidget(QWidget):
    """The timeline canvas, plus the sequence, sweep and rig settings."""

    # Qt's own signal-naming convention, as in odmr_control.py and
    # axes_control.py — snake_case here would be the odd one out.
    sigParamChanged = pyqtSignal(str, object)
    sigGenerate = pyqtSignal()
    sigFillRequested = pyqtSignal(str)

    def __init__(
        self,
        params: dict[str, Any],
        generators: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._generators = list(generators or _KNOWN)
        self._params = dict(params)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.timeline = PulseTimelineWidget(
            Timeline.from_dict(self._params.get("TIMELINE") or {}),
            self.channels_from(self._params),
            readout=self.readout_from(self._params),
        )
        self.timeline.sigTimelineChanged.connect(self._on_timeline_changed)
        self.timeline.sigSelectionChanged.connect(lambda _pulse: self._describe())

        # Canvas left, settings right. A splitter rather than a fixed
        # layout so the column can be dragged away entirely on a small
        # screen — the canvas is the part that benefits from every pixel.
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.timeline)
        split.addWidget(self._side_panel())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1000, _PANEL_WIDTH])
        split.setCollapsible(0, False)
        layout.addWidget(split, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)
        self._describe()

    def _side_panel(self) -> QWidget:
        """Everything that is not the canvas, in one scrollable column."""
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(self._sequence_group())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._sweep_group(), "Sweep")
        self.tabs.addTab(self._build_rig_tab(), "Rig")
        column.addWidget(self.tabs, 1)

        self.generate_button = IconButton("Save sequence", "document-save")
        self.generate_button.setToolTip(
            "Validate what is drawn and write it to "
            "~/.labpilot/sequences/<name>.json"
        )
        self.generate_button.clicked.connect(lambda _checked=False: self.sigGenerate.emit())
        column.addWidget(self.generate_button)

        scroll = QScrollArea()
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(300)
        scroll.setMaximumWidth(_PANEL_WIDTH + 80)
        return scroll

    # --- Sequence ---------------------------------------------------------

    def _sequence_group(self) -> QGroupBox:
        box = QGroupBox("Sequence")
        form = QFormLayout(box)

        self.name_edit = QLineEdit(str(self._params.get("SEQUENCE_NAME", "")))
        self.name_edit.setPlaceholderText("Saved as ~/.labpilot/sequences/<name>.json")
        self.name_edit.editingFinished.connect(
            lambda: self.sigParamChanged.emit("SEQUENCE_NAME", self.name_edit.text())
        )
        form.addRow("Save as:", self.name_edit)

        start = QWidget()
        row = QHBoxLayout(start)
        row.setContentsMargins(0, 0, 0, 0)
        self.generator_combo = QComboBox()
        self.generator_combo.addItems(self._generators)
        current = str(self._params.get("START_FROM", self._generators[0]))
        if current in self._generators:
            self.generator_combo.setCurrentText(current)
        row.addWidget(self.generator_combo, 1)

        self.fill_button = IconButton("Fill", "document-import")
        self.fill_button.setToolTip(
            "Draw this experiment on the timeline, replacing what is there. "
            "A starting point to edit — once filled, the timeline is what "
            "gets saved."
        )
        self.fill_button.clicked.connect(
            lambda _checked=False: self.sigFillRequested.emit(
                self.generator_combo.currentText()
            )
        )
        row.addWidget(self.fill_button)
        form.addRow("Start from:", start)

        self.alternating_check = QCheckBox(
            "Alternating — every second readout is the reference"
        )
        self.alternating_check.setChecked(bool(self._params.get("ALTERNATING", False)))
        self.alternating_check.setToolTip(
            "Ramsey, Hahn echo and every experiment past Rabi measure each "
            "point twice with opposite final phases, and the analysis "
            "divides one by the other."
        )
        self.alternating_check.toggled.connect(
            lambda checked: self.sigParamChanged.emit("ALTERNATING", bool(checked))
        )
        form.addRow(self.alternating_check)
        return box

    # --- The Sweep tab ----------------------------------------------------

    def _sweep_group(self) -> QWidget:
        page = QWidget()
        # The form in its own widget above a stretch, so the rows keep
        # their natural heights instead of being spread down the tab.
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        box = QWidget()
        column.addWidget(box)
        column.addStretch(1)
        form = QFormLayout(box)

        self.quantity_combo = QComboBox()
        self.quantity_combo.addItem("Nothing — one fixed point", None)
        self.quantity_combo.addItem("Time — the shaded regions grow", TIME)
        self.quantity_combo.addItem("Microwave frequency", FREQUENCY)
        self.quantity_combo.setToolTip(
            "Time: the marked regions on the canvas stretch point by point "
            "and the pulser plays the whole sweep in one pass — Rabi, "
            "Ramsey, Hahn echo, T1.\n\n"
            "Microwave frequency: the drawn pattern never changes and the "
            "bound source steps between passes, because no pulse duration "
            "can encode a carrier. That is a pulsed ODMR, and it needs a "
            "'microwave' role bound when the measurement runs."
        )
        index = self.quantity_combo.findData(self._current_quantity())
        self.quantity_combo.setCurrentIndex(max(index, 0))
        self.quantity_combo.currentIndexChanged.connect(self._on_quantity_changed)
        form.addRow("Sweep over:", self.quantity_combo)

        self.sweep_name = QLineEdit(self._sweep_field("name", "tau"))
        self.sweep_name.editingFinished.connect(
            lambda: self.timeline.set_sweep(name=self.sweep_name.text() or "tau")
        )
        form.addRow("Name:", self.sweep_name)

        self.sweep_points = QSpinBox()
        self.sweep_points.setRange(1, 1_000_000)
        self.sweep_points.setValue(int(self._sweep_field("points", 50)))
        self.sweep_points.valueChanged.connect(
            lambda value: self.timeline.set_sweep(points=int(value))
        )
        form.addRow("Points:", self.sweep_points)

        self.spacing_combo = QComboBox()
        self.spacing_combo.addItem("Linear (constant step)", LINEAR)
        self.spacing_combo.addItem("Logarithmic (spans decades)", LOG)
        index = self.spacing_combo.findData(self._sweep_field("spacing", LINEAR))
        self.spacing_combo.setCurrentIndex(max(index, 0))
        self.spacing_combo.setToolTip(
            "A T1 decay spans decades, so linear spacing wastes almost every "
            "point. Log spacing becomes one block per point, since no "
            "constant increment produces a geometric series."
        )
        self.spacing_combo.currentIndexChanged.connect(self._on_spacing_changed)
        form.addRow("Spacing:", self.spacing_combo)

        self.sweep_step = _time_spinbox(self._sweep_field("step", 20e-9))
        self.sweep_step.sigValueChanged.connect(
            lambda box: self.timeline.set_sweep(step=float(box.value()))
        )
        self.step_row = _row(form, "Step:", self.sweep_step)

        self.sweep_start = _sized(pg.SpinBox(
            value=float(self._sweep_field("start_value", 2.82e9)),
            bounds=(0.0, None), suffix="Hz", siPrefix=True, step=1e6, dec=True,
        ))
        self.sweep_start.setToolTip("What the source emits at the first point.")
        self.sweep_start.sigValueChanged.connect(
            lambda box: self.timeline.set_sweep(start_value=float(box.value()))
        )
        self.start_row = _row(form, "First value:", self.sweep_start)

        self.sweep_stop = _time_spinbox(self._sweep_field("stop_value", 0.0))
        self.sweep_stop.sigValueChanged.connect(
            lambda box: self.timeline.set_sweep(stop_value=float(box.value()))
        )
        self.stop_row = _row(form, "Last value:", self.sweep_stop)

        self.sweep_stop_hz = _sized(pg.SpinBox(
            value=float(self._sweep_field("stop_value", 2.92e9)),
            bounds=(0.0, None), suffix="Hz", siPrefix=True, step=1e6, dec=True,
        ))
        self.sweep_stop_hz.sigValueChanged.connect(
            lambda box: self.timeline.set_sweep(stop_value=float(box.value()))
        )
        self.stop_hz_row = _row(form, "Last value:", self.sweep_stop_hz)

        self.region_buttons = QWidget()
        row = QHBoxLayout(self.region_buttons)
        row.setContentsMargins(0, 0, 0, 0)
        add = IconButton("Add region", "list-add")
        add.setToolTip(
            "Mark another interval that takes the same value. A Ramsey's "
            "tau appears once per alternating arm and a Hahn echo's twice, "
            "and they all grow together."
        )
        add.clicked.connect(lambda _checked=False: self.timeline.add_sweep_region())
        row.addWidget(add)
        form.addRow(self.region_buttons)

        self.sweep_hint = QLabel("")
        self.sweep_hint.setWordWrap(True)
        self.sweep_hint.setStyleSheet("color: #888;")
        form.addRow(self.sweep_hint)

        self._update_sweep_fields()
        return page

    def _sweep_field(self, key: str, default: Any) -> Any:
        sweep = (self._params.get("TIMELINE") or {}).get("sweep") or {}
        return sweep.get(key, default)

    def _current_quantity(self) -> str | None:
        sweep = (self._params.get("TIMELINE") or {}).get("sweep")
        return sweep.get("quantity", TIME) if sweep else None

    def _on_quantity_changed(self) -> None:
        self.timeline.set_sweep_quantity(self.quantity_combo.currentData())
        self._sync_sweep_fields()

    def _on_spacing_changed(self) -> None:
        self.timeline.set_sweep(spacing=self.spacing_combo.currentData())
        self._update_sweep_fields()

    def _update_sweep_fields(self) -> None:
        """Show only the fields this kind of sweep actually reads.

        A constant step and a last value are alternatives, not both, and a
        frequency sweep reads neither the step nor any region — showing a
        field that does nothing is how someone spends an afternoon tuning
        one that is never read.
        """
        quantity = self.quantity_combo.currentData()
        logarithmic = self.spacing_combo.currentData() == LOG
        frequency = quantity == FREQUENCY
        swept = quantity is not None

        for widget in (self.sweep_name, self.sweep_points, self.spacing_combo):
            widget.setEnabled(swept)
        _show(self.step_row, swept and not frequency and not logarithmic)
        _show(self.stop_row, swept and not frequency and logarithmic)
        _show(self.start_row, frequency)
        _show(self.stop_hz_row, frequency)
        self.region_buttons.setVisible(swept and not frequency)

        if not swept:
            self.sweep_hint.setText(
                "The sequence plays once, unchanged. One point, no axis."
            )
        elif frequency:
            self.sweep_hint.setText(
                "Nothing is marked on the canvas: the pattern plays unchanged "
                "and the bound microwave source steps between passes. The "
                "measurement needs a 'microwave' role bound."
            )
        else:
            self.sweep_hint.setText(
                "The shaded regions take this value; everything after them "
                "shifts as they grow."
            )

    # --- The Rig tab ------------------------------------------------------

    def _build_rig_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        timing = QGroupBox("Timing")
        timing_form = QFormLayout(timing)
        self._rig_spins: dict[str, pg.SpinBox] = {}
        for label, name, default in (
            ("Rabi period:", "RABI_PERIOD", 200e-9),
            ("Laser length:", "LASER_LENGTH", 3e-6),
            ("Laser delay:", "LASER_DELAY", 700e-9),
            ("Wait time:", "WAIT_TIME", 1e-6),
        ):
            spin = _time_spinbox(self._params.get(name, default))
            spin.sigValueChanged.connect(
                lambda sb, key=name: self.sigParamChanged.emit(key, sb.value())
            )
            timing_form.addRow(label, spin)
            self._rig_spins[name] = spin
        self.rabi_hint = QLabel("")
        self.rabi_hint.setStyleSheet("color: #888;")
        timing_form.addRow("", self.rabi_hint)
        self._rig_spins["RABI_PERIOD"].sigValueChanged.connect(
            lambda sb: self._update_rabi_hint(sb.value())
        )
        self._update_rabi_hint(self._params.get("RABI_PERIOD", 200e-9))
        layout.addWidget(timing)

        drive = QGroupBox("Microwave")
        drive_form = QFormLayout(drive)
        self.frequency_spin = _sized(pg.SpinBox(
            value=float(self._params.get("MW_FREQUENCY", 2.87e9)),
            bounds=(0.0, None), suffix="Hz", siPrefix=True, step=1e6, dec=True,
        ))
        self.frequency_spin.sigValueChanged.connect(
            lambda sb: self.sigParamChanged.emit("MW_FREQUENCY", sb.value())
        )
        self.amplitude_spin = _sized(pg.SpinBox(
            value=float(self._params.get("MW_AMPLITUDE", 0.25)),
            bounds=(0.0, None), suffix="V", siPrefix=True, step=0.01,
        ))
        self.amplitude_spin.sigValueChanged.connect(
            lambda sb: self.sigParamChanged.emit("MW_AMPLITUDE", sb.value())
        )
        self.analog_check = QCheckBox("Analog drive (an AWG synthesises the pulse)")
        self.analog_check.setChecked(bool(self._params.get("ANALOG_MW", True)))
        self.analog_check.setToolTip(
            "Unchecked describes a digital-only rig — a PulseBlaster gating "
            "an external microwave source. The sequences are identical either "
            "way; only this flag changes."
        )
        self.analog_check.toggled.connect(
            lambda checked: self._on_analog_toggled(bool(checked))
        )
        drive_form.addRow("Frequency:", self.frequency_spin)
        drive_form.addRow("Amplitude:", self.amplitude_spin)
        drive_form.addRow(self.analog_check)
        layout.addWidget(drive)

        channels = QGroupBox("Symbolic channels")
        channels.setToolTip(
            "Names, not wiring. The mapping onto a pulser's physical "
            "channels belongs to the measurement workflow's bindings, so "
            "this file runs on any rig."
        )
        channel_form = QFormLayout(channels)
        self._channel_edits: dict[str, QLineEdit] = {}
        for label, name, default in (
            ("Laser:", "LASER_CHANNEL", "laser"),
            ("Microwave:", "MW_CHANNEL", "mw"),
            ("APD readout:", "GATE_CHANNEL", "gate"),
        ):
            edit = QLineEdit(str(self._params.get(name, default) or ""))
            edit.editingFinished.connect(
                lambda key=name, w=edit: self._on_channel_renamed(
                    key, w.text().strip() or None
                )
            )
            channel_form.addRow(label, edit)
            self._channel_edits[name] = edit
        self._channel_edits["GATE_CHANNEL"].setPlaceholderText(
            "empty = ungated; laser pulses are the readouts"
        )
        layout.addWidget(channels)

        layout.addStretch()
        return page

    def _on_channel_renamed(self, key: str, value: str | None) -> None:
        """A renamed channel is a renamed lane, so the canvas follows.

        Otherwise the editor would keep a lane called `mw` after the rig
        was told the channel is `microwave`, and the sequence would
        validate against a channel no element uses.
        """
        self.sigParamChanged.emit(key, value)
        self._params[key] = value
        self.timeline.set_channels(self.channels())
        # Clearing the gate makes the laser lane the measurement, which is
        # the rule the sequence itself applies — so the mark has to move
        # with it rather than stay on a lane that no longer gates anything.
        self.timeline.set_readout(self.readout_from(self._params))

    def _on_analog_toggled(self, analog: bool) -> None:
        self.sigParamChanged.emit("ANALOG_MW", analog)
        # A digital rig has no amplitude to set: the channel is a gate.
        self.amplitude_spin.setEnabled(analog)
        self.frequency_spin.setEnabled(analog)

    def _update_rabi_hint(self, period: float) -> None:
        self.rabi_hint.setText(
            f"pi = {period / 2 * 1e9:.1f} ns,  pi/2 = {period / 4 * 1e9:.1f} ns"
        )

    # --- Wiring -----------------------------------------------------------

    def _on_timeline_changed(self, data: Any) -> None:
        self.sigParamChanged.emit("TIMELINE", data)
        self._sync_sweep_fields()
        self._describe()

    def _sync_sweep_fields(self) -> None:
        """Dragging a region's edge changes its length, and the sweep's
        first value with it — so the fields follow the canvas rather than
        showing what was typed before the drag."""
        sweep = self.timeline.timeline.sweep
        widgets = (
            self.quantity_combo, self.sweep_name, self.sweep_points,
            self.spacing_combo, self.sweep_step, self.sweep_stop,
            self.sweep_start, self.sweep_stop_hz,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            quantity = sweep.quantity if sweep is not None else None
            self.quantity_combo.setCurrentIndex(
                max(self.quantity_combo.findData(quantity), 0)
            )
            if sweep is not None:
                self.sweep_name.setText(sweep.name)
                self.sweep_points.setValue(sweep.points)
                self.spacing_combo.setCurrentIndex(
                    max(self.spacing_combo.findData(sweep.spacing), 0)
                )
                if sweep.stepped:
                    self.sweep_start.setValue(sweep.start_value)
                    self.sweep_stop_hz.setValue(sweep.stop_value)
                else:
                    self.sweep_step.setValue(sweep.step)
                    self.sweep_stop.setValue(sweep.stop_value)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._update_sweep_fields()

    def _describe(self) -> None:
        """What is drawn, in one line — the count a person checks before
        pressing Save."""
        line = self.timeline.timeline
        sweep = line.sweep
        pulses = sum(len(track.pulses) for track in line.tracks)
        parts = [
            f"{len(line.tracks)} track(s)",
            f"{pulses} pulse(s)",
            f"{pg.siFormat(line.end, suffix='s')} long",
        ]
        if sweep is None:
            parts.append("no sweep")
        elif sweep.stepped:
            parts.append(
                f"{sweep.name}: {sweep.points} points, "
                f"{pg.siFormat(sweep.start_value, suffix='Hz')} to "
                f"{pg.siFormat(sweep.stop_value, suffix='Hz')} (stepped)"
            )
        else:
            parts.append(
                f"{sweep.name}: {sweep.points} points over "
                f"{len(sweep.regions)} region(s)"
            )
        self.status.setText(" · ".join(parts))

    # --- Called by the window ---------------------------------------------

    @staticmethod
    def channels_from(params: dict[str, Any]) -> list[str]:
        """The rig's symbolic channels, in reading order.

        A plain function of the parameters rather than of the Rig tab's
        widgets, because the canvas is built before that tab exists — and
        because these are the one source of truth an offline editor has
        for its lanes.
        """
        names = [
            params.get(key)
            for key in ("LASER_CHANNEL", "MW_CHANNEL", "GATE_CHANNEL")
        ]
        return [str(name) for name in names if name]

    @staticmethod
    def readout_from(params: dict[str, Any]) -> str:
        """Which lane is the measurement.

        The same rule `PulseSequence.readout_channel` applies, and it has
        to be the same one or the canvas would mark a lane the run does
        not count: the gate when there is one, and otherwise the laser,
        because on an ungated rig the laser pulses *are* the readouts.
        """
        return str(params.get("GATE_CHANNEL") or params.get("LASER_CHANNEL") or "")

    def load_timeline(self, timeline: Timeline) -> None:
        """Draw a sequence on the canvas, replacing what is there.

        The moment authoring switches from "start from" to "edit", which
        is why it stores the result immediately: leaving that until the
        next drag would mean a Fill followed by a Save wrote the old
        timeline.
        """
        self.timeline.set_timeline(timeline)
        # Onto the Sweep tab: the canvas is always visible now, and what a
        # person checks straight after filling is what the generator chose
        # to sweep — a frequency, for a pulsed ODMR.
        self.tabs.setCurrentIndex(0)
        self._on_timeline_changed(timeline.to_dict())

    def set_status(self, message: str) -> None:
        self.status.setText(message)

    def set_locked(self, locked: bool) -> None:
        """Disabled while the workflow runs, like every other control
        dock."""
        self.setEnabled(not locked)

    def channels(self) -> list[str]:
        """The symbolic channels this rig declares — what the lanes come
        from, and the one source of truth an offline editor has."""
        names = [
            self._channel_edits[key].text().strip()
            for key in ("LASER_CHANNEL", "MW_CHANNEL", "GATE_CHANNEL")
        ]
        return [name for name in names if name]
