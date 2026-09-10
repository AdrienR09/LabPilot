#!/usr/bin/env python3
"""Verify the port map of a DAQ card can be edited in the settings window.

Configuring an NI card used to mean typing a channel string into the form
that creates the instrument, and then never being able to change it: the
settings tree renders a structured parameter as a group of its fields and
stops at a *table* of them, because rows are something a tree cannot add
or reorder.

So there is a component for the table, and this drives the real widget.
What it checks is the part a screenshot cannot: that the rows shown are
the card's own wiring, that Apply writes the **whole** table with every
declared field (a record rejects a partial one), and that when the device
refuses a row its own message is what appears.

The schema below is written out rather than taken from `mock_ni_card`,
and that is not laziness: importing `labpilot.instruments` pulls in every
registered adapter, a few of which load a second Qt binding through qtpy,
and the process then dies on the duplicate-class check before printing
anything. `tests/test_ni_card.py` asserts the real card declares exactly
this shape, so the two halves meet there — the same division of labour
`tests/` and `scripts/verify_*.py` have everywhere else in this repo.

Run it:

    QT_QPA_PLATFORM=offscreen python scripts/verify_channel_table.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "src" / "labpilot" / "ui" / "desktop"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DESKTOP))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
)

import labpilot.ui.qt_api  # noqa: F401, E402  (pins QT_API before Qt loads)

failures: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✅ {description}")
    else:
        print(f"  ❌ {description}{f' — {detail}' if detail else ''}")
        failures.append(description)


KINDS = ("ai", "ao", "ci", "di", "do", "co")

#: What `mock_ni_card`'s schema carries — see this module's docstring, and
#: `tests/test_ni_card.py::test_the_channel_table_is_declared_as_the_widget_expects`.
SCHEMA = {
    "name": "ni_card",
    "kind": "generic",
    "parameters": [
        {"name": "model", "dtype": "str", "settable": True,
         "choices": ["PCIe-6363", "USB-6008"]},
        {"name": "channels", "dtype": "record", "shape": [None], "settable": True,
         "description": "What is wired where.",
         "fields": [
             {"name": "name", "dtype": "str", "settable": True},
             {"name": "kind", "dtype": "str", "settable": True, "choices": list(KINDS)},
             {"name": "terminal", "dtype": "str", "settable": True},
             {"name": "source", "dtype": "str", "settable": True},
         ]},
        {"name": "x", "dtype": "f8", "settable": True, "unit": "V"},
    ],
}

WIRING = [
    {"name": "x", "kind": "ao", "terminal": "ao0", "source": ""},
    {"name": "y", "kind": "ao", "terminal": "ao1", "source": ""},
    {"name": "apd", "kind": "ci", "terminal": "ctr0", "source": "pfi8"},
    {"name": "pd", "kind": "ai", "terminal": "ai0", "source": ""},
]


class _Client:
    """Records writes, and refuses a terminal the way the adapter does.

    The refusal message is copied from `channels.py` deliberately: what is
    being checked here is that the *widget* shows whatever the device
    said, not that this harness can validate a terminal.
    """

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = [dict(row) for row in (rows if rows is not None else WIRING)]
        self.writes: list[dict] = []

    def read(self, _id):
        return {"channels": [dict(row) for row in self.rows]}

    def get_instrument(self, _id):
        return {"custom_settings": {}}

    def write(self, _id, values, persist=False):
        self.writes.append(values)
        rows = values.get("channels", [])
        for row in rows:
            terminal = str(row.get("terminal", ""))
            if terminal.startswith("ao") and terminal not in ("ao0", "ao1", "ao2", "ao3"):
                raise ValueError(
                    f"{row.get('name')!r} is wired to {terminal!r}, which the "
                    f"6363 does not have — it offers ao0, ao1, ao2, ao3"
                )
        self.rows = [dict(row) for row in rows]


def build(client: _Client):
    from components.base import InstrumentContext
    from components.channel_table import ChannelTableComponent

    window = QMainWindow()
    instrument = type(
        "I", (), {"id": "ni_card_1", "kind": "generic", "dimensionality": "GENERIC"}
    )()
    ctx = InstrumentContext(
        instrument=instrument, client=client, schema=SCHEMA,
        value_key=None, axis_key=None, units="", axis_units="",
    )
    component = ChannelTableComponent(window, ctx)
    component.build()
    return window, component


def table_of(window: QMainWindow):
    return window.findChild(QTableWidget)


def button(window: QMainWindow, label: str):
    return next(
        (b for b in window.findChildren(QPushButton) if b.text() == label), None
    )


def main() -> int:
    # Bound, not discarded: an unreferenced QApplication is collected the
    # moment it is created, and the next widget aborts the process.
    app = QApplication.instance() or QApplication([])
    assert app is not None

    print("1. The dock is built from the card's own wiring")
    client = _Client()
    window, _ = build(client)
    table = table_of(window)
    check("a table is built", table is not None)
    if table is None:
        return 1

    check("one row per configured channel", table.rowCount() == 4,
          f"got {table.rowCount()}")
    check("one column per declared field", table.columnCount() == 4,
          f"got {table.columnCount()}")
    headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    check("the columns are the record's own fields",
          headers == ["Name", "Kind", "Terminal", "Source"], str(headers))
    check("the rows are the wiring the device reports, in order",
          [table.item(r, 0).text() for r in range(4)] == ["x", "y", "apd", "pd"])
    check("a counter shows the terminal it counts",
          table.item(2, 3).text() == "pfi8")

    print("\n2. An enumerated field is a dropdown, not free text")
    kind_cell = table.cellWidget(0, 1)
    check("kind renders as a combo box", isinstance(kind_cell, QComboBox))
    if isinstance(kind_cell, QComboBox):
        choices = [kind_cell.itemData(i) for i in range(kind_cell.count())]
        check("it offers every channel kind", set(choices) == set(KINDS), str(choices))
        check("it starts on this channel's kind", kind_cell.currentData() == "ao")

    print("\n3. Apply writes the whole table, not the edited cell")
    table.item(0, 2).setText("ao2")
    apply = button(window, "Apply")
    check("there is an Apply button", apply is not None)
    if apply is None:
        return 1
    apply.click()

    check("exactly one write was made", len(client.writes) == 1, str(client.writes))
    written = client.writes[-1].get("channels", [])
    check("it carries every row", len(written) == 4, str(written))
    check("every row carries every declared field, blanks included",
          all(set(row) == {"name", "kind", "terminal", "source"} for row in written),
          str(written[:1]))
    check("the edit is in it", written[0]["terminal"] == "ao2")
    check("the table reloads from the device afterwards",
          table.item(0, 2).text() == "ao2")

    print("\n4. Adding and removing rows")
    client = _Client()
    window, _ = build(client)
    table = table_of(window)
    button(window, "Add row").click()
    check("Add row appends an empty row", table.rowCount() == 5)

    table.item(4, 0).setText("shutter")
    table.item(4, 2).setText("port0/line0")
    kind = table.cellWidget(4, 1)
    kind.setCurrentIndex([kind.itemData(i) for i in range(kind.count())].index("do"))
    button(window, "Apply").click()
    written = client.writes[-1]["channels"]
    check("the new row is written with its dropdown value",
          written[-1] == {"name": "shutter", "kind": "do",
                          "terminal": "port0/line0", "source": ""}, str(written[-1]))

    table.selectRow(0)
    button(window, "Remove selected").click()
    check("Remove drops the selected row", table.rowCount() == 4)
    button(window, "Apply").click()
    check("the removed channel is not in the write",
          "x" not in [row["name"] for row in client.writes[-1]["channels"]])

    print("\n5. A refused write shows the device's own message")
    client = _Client()
    window, _ = build(client)
    table = table_of(window)
    table.item(0, 2).setText("ao9")
    button(window, "Apply").click()

    messages = [w.text() for w in window.findChildren(QLabel)]
    check("the adapter's message is shown verbatim",
          any("ao9" in m and "ao0, ao1, ao2, ao3" in m for m in messages),
          str(messages))
    check("the wiring is unchanged", client.rows[0]["terminal"] == "ao0")

    print("\n6. An instrument with no record table gets no dock")
    from components.base import InstrumentContext
    from components.channel_table import ChannelTableComponent

    bare = QMainWindow()
    ctx = InstrumentContext(
        instrument=type("I", (), {"id": "x", "kind": "detector",
                                  "dimensionality": "0D"})(),
        client=_Client([]),
        schema={"parameters": [
            {"name": "value", "settable": False},
            # A record with no shape is a single structure — the settings
            # tree renders that one, and this must not also claim it.
            {"name": "gate", "settable": True, "dtype": "record",
             "fields": [{"name": "bins", "dtype": "i8"}]},
        ]},
        value_key="value", axis_key=None, units="", axis_units="",
    )
    ChannelTableComponent(bare, ctx).build()
    check("nothing is built without a record *table*", table_of(bare) is None)

    print("\n" + "=" * 78)
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"All channel-table checks passed ({_counted()} checks).")
    return 0


def _counted() -> int:
    return _COUNT[0]


_COUNT = [0]
_original_check = check


def check(description: str, condition: bool, detail: str = "") -> None:
    _COUNT[0] += 1
    _original_check(description, condition, detail)


if __name__ == "__main__":
    raise SystemExit(main())
