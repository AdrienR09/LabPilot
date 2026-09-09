"""The pulse sequence editor's control dock — a workflow control, not an
instrument block.

This is the GUI of `workflow_templates/pulse_sequence_editor.py`, which
binds no instruments, so the dock never touches a device: every widget
edits one of the workflow's own parameters, and running the workflow
writes `~/.labpilot/sequences/<name>.json`. The timing diagram it produces
is the result view (`PulseSequenceResultView`), the same way a scan's
image is.

Three tabs, matching how a sequence actually gets authored:

- **Generator** — pick one of `core/pulse/library.py`'s four experiments
  and set its parameters. This is Qudi's *predefined-methods* panel, and
  it is a starting point, not the editor. The controls are built from the
  generator's own declared `Parameter` objects, so a unit, a limit and a
  dtype come from the generator rather than from a name-substring guess;
  Qudi reads `inspect.signature` defaults instead and infers units from
  substrings (`'amp' in name` means volts), which is the one part of that
  subsystem worth not copying.
- **Blocks** — Qudi's actual PulseEditor: the dynamic-column element
  table, in `pulse_blocks.py`. Generate a Rabi, press **Load into editor**,
  and hand-edit from there — the generator's output is already in the
  table's own form, so the two paths meet instead of competing.
- **Rig** — the profile the sequence is written against: Rabi period,
  laser length and delay, wait time, the symbolic channel names, and
  whether the microwave channel carries an analog shape or gates an
  external source. Physics and wiring conventions, not driver settings,
  which is exactly why they are editable with nothing plugged in.

Dumb-view widgets, the same convention `axes_control.py` and
`odmr_control.py` follow: this holds no client and makes no network call.
It emits `sigParamChanged(name, value)`, and `workflow_window.py` wires
that to the PUT that stores the parameter.

## Where the channel columns come from

The rig profile's symbolic channel names, never a connected pulser's
channel list. An offline editor has no pulser to ask, and a sequence that
took its channels from one is a sequence tied to one rig's wiring — the
thing the symbolic-channel decision exists to prevent.
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from components.pulse_blocks import PulseBlockEditorWidget
from components.widgets import IconButton
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

__all__ = ["PulseEditorControlWidget"]

#: What the Generator tab offers. Read from `core.pulse.library.GENERATORS`
#: at build time; this is only the fallback when that import is
#: unavailable, and the order the well-known four should appear in.
_KNOWN = ("rabi", "ramsey", "hahn_echo", "t1")


def _time_spinbox(value: float, step: float = 1e-9) -> pg.SpinBox:
    """Seconds with an SI prefix, which is the only way ns-to-ms ranges
    are readable in one control."""
    return pg.SpinBox(
        value=float(value), bounds=(0.0, None), suffix="s", siPrefix=True,
        step=step, dec=True, minStep=1e-12,
    )


class PulseEditorControlWidget(QWidget):
    """Generator + rig profile, as one dock.

    Emits `sigParamChanged(name, value)` per edit and `sigGenerate()` when
    the user asks for the sequence to be built and saved. Nothing here
    writes anything itself.
    """

    # Qt's own signal-naming convention, as in odmr_control.py and
    # axes_control.py — snake_case here would be the odd one out.
    sigParamChanged = pyqtSignal(str, object)  # noqa: N815
    sigGenerate = pyqtSignal()  # noqa: N815
    sigLoadRequested = pyqtSignal()  # noqa: N815

    def __init__(
        self,
        params: dict[str, Any],
        parameters_for: Any = None,
        generators: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        """`parameters_for(name) -> tuple[Parameter, ...]` and `generators`
        are injected rather than imported here so this stays a dumb view
        and the offscreen harness can drive it with stubs."""
        super().__init__(parent)
        self._parameters_for = parameters_for
        self._generators = list(generators or _KNOWN)
        self._params = dict(params)
        self._generator_widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.blocks = PulseBlockEditorWidget(
            self._params.get("BLOCKS") or [], self.channels_from(self._params)
        )
        self.blocks.sigBlocksChanged.connect(self._on_blocks_changed)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_generator_tab(), "Generator")
        self.tabs.addTab(self.blocks, "Blocks")
        self.tabs.addTab(self._build_rig_tab(), "Rig")
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.load_button = IconButton("Load into editor", "document-import")
        self.load_button.setToolTip(
            "Put the last generated sequence into the block table, and "
            "author from there. The generator's output is already in the "
            "table's own form, so nothing is lost."
        )
        self.load_button.clicked.connect(lambda _checked=False: self.sigLoadRequested.emit())
        buttons.addWidget(self.load_button)

        self.generate_button = IconButton("Generate and save", "document-save")
        self.generate_button.clicked.connect(lambda _checked=False: self.sigGenerate.emit())
        buttons.addWidget(self.generate_button)
        layout.addLayout(buttons)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)

    # --- The block editor -------------------------------------------------

    @staticmethod
    def channels_from(params: dict[str, Any]) -> list[str]:
        """The rig's symbolic channels, in reading order.

        A plain function of the parameters rather than of the Rig tab's
        widgets, because the block table is built before that tab exists —
        and because these are the one source of truth an offline editor
        has for its columns.
        """
        names = [
            params.get(key)
            for key in ("LASER_CHANNEL", "MW_CHANNEL", "GATE_CHANNEL")
        ]
        return [str(name) for name in names if name]

    def load_blocks(
        self, blocks: list[dict[str, Any]], channels: list[str] | None = None
    ) -> None:
        """Put a generated (or saved) sequence into the table and show it.

        This is the moment authoring switches from "generate" to "edit",
        which is why it also sets SOURCE — leaving that to the user would
        mean pressing Generate afterwards silently threw the edits away.
        """
        self.blocks.set_blocks(blocks, channels or self.channels())
        self.tabs.setCurrentWidget(self.blocks)

    def _on_blocks_changed(self, blocks: Any) -> None:
        self.sigParamChanged.emit("BLOCKS", blocks)
        self.sigParamChanged.emit("SOURCE", "table")

    # --- The Generator tab ------------------------------------------------

    def _build_generator_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)

        chooser = QGroupBox("Experiment")
        form = QFormLayout(chooser)

        self.generator_combo = QComboBox()
        self.generator_combo.addItems(self._generators)
        current = str(self._params.get("GENERATOR", self._generators[0]))
        if current in self._generators:
            self.generator_combo.setCurrentText(current)
        self.generator_combo.currentTextChanged.connect(self._on_generator_changed)
        form.addRow("Generator:", self.generator_combo)

        self.name_edit = QLineEdit(str(self._params.get("SEQUENCE_NAME", "")))
        self.name_edit.setPlaceholderText("Saved as ~/.labpilot/sequences/<name>.json")
        self.name_edit.editingFinished.connect(
            lambda: self.sigParamChanged.emit("SEQUENCE_NAME", self.name_edit.text())
        )
        form.addRow("Save as:", self.name_edit)

        self.preview_spin = QSpinBox()
        self.preview_spin.setRange(0, 1_000_000)
        self.preview_spin.setValue(int(self._params.get("PREVIEW_POINT", 0)))
        self.preview_spin.setToolTip(
            "Which point of the sweep the timing diagram shows. A whole "
            "50-point Rabi drawn at once is a solid block."
        )
        self.preview_spin.editingFinished.connect(
            lambda: self.sigParamChanged.emit("PREVIEW_POINT", self.preview_spin.value())
        )
        form.addRow("Preview point:", self.preview_spin)
        layout.addWidget(chooser)

        self.generator_group = QGroupBox("Parameters")
        self.generator_form = QFormLayout(self.generator_group)
        layout.addWidget(self.generator_group)
        self._rebuild_generator_form(current)

        layout.addStretch()
        return page

    def _on_generator_changed(self, name: str) -> None:
        self.sigParamChanged.emit("GENERATOR", name)
        self._rebuild_generator_form(name)
        # A new generator takes different parameters, so the old values
        # cannot carry over — sending the fresh defaults keeps the stored
        # GENERATOR_PARAMS in step with the generator it belongs to,
        # rather than leaving a key the next build would refuse.
        self.sigParamChanged.emit("GENERATOR_PARAMS", self.generator_params())

    def _rebuild_generator_form(self, name: str) -> None:
        """Controls built from the generator's declared `Parameter`s.

        Units, limits and dtypes are stated by the generator, so an int
        parameter gets a spin box and a seconds parameter gets an SI
        spin box without anything here inspecting its name.
        """
        while self.generator_form.rowCount():
            self.generator_form.removeRow(0)
        self._generator_widgets.clear()

        declared = self._declared(name)
        if not declared:
            self.generator_form.addRow(QLabel("This generator takes no parameters."))
            return

        stored = dict(self._params.get("GENERATOR_PARAMS") or {})
        for parameter in declared:
            value = stored.get(parameter.name, getattr(parameter, "default", None))
            widget = self._widget_for(parameter, value)
            self._generator_widgets[parameter.name] = widget
            label = parameter.name.replace("_", " ").capitalize()
            self.generator_form.addRow(f"{label}:", widget)
            if getattr(parameter, "description", ""):
                widget.setToolTip(parameter.description)

    def _declared(self, name: str) -> list[Any]:
        if self._parameters_for is None:
            return []
        try:
            return list(self._parameters_for(name))
        except Exception:
            return []

    def _widget_for(self, parameter: Any, value: Any) -> QWidget:
        dtype = str(getattr(parameter, "dtype", "f8"))
        limits = getattr(parameter, "limits", None) or (None, None)

        if dtype.startswith("i"):
            widget = QSpinBox()
            low = int(limits[0]) if limits[0] is not None else 1
            high = int(limits[1]) if limits[1] is not None else 1_000_000
            widget.setRange(low, high)
            widget.setValue(int(value if value is not None else low))
            widget.editingFinished.connect(self._emit_generator_params)
            return widget

        step = 1e-9 if getattr(parameter, "unit", "") == "s" else 0.01
        widget = pg.SpinBox(
            value=float(value or 0.0),
            bounds=(limits[0], limits[1]),
            suffix=getattr(parameter, "unit", "") or None,
            siPrefix=bool(getattr(parameter, "unit", "")),
            step=step, dec=True, minStep=1e-12,
        )
        widget.sigValueChanged.connect(lambda _sb: self._emit_generator_params())
        return widget

    def generator_params(self) -> dict[str, Any]:
        """What the Parameters form currently holds."""
        values: dict[str, Any] = {}
        for name, widget in self._generator_widgets.items():
            values[name] = (
                widget.value() if isinstance(widget, QSpinBox) else float(widget.value())
            )
        return values

    def _emit_generator_params(self) -> None:
        self.sigParamChanged.emit("GENERATOR_PARAMS", self.generator_params())

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
        self.frequency_spin = pg.SpinBox(
            value=float(self._params.get("MW_FREQUENCY", 2.87e9)),
            bounds=(0.0, None), suffix="Hz", siPrefix=True, step=1e6, dec=True,
        )
        self.frequency_spin.sigValueChanged.connect(
            lambda sb: self.sigParamChanged.emit("MW_FREQUENCY", sb.value())
        )
        self.amplitude_spin = pg.SpinBox(
            value=float(self._params.get("MW_AMPLITUDE", 0.25)),
            bounds=(0.0, None), suffix="V", siPrefix=True, step=0.01,
        )
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
            ("Gate:", "GATE_CHANNEL", "gate"),
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
        """A renamed channel is a renamed column, so the table follows.

        Otherwise the block editor would keep offering `mw` after the rig
        was told the channel is called `microwave`, and the sequence would
        validate against a channel no element uses.
        """
        self.sigParamChanged.emit(key, value)
        self.blocks.set_blocks(self.blocks.blocks(), self.channels())

    def _on_analog_toggled(self, analog: bool) -> None:
        self.sigParamChanged.emit("ANALOG_MW", analog)
        # A digital rig has no amplitude to set: the channel is a gate.
        self.amplitude_spin.setEnabled(analog)
        self.frequency_spin.setEnabled(analog)

    def _update_rabi_hint(self, period: float) -> None:
        self.rabi_hint.setText(
            f"pi = {period / 2 * 1e9:.1f} ns,  pi/2 = {period / 4 * 1e9:.1f} ns"
        )

    # --- Called by the window ---------------------------------------------

    def set_status(self, message: str) -> None:
        self.status.setText(message)

    def set_locked(self, locked: bool) -> None:
        """Disabled while the workflow runs, like every other control
        dock. Generating is fast enough that this is barely visible, but
        the rule is the same one every workflow control follows."""
        self.setEnabled(not locked)

    def channels(self) -> list[str]:
        """The symbolic channels this rig declares — what a table editor's
        columns come from, and the one source of truth an offline editor
        has."""
        names = [
            self._channel_edits[key].text().strip()
            for key in ("LASER_CHANNEL", "MW_CHANNEL", "GATE_CHANNEL")
        ]
        return [name for name in names if name]
