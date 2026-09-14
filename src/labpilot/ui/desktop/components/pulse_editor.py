"""The pulse sequence editor's dock — a workflow control, not an instrument block.

This is the GUI of `workflow_templates/pulse_sequence_editor.py`, which
binds no instruments, so the dock never touches a device: every widget
edits one of the workflow's own parameters, and running the workflow
writes `~/.labpilot/sequences/<name>.json`.

The editor **is** the timeline (`pulse_timeline.py`): one lane per
instrument, pulses drawn on the lanes. That template declares no
`RESULT_UI`, so this dock is the whole window and the canvas takes all
the height — a second plot of the same picture used to sit beside it, and
an inspector used to sit under it, and between them they left the canvas
a third of the window.

So the layout is one canvas and one column, and the column holds three
things:

- **Sequence** — the file's name, the folder it lands in, which
  experiment **Start from** draws, and whether consecutive readouts
  alternate signal and reference.
- **Pulse** — everything about whatever is selected: name, time, shape,
  whether it drives its channel, and whether the measurement sweeps it.
- **Channels** — the lanes this rig has and what each one is for. Names,
  not wiring, which is exactly why they are editable with nothing plugged
  in.

## What is not here any more

A track picker and an Add button (double-click the lane and the moment
you want); a Sweep panel (a sweep is a property of a pulse, so it is
edited from the pulse); a "No sweep" button and an "Add region" button
(marking a second pulse is what adds a second place tau appears); a Fit
button (pyqtgraph's own auto-range button already does that, in the place
every pyqtgraph user looks for it). Each of them was a second way to say
something the canvas already says.

The rig's physics — Rabi period, laser length and delay, wait time, the
microwave defaults — used to sit in a permanent "Rig profile" tab beside
those. It is in the **Start from** dialog now, because that is the only
thing that reads it: once a sequence is drawn, what gets saved is the
drawing, so those fields were live for one click and inert thereafter.

## Two kinds of sweep, both on the pulse

**Its length**: the pulse grows point by point and everything after it
shifts, and the pulser plays the whole sweep in one pass. Offered on
every pulse, because any drawn interval has a length.

**The microwave frequency**: the drawing never changes and the bound
source steps between passes. Offered only on a drive — a laser line and a
counter gate are on/off, with no carrier to move.

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

import contextlib
from typing import TYPE_CHECKING, Any

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labpilot.core.config.paths import sequence_dir
from labpilot.core.pulse.library import (
    GATE,
    KINDS,
    LASER,
    MW,
    OTHER,
    generator_defaults,
    generator_parameters,
)
from labpilot.core.pulse.sequence import SequenceError
from labpilot.core.pulse.store import slug
from labpilot.core.pulse.tracks import Timeline
from labpilot.ui.desktop.components.pulse_timeline import PulseTimelineWidget
from labpilot.ui.desktop.components.widgets import IconButton


def sequence_folder() -> str:
    """Where saving puts the file. Named in the dock rather than left to
    be discovered, because "where did it go" is the first question after
    pressing Save."""
    return str(sequence_dir())

if TYPE_CHECKING:
    from labpilot.core.device.parameter import Parameter

__all__ = ["FillDialog", "PulseEditorControlWidget"]

#: What "Start from" offers. Read from `core.pulse.library.GENERATORS` at
#: build time; this is only the fallback when that is unavailable, and the
#: order the well-known experiments should appear in.
_KNOWN = ("rabi", "ramsey", "hahn_echo", "t1", "pulsed_odmr")

#: What each channel kind is called in the table, spelled out rather than
#: left as the bare token — "gate" alone does not say that it is the lane
#: whose edges the run counts.
_KIND_LABELS = {
    LASER: "Laser — polarise and read out",
    MW: "Microwave — drive (can sweep frequency)",
    GATE: "Gate — opens the counter",
    OTHER: "Other — trigger, shutter, …",
}

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


class FillDialog(QDialog):
    """What **Start from** draws with — and nothing else.

    Every field here is an argument to one call: `build(generator,
    profile, **params)`. They used to live in a permanent "Rig profile"
    tab, which is where the complaint about that tab comes from — after
    the first Fill they did nothing at all, because what gets saved is
    the drawing, not the numbers it was drawn from. A control that is
    live for one click and dead thereafter reads as clutter because it
    *is* clutter.

    Putting them behind the button that consumes them also closes a real
    gap. The top half is built from the chosen generator's own declared
    `Parameter`s — `tau_start`, `tau_step`, `points` for a Rabi,
    `start`/`stop`/`points` for a pulsed ODMR — which the editor could
    not set at all before, so Fill always drew the default fifty points
    and any other range had to be dragged in by hand. `library.py`
    declares those parameters explicitly, with units and limits, for
    exactly this; only the console was reading them.
    """

    def __init__(
        self, generator: str, params: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Start from {generator}")
        self._generator = generator
        self._fields: dict[str, pg.SpinBox] = {}

        layout = QVBoxLayout(self)
        blurb = QLabel(
            f"Draws a <b>{generator}</b> on the timeline, replacing what is "
            f"there. A starting point to edit: once drawn, the timeline is "
            f"what gets saved, so a hand-moved gate stays moved."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet("color: #888;")
        layout.addWidget(blurb)

        experiment = QGroupBox("This experiment")
        form = QFormLayout(experiment)
        defaults = generator_defaults(generator)
        for parameter in generator_parameters(generator):
            box = self._spin_for(parameter, defaults.get(parameter.name, 0.0))
            self._fields[parameter.name] = box
            if parameter.description:
                box.setToolTip(parameter.description)
            form.addRow(f"{parameter.name.replace('_', ' ')}:", box)
        layout.addWidget(experiment)

        timing = QGroupBox("Rig timing")
        timing.setToolTip(
            "Physics, not driver settings — so it is all editable with "
            "nothing connected, which is what lets a sequence be designed "
            "away from the lab."
        )
        timing_form = QFormLayout(timing)
        self._rig: dict[str, pg.SpinBox] = {}
        for label, name, default, tip in (
            ("Rabi period:", "RABI_PERIOD", 200e-9,
             "One full Rabi oscillation. A pi pulse is half of it and a "
             "pi/2 pulse a quarter, so every experiment's drive lengths "
             "come from this one number — calibrate it with a Rabi."),
            ("Laser length:", "LASER_LENGTH", 3e-6,
             "How long the readout laser stays on. Long enough to collect "
             "photons, short enough not to repolarise before you have."),
            ("Laser delay:", "LASER_DELAY", 700e-9,
             "Between the readout window closing and the laser actually "
             "being off: cable length, AOM rise time, photon travel."),
            ("Wait time:", "WAIT_TIME", 1e-6,
             "Repolarisation before the next repetition, so each point "
             "starts from the same spin state."),
        ):
            spin = _time_spinbox(params.get(name, default))
            spin.setToolTip(tip)
            timing_form.addRow(label, spin)
            self._rig[name] = spin

        self.rabi_hint = QLabel("")
        self.rabi_hint.setStyleSheet("color: #888;")
        timing_form.addRow("", self.rabi_hint)
        self._rig["RABI_PERIOD"].sigValueChanged.connect(
            lambda sb: self._update_rabi_hint(sb.value())
        )
        self._update_rabi_hint(params.get("RABI_PERIOD", 200e-9))
        layout.addWidget(timing)

        drive = QGroupBox("Microwave")
        drive_form = QFormLayout(drive)
        self.frequency_spin = _sized(pg.SpinBox(
            value=float(params.get("MW_FREQUENCY", 2.87e9)),
            bounds=(0.0, None), suffix="Hz", siPrefix=True, step=1e6, dec=True,
        ))
        self.amplitude_spin = _sized(pg.SpinBox(
            value=float(params.get("MW_AMPLITUDE", 0.25)),
            bounds=(0.0, None), suffix="V", siPrefix=True, step=0.01,
        ))
        self.analog_check = QCheckBox("Analog drive (an AWG synthesises the pulse)")
        self.analog_check.setChecked(bool(params.get("ANALOG_MW", True)))
        self.analog_check.setToolTip(
            "Unchecked describes a digital-only rig — a PulseBlaster gating "
            "an external microwave source. The sequences are identical "
            "either way; only this flag changes."
        )
        self.analog_check.toggled.connect(self._on_analog_toggled)
        drive_form.addRow("Frequency:", self.frequency_spin)
        drive_form.addRow("Amplitude:", self.amplitude_spin)
        drive_form.addRow(self.analog_check)
        self._on_analog_toggled(self.analog_check.isChecked())
        layout.addWidget(drive)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Draw")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _spin_for(parameter: Parameter, default: Any) -> pg.SpinBox:
        """One control, from what the generator declared about it.

        Units and limits are stated on the `Parameter`, so nothing here
        guesses them from the name — which is the trap Qudi's own
        generator GUI falls into (`'amp' in name` gives it volts). The
        starting value comes from the generator's own signature, which is
        where it already lives.
        """
        low, high = parameter.limits or (None, None)
        if parameter.dtype == "i8":
            return _sized(pg.SpinBox(
                value=int(default or 1), int=True, step=1, dec=False,
                bounds=(low, high),
            ))
        return _sized(pg.SpinBox(
            value=float(default or 0.0), bounds=(low, high),
            suffix=parameter.unit or None, siPrefix=bool(parameter.unit),
            step=1e-9 if parameter.unit == "s" else 1e6, dec=True, minStep=1e-12,
        ))

    def _on_analog_toggled(self, analog: bool) -> None:
        # A digital rig has no amplitude to set: the channel is a gate.
        self.amplitude_spin.setEnabled(analog)
        self.frequency_spin.setEnabled(analog)

    def _update_rabi_hint(self, period: float) -> None:
        self.rabi_hint.setText(
            f"pi = {period / 2 * 1e9:.1f} ns,  pi/2 = {period / 4 * 1e9:.1f} ns"
        )

    def rig_values(self) -> dict[str, Any]:
        """The rig profile fields, as workflow parameters."""
        values: dict[str, Any] = {
            name: float(box.value()) for name, box in self._rig.items()
        }
        values["MW_FREQUENCY"] = float(self.frequency_spin.value())
        values["MW_AMPLITUDE"] = float(self.amplitude_spin.value())
        values["ANALOG_MW"] = bool(self.analog_check.isChecked())
        return values

    def generator_values(self) -> dict[str, Any]:
        """The chosen experiment's own arguments."""
        return {
            name: (int(box.value()) if box.opts.get("int") else float(box.value()))
            for name, box in self._fields.items()
        }


class PulseEditorControlWidget(QWidget):
    """The timeline canvas, plus the sequence, sweep and rig settings."""

    # Qt's own signal-naming convention, as in odmr_control.py and
    # axes_control.py — snake_case here would be the odd one out.
    sigParamChanged = pyqtSignal(str, object)
    sigGenerate = pyqtSignal()
    sigFillRequested = pyqtSignal(str, dict)
    """The generator to draw, and the arguments it was given."""

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
            kinds=self.kinds_from(self._params),
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
        # The pulse first: it is what you edit, and the rig profile is
        # what you set once.
        self.tabs.addTab(self.timeline.inspector, "Pulse")
        self.tabs.addTab(self._build_channels_tab(), "Channels")
        column.addWidget(self.tabs, 1)

        self.generate_button = IconButton("Save sequence", "document-save")
        self.generate_button.setToolTip(
            f"Validate what is drawn and write it to {sequence_folder()}"
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
        self.name_edit.setPlaceholderText("rabi")
        self.name_edit.editingFinished.connect(self._on_name_changed)
        form.addRow("Name:", self.name_edit)

        # The folder, spelled out. Saving writes one abstract JSON file
        # named after the sequence, and where it lands is the first thing
        # you need in order to find it again, copy it or share it.
        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #888;")
        self.path_label.setToolTip(
            "Device-independent: symbolic channels, seconds and volts, no "
            "sample rate and no channel numbers. Whichever pulser the "
            "measurement binds compiles it — that is what lets one file "
            "run on any rig."
        )
        form.addRow("File:", self.path_label)
        self._update_path()

        start = QWidget()
        row = QHBoxLayout(start)
        row.setContentsMargins(0, 0, 0, 0)
        self.generator_combo = QComboBox()
        self.generator_combo.addItems(self._generators)
        current = str(self._params.get("START_FROM", self._generators[0]))
        if current in self._generators:
            self.generator_combo.setCurrentText(current)
        row.addWidget(self.generator_combo, 1)

        self.fill_button = IconButton("Fill…", "document-import")
        self.fill_button.setToolTip(
            "Draw this experiment on the timeline, replacing what is there. "
            "Asks for its range and your rig's timing first — a starting "
            "point to edit, and once drawn the timeline is what gets saved."
        )
        self.fill_button.clicked.connect(lambda _checked=False: self._ask_and_fill())
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

    # --- Where the file goes ----------------------------------------------

    def _on_name_changed(self) -> None:
        self.sigParamChanged.emit("SEQUENCE_NAME", self.name_edit.text())
        self._params["SEQUENCE_NAME"] = self.name_edit.text()
        self._update_path()

    def _update_path(self) -> None:
        name = self.name_edit.text().strip() or "rabi"
        try:
            filename = f"{slug(name)}.json"
        except Exception:
            filename = "<not a usable filename>"
        self.path_label.setText(f"{sequence_folder()}/{filename}")

    # --- The Channels tab -------------------------------------------------

    def _ask_and_fill(self) -> None:
        """Collect what **Start from** needs, then ask for the drawing.

        The values are stored as workflow parameters on the way through,
        so the numbers a sequence was drawn with are recorded in the file
        that drew it rather than living only in a dialog that has closed.
        """
        generator = self.generator_combo.currentText()
        dialog = FillDialog(generator, self._params, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for name, value in dialog.rig_values().items():
            self._params[name] = value
            self.sigParamChanged.emit(name, value)
        self.sigFillRequested.emit(generator, dialog.generator_values())

    # --- The Channels tab -------------------------------------------------

    def _build_channels_tab(self) -> QWidget:
        """The lanes this rig has, and what each one is for.

        The one part of the old "Rig profile" tab that is live the whole
        time you are editing: it is where the lanes come from, so adding a
        row adds a lane to draw on. Everything else that tab held —
        Rabi period, laser length, microwave defaults — fed exactly one
        call, `build()` behind the Fill button, and did nothing at all
        once a sequence was drawn. It now lives in that button's dialog.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        preamble = QLabel(
            "Names, not wiring. Which physical channel each one becomes "
            "belongs to the measurement workflow's bindings, so the saved "
            "file runs on any rig.<br><br>A rig may have several of a kind "
            "— two lasers, two microwave lines, two counters. The "
            "<i>kind</i> is what the editor reasons about, never the name, "
            "so a drive called <tt>mw2</tt> is a drive because it says so. "
            "Declare no gate and the rig is ungated: the laser pulses are "
            "then the readouts."
        )
        preamble.setWordWrap(True)
        preamble.setStyleSheet("color: #888;")
        layout.addWidget(preamble)

        self.channel_table = QTableWidget(0, 2)
        self.channel_table.setHorizontalHeaderLabels(["Name", "Used for"])
        self.channel_table.horizontalHeader().setStretchLastSection(True)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.channel_table, 1)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        add = IconButton("Add channel", "list-add")
        add.clicked.connect(lambda _checked=False: self._add_channel_row())
        row.addWidget(add)
        drop = IconButton("Remove", "list-remove")
        drop.clicked.connect(lambda _checked=False: self._remove_channel_row())
        row.addWidget(drop)
        row.addStretch(1)
        layout.addWidget(buttons)
        self._fill_channel_table()
        return page

    # --- The channel table ------------------------------------------------

    def _fill_channel_table(self) -> None:
        self.channel_table.blockSignals(True)
        # Nothing is connected on the first fill, and `disconnect` raises
        # rather than shrugging when that is so.
        with contextlib.suppress(TypeError):
            self.channel_table.itemChanged.disconnect()
        self.channel_table.setRowCount(0)
        for entry in self.declared_channels(self._params):
            self._add_channel_row(entry["name"], entry["kind"], report=False)
        self.channel_table.blockSignals(False)
        self.channel_table.itemChanged.connect(lambda _item: self._channels_edited())

    def _add_channel_row(
        self, name: str = "", kind: str = OTHER, report: bool = True
    ) -> None:
        row = self.channel_table.rowCount()
        self.channel_table.insertRow(row)
        self.channel_table.setItem(row, 0, QTableWidgetItem(name))

        combo = QComboBox()
        for choice in KINDS:
            combo.addItem(_KIND_LABELS[choice], choice)
        combo.setCurrentIndex(max(combo.findData(kind), 0))
        combo.currentIndexChanged.connect(lambda _index: self._channels_edited())
        self.channel_table.setCellWidget(row, 1, combo)
        if report:
            self._channels_edited()

    def _remove_channel_row(self) -> None:
        row = self.channel_table.currentRow()
        if row >= 0:
            self.channel_table.removeRow(row)
            self._channels_edited()

    def _channels_edited(self) -> None:
        """Push the table back as the CHANNELS parameter, and relane.

        A renamed or added channel is a renamed or added lane, so the
        canvas follows immediately — otherwise the editor would keep a
        lane called `mw` after the rig was told the channel is
        `microwave`, and the sequence would validate against a channel no
        element uses.
        """
        declared = self.channels()
        self._params["CHANNELS"] = declared
        self.sigParamChanged.emit("CHANNELS", declared)
        self.timeline.set_channels([entry["name"] for entry in declared])
        self.timeline.set_kinds({e["name"]: e["kind"] for e in declared})
        self._describe()

    # --- Wiring -----------------------------------------------------------

    def _on_timeline_changed(self, data: Any) -> None:
        self.sigParamChanged.emit("TIMELINE", data)
        self._describe()

    def _describe(self) -> None:
        """What is drawn, in one line — the count a person checks before
        pressing Save."""
        line = self.timeline.timeline
        pulses = sum(len(track.pulses) for track in line.tracks)
        readouts = sum(
            len(track.driving) for track in line.tracks
            if track.channel == self.readout_from(self._params)
        )
        parts = [
            f"{len(line.tracks)} track(s)",
            f"{pulses} pulse(s)",
            f"{readouts} readout(s)",
            f"{pg.siFormat(line.end, suffix='s')} long",
        ]
        try:
            values = line.sweep_values()
        except SequenceError as error:
            parts.append(str(error))
            self.status.setText(" · ".join(parts))
            return

        if values is None:
            parts.append("no sweep — mark a pulse to sweep it")
        else:
            marked = len(line.swept)
            unit = values.unit
            parts.append(
                f"{values.name}: {len(values)} points, "
                f"{pg.siFormat(values.values[0], suffix=unit)} to "
                f"{pg.siFormat(values.values[-1], suffix=unit)} "
                f"over {marked} pulse(s)"
            )
        self.status.setText(" · ".join(parts))

    # --- Called by the window ---------------------------------------------

    @staticmethod
    def declared_channels(params: dict[str, Any]) -> list[dict[str, str]]:
        """The rig's channels, in lane order, each with its kind.

        A plain function of the parameters rather than of the Channels tab's
        widgets, because the canvas is built before that tab exists — and
        because these are the one source of truth an offline editor has
        for its lanes. A malformed entry is skipped rather than raised on:
        a hand-edited parameter must not cost the whole window.
        """
        declared = params.get("CHANNELS")
        if not isinstance(declared, list):
            return []
        entries: list[dict[str, str]] = []
        for entry in declared:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            kind = str(entry.get("kind", OTHER))
            entries.append({
                "name": str(entry["name"]),
                "kind": kind if kind in KINDS else OTHER,
            })
        return entries

    @classmethod
    def channels_from(cls, params: dict[str, Any]) -> list[str]:
        """Just the lane names."""
        return [entry["name"] for entry in cls.declared_channels(params)]

    @classmethod
    def kinds_from(cls, params: dict[str, Any]) -> dict[str, str]:
        """Lane name -> what it is for. What decides which lane is the
        measurement and which may sweep a carrier."""
        return {e["name"]: e["kind"] for e in cls.declared_channels(params)}

    @classmethod
    def readout_from(cls, params: dict[str, Any]) -> str:
        """Which lane is the measurement.

        The same rule `PulseSequence.readout_channel` applies, and it has
        to be the same one or the canvas would mark a lane the run does
        not count: the first gate when there is one, and otherwise the
        first laser, because on an ungated rig the laser pulses *are* the
        readouts.
        """
        entries = cls.declared_channels(params)
        for kind in (GATE, LASER):
            first = next((e["name"] for e in entries if e["kind"] == kind), "")
            if first:
                return first
        return ""

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

    def channels(self) -> list[dict[str, str]]:
        """What the channel table currently says — name and kind per lane.

        Rows with a blank name are dropped rather than refused: a
        half-typed row is an ordinary state to be in while adding one.
        """
        entries: list[dict[str, str]] = []
        for row in range(self.channel_table.rowCount()):
            item = self.channel_table.item(row, 0)
            combo = self.channel_table.cellWidget(row, 1)
            name = (item.text().strip() if item else "")
            if name:
                entries.append({
                    "name": name,
                    "kind": (combo.currentData() if combo else OTHER) or OTHER,
                })
        return entries
