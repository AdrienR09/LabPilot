"""Editing a table of records — the port map of a DAQ card, in the window.

`SettingsTreeComponent` renders a structured parameter as a group of its
own fields, and stops at a *table* of them with a comment saying a
dedicated component owns those. This is that component, and it is generic:
it renders any settable parameter declared as `shape=(None,)` with
`fields`, whatever the instrument.

The case it was built for is an NI DAQ card. Which terminal the APD is
wired to, which two analog outputs drive the galvos, whether `port0/line3`
is the shutter — that is a table, it changes when someone re-plugs a BNC,
and until now it could only be set in the form that created the
instrument. A card's ports are not connection details; they are settings,
and they belong in the settings window beside everything else.

## Rows are validated by the device, not by this widget

Type a terminal the card does not have and the write is refused with a
message naming the terminals it does have — the same check a config file
or a script gets, because it lives in the adapter. So this widget is
deliberately thin: it collects rows, sends the whole table, and shows
whatever came back. Re-implementing the rules here would mean two
validators disagreeing, and the one in the window would be the one without
the hardware in front of it.

A `choices` field renders as a dropdown, everything else as a text cell.
That is enough for a port map, and it keeps this component honest about
what it is: a table editor, not a form builder.
"""

from __future__ import annotations

from typing import Any, ClassVar

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from labpilot.ui.desktop.components.base import UIComponent
from labpilot.ui.desktop.components.widgets import IconButton, dock


def table_parameters(schema: dict) -> list[dict]:
    """Every settable record-table parameter this instrument declares.

    A record table is `fields` plus a non-empty `shape` — one row per
    entry. A record with no shape is a single structure and the settings
    tree already renders it as a group.
    """
    return [
        param
        for param in (schema.get("parameters") or [])
        if param.get("settable")
        and param.get("fields")
        and list(param.get("shape") or [])
    ]


class ChannelTableComponent(UIComponent):
    """One dock per record-table parameter, with add/remove and Apply."""

    component_type = "channel_table"
    default_params: ClassVar[dict[str, Any]] = {"dock_title": ""}

    def build(self) -> None:
        parameters = table_parameters(self.ctx.schema)
        if not parameters:
            # Nothing to edit — safe to list this block unconditionally,
            # the same property `actions` and `settings_tree` have.
            return
        for param in parameters:
            self._build_one(param)

    # --- One parameter -----------------------------------------------------

    def _build_one(self, param: dict) -> None:
        fields = [f for f in param["fields"] if f.get("name")]
        name = param["name"]
        title = self.params.get("dock_title") or _title(name)

        table = QTableWidget(0, len(fields))
        table.setHorizontalHeaderLabels([_title(f["name"]) for f in fields])
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setVisible(False)
        for column, field in enumerate(fields):
            if field.get("description"):
                item = table.horizontalHeaderItem(column)
                item.setToolTip(str(field["description"]))

        status = QLabel(param.get("description", ""))
        status.setWordWrap(True)

        for row in self._current(name):
            _append(table, fields, row)

        def add() -> None:
            _append(table, fields, {})

        def remove() -> None:
            for index in sorted(
                {i.row() for i in table.selectedIndexes()}, reverse=True
            ):
                table.removeRow(index)

        def apply() -> None:
            rows = _rows(table, fields)
            try:
                self.ctx.client.write(self.ctx.instrument.id, {name: rows}, persist=True)
            except Exception as exc:
                # The adapter's own message, verbatim: it names the
                # terminal and what the card actually offers, which is
                # more than this widget could say.
                status.setText(str(exc))
                status.setStyleSheet("color: #d9534f;")
                return
            status.setText(f"{len(rows)} channel(s) applied.")
            status.setStyleSheet("")
            self._refresh(table, fields, name)

        buttons = QHBoxLayout()
        for label, handler in (
            ("Add row", add), ("Remove selected", remove), ("Apply", apply)
        ):
            if label == "Apply":
                buttons.addStretch(1)
            button = IconButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(table)
        layout.addLayout(buttons)
        layout.addWidget(status)

        panel = dock(title, self.window)
        panel.setWidget(body)
        self.window.addDockWidget(self._area(), panel)

    def _area(self):
        from PyQt6.QtCore import Qt

        return {
            "left": Qt.DockWidgetArea.LeftDockWidgetArea,
            "right": Qt.DockWidgetArea.RightDockWidgetArea,
            "top": Qt.DockWidgetArea.TopDockWidgetArea,
            "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
        }.get(self.params.get("area", "right"), Qt.DockWidgetArea.RightDockWidgetArea)

    # --- What the device currently holds -----------------------------------

    def _current(self, name: str) -> list[dict]:
        """The rows the instrument reports, falling back to what was staged.

        Reading wins: the device is the authority on its own wiring, and a
        staged value that failed to apply should not look applied.
        """
        try:
            reading = self.ctx.client.read(self.ctx.instrument.id) or {}
            rows = reading.get(name)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        except Exception:
            pass
        try:
            instrument = self.ctx.client.get_instrument(self.ctx.instrument.id) or {}
            rows = (instrument.get("custom_settings") or {}).get(name)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        except Exception:
            pass
        return []

    def _refresh(self, table: QTableWidget, fields: list[dict], name: str) -> None:
        table.setRowCount(0)
        for row in self._current(name):
            _append(table, fields, row)


def _title(name: str) -> str:
    return str(name).replace("_", " ").title()


def _append(table: QTableWidget, fields: list[dict], row: dict) -> None:
    index = table.rowCount()
    table.insertRow(index)
    for column, field in enumerate(fields):
        value = row.get(field["name"], "")
        choices = field.get("choices")
        if choices:
            combo = QComboBox()
            for choice in choices:
                combo.addItem(str(choice), choice)
            position = combo.findData(value)
            if position >= 0:
                combo.setCurrentIndex(position)
            table.setCellWidget(index, column, combo)
        else:
            table.setItem(index, column, QTableWidgetItem("" if value is None else str(value)))


def _rows(table: QTableWidget, fields: list[dict]) -> list[dict[str, Any]]:
    """The table's contents, one dict per row.

    Every declared field is written, empty string included: a record
    rejects an undeclared key *and* a missing one, and a blank `source` on
    an analog channel is a real value rather than an omission.
    """
    rows: list[dict[str, Any]] = []
    for index in range(table.rowCount()):
        row: dict[str, Any] = {}
        for column, field in enumerate(fields):
            widget = table.cellWidget(index, column)
            if isinstance(widget, QComboBox):
                row[field["name"]] = widget.currentData()
            else:
                item = table.item(index, column)
                row[field["name"]] = item.text().strip() if item else ""
        if any(str(value).strip() for value in row.values()):
            rows.append(row)
    return rows
