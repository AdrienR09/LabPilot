"""The block editor — Qudi's dynamic-column pulse table.

This is the editing surface, as distinct from the generator form next to
it. One row per `PulseElement`; one column per channel, plus Length and
Increment. Rows are added, removed, reordered and typed into, and the
timing diagram redraws from whatever the table currently holds.

**The columns are not fixed**, which is the idea worth taking from Qudi's
`pulsed_maingui.py` whole. A digital channel is a checkbox. An analog
channel contributes a shape combobox *plus one column per that shape's
parameters*, so choosing `Sin` on the microwave channel grows Amplitude,
Frequency and Phase columns, and choosing `Chirp` replaces them with the
chirp's own. The column rule itself lives in `core/pulse/table.py`, Qt-free
and tested headless; this file is the widget over it.

One deliberate difference from Qudi: the columns come from the **rig
profile's symbolic channels**, never from a connected pulser's
`activation_config`. An offline editor has no pulser to ask, and taking
columns from one would tie a saved sequence to a single rig's wiring.

## Blocks

A sequence is a list of blocks and most experiments are one block played
many times — but T1 is twenty blocks, because a log-spaced sweep is the
one thing an increment cannot express. So there is a block selector with
its own repetition count, and the table edits the selected block. Qudi
splits these into two panes (Block Editor and Block Organizer); one
selector is the same information with less furniture.

Dumb view, the convention `axes_control.py` and `odmr_control.py` follow:
it holds no client, makes no network call, and emits `sigBlocksChanged`
with the whole edited table for `workflow_window.py` to store.
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from components.widgets import IconButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from labpilot.core.pulse.shapes import SHAPES
from labpilot.core.pulse.table import (
    ANALOG,
    DIGITAL,
    INCREMENT,
    LENGTH,
    NAME,
    SHAPE,
    blank_element,
    cell,
    columns,
    set_cell,
)

__all__ = ["PulseBlockEditorWidget"]

#: What an analog channel's shape combobox offers. "off" is not a shape —
#: it is how a channel that carries no analog signal in this element is
#: spelled, which the model represents as a plain False.
_OFF = "off"


class PulseBlockEditorWidget(QWidget):
    """A table of pulse elements, with columns built from what is in them."""

    # Qt's own signal-naming convention, as in odmr_control.py — snake_case
    # here would be the odd one out.
    sigBlocksChanged = pyqtSignal(object)  # noqa: N815
    sigPreviewRequested = pyqtSignal()  # noqa: N815

    def __init__(
        self,
        blocks: list[dict[str, Any]] | None = None,
        channels: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._blocks: list[dict[str, Any]] = [dict(b) for b in (blocks or [])]
        self._channels = list(channels or ["laser", "mw", "gate"])
        self._columns: tuple = ()
        self._current = 0
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(self._build_block_row())

        self.table = QTableWidget(0, 0)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        layout.addLayout(self._build_element_row())

        self.summary = QLabel("")
        self.summary.setStyleSheet("color: #888;")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.set_blocks(self._blocks, self._channels)

    # --- Chrome ------------------------------------------------------------

    def _build_block_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Block:"))

        self.block_combo = QComboBox()
        self.block_combo.setMinimumWidth(140)
        self.block_combo.currentIndexChanged.connect(self._on_block_selected)
        row.addWidget(self.block_combo, 1)

        row.addWidget(QLabel("Repetitions:"))
        self.repetitions_spin = QSpinBox()
        self.repetitions_spin.setRange(1, 1_000_000)
        self.repetitions_spin.setToolTip(
            "How many times this block plays — exactly this many. Qudi's "
            "means extra plays, so 3 runs four times."
        )
        self.repetitions_spin.editingFinished.connect(self._on_repetitions_changed)
        row.addWidget(self.repetitions_spin)

        self.add_block_button = IconButton("+ Block", "list-add")
        self.add_block_button.clicked.connect(lambda _c=False: self.add_block())
        row.addWidget(self.add_block_button)

        self.remove_block_button = IconButton("- Block", "list-remove")
        self.remove_block_button.clicked.connect(lambda _c=False: self.remove_block())
        row.addWidget(self.remove_block_button)
        return row

    def _build_element_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for label, icon, slot in (
            ("Add", "list-add", self.add_element),
            ("Duplicate", "edit-copy", self.duplicate_element),
            ("Remove", "list-remove", self.remove_element),
            ("Up", "go-up", lambda: self.move_element(-1)),
            ("Down", "go-down", lambda: self.move_element(+1)),
        ):
            button = IconButton(label, icon)
            button.clicked.connect(lambda _checked=False, fn=slot: fn())
            row.addWidget(button)
        row.addStretch()
        return row

    # --- State -------------------------------------------------------------

    def set_blocks(
        self, blocks: list[dict[str, Any]] | None, channels: list[str] | None = None
    ) -> None:
        """Load a table — from a generated sequence, or a saved file.

        This is the bridge between the two authoring paths: "generate a
        Rabi, then hand-edit it" is one gesture because the generator's
        output is already in the table's own form.
        """
        if channels is not None:
            self._channels = [name for name in channels if name]
        self._blocks = [
            {
                "name": block.get("name") or f"block_{index}",
                "repetitions": int(block.get("repetitions", 1) or 1),
                "elements": [dict(e) for e in (block.get("elements") or ())],
            }
            for index, block in enumerate(blocks or [])
        ]
        if not self._blocks:
            self._blocks = [
                {"name": "block_0", "repetitions": 1,
                 "elements": [blank_element(self._channels)]}
            ]
        self._current = min(self._current, len(self._blocks) - 1)

        self._loading = True
        self.block_combo.clear()
        self.block_combo.addItems([block["name"] for block in self._blocks])
        self.block_combo.setCurrentIndex(self._current)
        self._loading = False
        self._rebuild()

    def blocks(self) -> list[dict[str, Any]]:
        """The edited table, in the form a sequence file stores."""
        return [
            {
                "name": block["name"],
                "repetitions": int(block["repetitions"]),
                "elements": [dict(e) for e in block["elements"]],
            }
            for block in self._blocks
        ]

    @property
    def _elements(self) -> list[dict[str, Any]]:
        return self._blocks[self._current]["elements"]

    # --- Building the table ------------------------------------------------

    def _rebuild(self) -> None:
        """Rebuild columns and rows from the current block.

        Columns are recomputed every time because they depend on the
        shapes in play: choosing `Chirp` where a `Sin` was replaces three
        parameter columns with four. Qudi rebuilds for the same reason.
        """
        self._loading = True
        try:
            self._columns = columns(self._elements, self._channels)
            self.table.clear()
            self.table.setColumnCount(len(self._columns))
            self.table.setRowCount(len(self._elements))
            self.table.setHorizontalHeaderLabels(
                [
                    f"{c.label} ({c.unit})" if c.unit else c.label
                    for c in self._columns
                ]
            )
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

            for row, element in enumerate(self._elements):
                for index, column in enumerate(self._columns):
                    self._place(row, index, column, element)

            self.repetitions_spin.setValue(int(self._blocks[self._current]["repetitions"]))
        finally:
            self._loading = False
        self._announce()

    def _place(self, row: int, index: int, column: Any, element: dict) -> None:
        value = cell(element, column)

        if column.kind == DIGITAL:
            box = QCheckBox()
            box.setChecked(bool(value))
            box.toggled.connect(
                lambda checked, r=row, c=column: self._edit(r, c, bool(checked))
            )
            self.table.setCellWidget(row, index, self._centred(box))
            return

        if column.kind == SHAPE:
            combo = QComboBox()
            combo.addItems([_OFF, *sorted(SHAPES)])
            combo.setCurrentText(value or _OFF)
            combo.currentTextChanged.connect(
                lambda text, r=row, c=column: self._edit(r, c, text)
            )
            self.table.setCellWidget(row, index, combo)
            return

        if column.kind in (LENGTH, INCREMENT, ANALOG):
            if value is None:
                # This row's shape does not declare this parameter — the
                # cell is genuinely not applicable, so it is shown blank
                # and locked rather than defaulted to a misleading zero.
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(row, index, item)
                return
            spin = pg.SpinBox(
                value=float(value),
                suffix=column.unit or None,
                siPrefix=bool(column.unit),
                dec=True,
                step=1e-9 if column.unit == "s" else 0.01,
                minStep=1e-12,
                # An increment may be negative — a sweep can shorten an
                # element as well as lengthen it.
                bounds=(None, None) if column.kind == INCREMENT else (0.0, None),
            )
            spin.sigValueChanged.connect(
                lambda sb, r=row, c=column: self._edit(r, c, sb.value())
            )
            self.table.setCellWidget(row, index, spin)
            return

        self.table.setItem(row, index, QTableWidgetItem(str(value)))

    @staticmethod
    def _centred(widget: QWidget) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return holder

    # --- Editing -----------------------------------------------------------

    def _edit(self, row: int, column: Any, value: Any) -> None:
        if self._loading or not 0 <= row < len(self._elements):
            return
        self._elements[row] = set_cell(self._elements[row], column, value)

        if column.kind == SHAPE:
            # A new shape brings different parameters, so the columns
            # themselves change — the one edit that cannot be applied in
            # place.
            self._rebuild()
            return
        self._announce()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Only the Name column is a plain text cell; everything else is a
        widget and reports through its own signal."""
        if self._loading:
            return
        index = item.column()
        if 0 <= index < len(self._columns) and self._columns[index].kind == NAME:
            self._edit(item.row(), self._columns[index], item.text())

    def _on_block_selected(self, index: int) -> None:
        if self._loading or not 0 <= index < len(self._blocks):
            return
        self._current = index
        self._rebuild()

    def _on_repetitions_changed(self) -> None:
        if self._loading:
            return
        self._blocks[self._current]["repetitions"] = self.repetitions_spin.value()
        self._announce()

    # --- Row and block commands -------------------------------------------

    def _selected_row(self) -> int:
        row = self.table.currentRow()
        return row if row >= 0 else len(self._elements) - 1

    def add_element(self) -> None:
        self._elements.insert(self._selected_row() + 1, blank_element(self._channels))
        self._rebuild()

    def duplicate_element(self) -> None:
        """Which is how a real sequence gets built: a readout block is the
        same three elements every time."""
        row = self._selected_row()
        if 0 <= row < len(self._elements):
            self._elements.insert(row + 1, dict(self._elements[row]))
            self._rebuild()

    def remove_element(self) -> None:
        row = self._selected_row()
        # Never down to zero rows: an empty table has no columns to add a
        # row back through.
        if len(self._elements) > 1 and 0 <= row < len(self._elements):
            del self._elements[row]
            self._rebuild()

    def move_element(self, delta: int) -> None:
        row = self._selected_row()
        target = row + delta
        if 0 <= row < len(self._elements) and 0 <= target < len(self._elements):
            elements = self._elements
            elements[row], elements[target] = elements[target], elements[row]
            self._rebuild()
            self.table.selectRow(target)

    def add_block(self) -> None:
        self._blocks.insert(
            self._current + 1,
            {
                "name": f"block_{len(self._blocks)}",
                "repetitions": 1,
                "elements": [blank_element(self._channels)],
            },
        )
        self._current += 1
        self.set_blocks(self._blocks)

    def remove_block(self) -> None:
        if len(self._blocks) > 1:
            del self._blocks[self._current]
            self._current = max(self._current - 1, 0)
            self.set_blocks(self._blocks)

    # --- Reporting ---------------------------------------------------------

    def _announce(self) -> None:
        self.summary.setText(
            f"{len(self._blocks)} block(s), "
            f"{len(self._elements)} element(s) in this one, "
            f"{sum(len(b['elements']) * b['repetitions'] for b in self._blocks)} "
            f"instruction(s) total"
        )
        self.sigBlocksChanged.emit(self.blocks())
        self.sigPreviewRequested.emit()

    def set_locked(self, locked: bool) -> None:
        self.setEnabled(not locked)
