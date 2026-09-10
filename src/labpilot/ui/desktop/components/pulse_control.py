"""The pulsed measurement's control dock — what to play, and how to reduce it.

The GUI of `workflow_templates/pulsed_measurement.py`, and the other half
of `pulse_editor.py`: that one authors a sequence with no hardware, this
one plays a saved one on the bound rig.

Three groups, matching the three decisions a pulsed measurement actually
makes:

- **Sequence** — which saved file to play, and the symbolic-to-physical
  channel map. The map is the one genuinely rig-specific thing in a
  pulsed measurement, which is why it lives with the measurement rather
  than in the sequence file.
- **Acquisition** — sweeps and checkpoints, the signal-to-noise knob and
  how often the curve is recorded on the way; bin width and record
  length.
- **Analysis** — extraction, analysis and fit. The two method combos are
  filled from the registries themselves, so a method added to
  `core/pulse/extract.py` appears here with no change to this file.

A dumb view, the same convention `axes_control.py` and
`pulse_editor.py` follow: no client, no network call. It emits
`sigParamChanged(name, value)` and `workflow_window.py` wires that to the
PUT that stores the parameter.

## Why the sequence is a combo and not a text field

A typo'd sequence name fails at `load_sequence` after the run has been
started and the pulser bound — so the dock lists what is actually in
`~/.labpilot/sequences/`, marks the ones that will not play, and says why.
The list comes in from `workflow_window.py` rather than being read here,
so the offscreen harness can drive this with stubs.
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from components.widgets import IconButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

__all__ = ["PulseMeasurementControlWidget"]

#: Fit models the template understands. Named rather than inferred: a
#: sequence's name says nothing about the physics it measures, and a
#: hand-edited one may measure something else entirely.
_FITS = (("none", "No fit"), ("rabi", "Rabi (decaying cosine)"), ("decay", "Exponential decay"))


def _time_spinbox(value: float, step: float = 1e-9) -> pg.SpinBox:
    return pg.SpinBox(
        value=float(value), bounds=(0.0, None), suffix="s", siPrefix=True,
        step=step, dec=True, minStep=1e-12,
    )


class PulseMeasurementControlWidget(QWidget):
    """Choose a sequence, say how long to accumulate, say how to reduce it."""

    sigParamChanged = pyqtSignal(str, object)
    sigRun = pyqtSignal()
    sigRefresh = pyqtSignal()

    def __init__(
        self,
        params: dict[str, Any],
        sequences: list[dict[str, Any]] | None = None,
        extractors: list[str] | None = None,
        analyses: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._params = dict(params or {})
        self._sequences = list(sequences or [])
        self._extractors = list(extractors or ["conv_deriv", "threshold"])
        self._analyses = list(analyses or ["mean", "mean_norm", "mean_reference"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._sequence_group())
        layout.addWidget(self._acquisition_group())
        layout.addWidget(self._analysis_group())

        run = IconButton("Run measurement", "media-playback-start")
        run.clicked.connect(self.sigRun.emit)
        layout.addWidget(run)
        layout.addStretch(1)

    # --- Sequence ---------------------------------------------------------

    def _sequence_group(self) -> QGroupBox:
        box = QGroupBox("Sequence")
        form = QFormLayout(box)

        self.sequence = QComboBox()
        self._fill_sequences()
        self.sequence.currentTextChanged.connect(
            lambda text: self._changed("SEQUENCE", self._name_of(text))
        )

        row = QHBoxLayout()
        row.addWidget(self.sequence, 1)
        refresh = IconButton("", "view-refresh")
        refresh.setToolTip("Re-read ~/.labpilot/sequences/")
        refresh.clicked.connect(self.sigRefresh.emit)
        row.addWidget(refresh)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Play", holder)

        self.summary = QLabel(self._summary())
        self.summary.setWordWrap(True)
        form.addRow("", self.summary)

        # Free text rather than one field per channel: which symbolic
        # channels exist is the sequence's business and changes with it,
        # so a fixed set of rows would be wrong for every sequence but one.
        self.channels = QLineEdit(self._channels_text())
        self.channels.setPlaceholderText("laser=d_ch1, mw=a_ch1, gate=d_ch2")
        self.channels.setToolTip(
            "Symbolic channel = this pulser's physical channel, comma "
            "separated. Empty means the sequence's own names are already "
            "the physical ones."
        )
        self.channels.editingFinished.connect(self._channels_edited)
        form.addRow("Channels", self.channels)
        return box

    def _fill_sequences(self) -> None:
        self.sequence.blockSignals(True)
        self.sequence.clear()
        current = str(self._params.get("SEQUENCE", ""))
        for entry in self._sequences:
            label = entry["name"] if entry.get("valid", True) else f"{entry['name']} (unplayable)"
            self.sequence.addItem(label, entry["name"])
            if entry.get("problem"):
                self.sequence.setItemData(
                    self.sequence.count() - 1,
                    entry["problem"],
                    Qt.ItemDataRole.ToolTipRole,
                )
        if not self._sequences and current:
            # Nothing on disk yet, or the list could not be read. Showing
            # the stored name beats showing an empty combo that silently
            # rewrites the parameter on first paint.
            self.sequence.addItem(current, current)
        index = self.sequence.findData(current)
        if index >= 0:
            self.sequence.setCurrentIndex(index)
        self.sequence.blockSignals(False)

    def _name_of(self, label: str) -> str:
        index = self.sequence.findText(label)
        return str(self.sequence.itemData(index) or label) if index >= 0 else label

    def _summary(self) -> str:
        name = str(self._params.get("SEQUENCE", ""))
        entry = next((e for e in self._sequences if e.get("name") == name), None)
        if entry is None:
            return "Not in the library yet — it is written on the first run."
        if not entry.get("valid", True):
            return f"Will not play: {entry.get('problem', 'unknown problem')}"
        return (
            f"{entry.get('points', '?')} points, {entry.get('readouts', '?')} readouts, "
            f"{float(entry.get('duration', 0.0)) * 1e6:.1f} us per sweep"
        )

    def _channels_text(self) -> str:
        mapping = self._params.get("CHANNELS") or {}
        return ", ".join(f"{k}={v}" for k, v in mapping.items())

    def _channels_edited(self) -> None:
        mapping: dict[str, str] = {}
        for pair in self.channels.text().split(","):
            symbolic, _, physical = pair.partition("=")
            if symbolic.strip() and physical.strip():
                mapping[symbolic.strip()] = physical.strip()
        self._changed("CHANNELS", mapping)

    # --- Acquisition ------------------------------------------------------

    def _acquisition_group(self) -> QGroupBox:
        box = QGroupBox("Acquisition")
        form = QFormLayout(box)

        self.sweeps = QSpinBox()
        self.sweeps.setRange(1, 100_000_000)
        self.sweeps.setValue(int(self._params.get("SWEEPS", 2000)))
        self.sweeps.setToolTip(
            "Complete passes over the sequence. Counts — and so the error "
            "bars — improve as the square root of this."
        )
        self.sweeps.valueChanged.connect(lambda v: self._changed("SWEEPS", int(v)))
        form.addRow("Sweeps", self.sweeps)

        self.checkpoints = QSpinBox()
        self.checkpoints.setRange(1, 1000)
        self.checkpoints.setValue(int(self._params.get("CHECKPOINTS", 20)))
        self.checkpoints.setToolTip(
            "How many times the curve is recorded on the way — the rows of "
            "the result, and the run's progress steps."
        )
        self.checkpoints.valueChanged.connect(
            lambda v: self._changed("CHECKPOINTS", int(v))
        )
        form.addRow("Checkpoints", self.checkpoints)

        self.bin_width = _time_spinbox(self._params.get("BIN_WIDTH", 1e-9))
        self.bin_width.sigValueChanged.connect(
            lambda box: self._changed("BIN_WIDTH", float(box.value()))
        )
        form.addRow("Bin width", self.bin_width)

        self.record_length = _time_spinbox(self._params.get("RECORD_LENGTH", 0.0))
        self.record_length.setToolTip(
            "0 derives it from the sequence: half again its readout window, "
            "so the record holds dark bins either side of the laser pulse."
        )
        self.record_length.sigValueChanged.connect(
            lambda box: self._changed("RECORD_LENGTH", float(box.value()))
        )
        form.addRow("Record length", self.record_length)
        return box

    # --- Analysis ---------------------------------------------------------

    def _analysis_group(self) -> QGroupBox:
        box = QGroupBox("Analysis")
        form = QFormLayout(box)

        self.extract = self._combo(
            self._extractors, str(self._params.get("EXTRACT", "conv_deriv")), "EXTRACT"
        )
        self.extract.setToolTip("How the laser pulse is found in the raw record.")
        form.addRow("Extract", self.extract)

        # "auto" first: it picks from the sequence — signal/reference when
        # it alternates, per-readout normalisation when it does not — and
        # a fixed default would be wrong for half the experiments.
        self.analyse = self._combo(
            ["auto", *self._analyses], str(self._params.get("ANALYSE", "auto")), "ANALYSE"
        )
        form.addRow("Analyse", self.analyse)

        self.fit = QComboBox()
        for value, label in _FITS:
            self.fit.addItem(label, value)
        index = self.fit.findData(str(self._params.get("FIT", "none")))
        self.fit.setCurrentIndex(max(index, 0))
        self.fit.currentIndexChanged.connect(
            lambda _: self._changed("FIT", self.fit.currentData())
        )
        form.addRow("Fit", self.fit)
        return box

    def _combo(self, choices: list[str], current: str, param: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(choices)
        if current in choices:
            combo.setCurrentText(current)
        combo.currentTextChanged.connect(lambda text: self._changed(param, text))
        return combo

    # --- Wiring -----------------------------------------------------------

    def _changed(self, name: str, value: Any) -> None:
        self._params[name] = value
        if name == "SEQUENCE":
            self.summary.setText(self._summary())
        self.sigParamChanged.emit(name, value)

    def set_sequences(self, sequences: list[dict[str, Any]]) -> None:
        """Re-fill the library list, keeping the current selection."""
        self._sequences = list(sequences or [])
        self._fill_sequences()
        self.summary.setText(self._summary())
