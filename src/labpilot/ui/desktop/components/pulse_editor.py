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
- **Rig profile** — the physics a sequence is written against. Rabi
  period, laser length and delay, wait time, the symbolic channel names.
  Not driver settings, which is exactly why they are editable with
  nothing plugged in.

## What is not here any more

A track picker and an Add button (double-click the lane and the moment
you want); a Sweep panel (a sweep is a property of a pulse, so it is
edited from the pulse); a "No sweep" button and an "Add region" button
(marking a second pulse is what adds a second place tau appears). Each of
them was a second way to say something the canvas already says.

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
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labpilot.core.config.paths import sequence_dir
from labpilot.core.pulse.sequence import SequenceError
from labpilot.core.pulse.store import slug
from labpilot.core.pulse.tracks import Timeline


def sequence_folder() -> str:
    """Where saving puts the file. Named in the dock rather than left to
    be discovered, because "where did it go" is the first question after
    pressing Save."""
    return str(sequence_dir())

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
            laser=str(self._params.get("LASER_CHANNEL") or ""),
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
        self.tabs.addTab(self._build_rig_tab(), "Rig profile")
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

    # --- The Rig tab ------------------------------------------------------

    def _build_rig_tab(self) -> QWidget:
        """Your rig's numbers — what **Start from** draws with.

        Not driver settings, and that is the point: every value here is
        physics or naming, so it is editable with nothing plugged in,
        which is what lets a sequence be designed away from the lab. A
        pulser's sample rate, memory granularity and channel numbers are
        deliberately absent — they belong to whichever device eventually
        plays the file, and the editor does not know which that is.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        preamble = QLabel(
            "Your rig's own numbers. <b>Start from</b> draws the standard "
            "experiments with these, and a hand-drawn sequence is written "
            "against them.<br><br>Nothing here is a driver setting — no "
            "sample rate, no channel numbers — so it is all editable with "
            "nothing connected, and the saved file runs on any pulser."
        )
        preamble.setWordWrap(True)
        preamble.setStyleSheet("color: #888;")
        layout.addWidget(preamble)

        timing = QGroupBox("Timing")
        timing_form = QFormLayout(timing)
        self._rig_spins: dict[str, pg.SpinBox] = {}
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
            spin = _time_spinbox(self._params.get(name, default))
            spin.setToolTip(tip)
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
        self.timeline.set_roles(
            str(self._params.get("LASER_CHANNEL") or ""),
            self.readout_from(self._params),
        )

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
