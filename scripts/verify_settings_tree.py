#!/usr/bin/env python3
"""Verify that the settings tree renders every declared parameter type.

The tree supported exactly two widgets — bool and float — and coerced
everything else through `float()`. An integer setting rendered as a float,
a string setting rendered as a float of it (or crashed), an enumerated
setting rendered as a free numeric field with no hint of its choices, and
a structured setting rendered as nothing at all because `dtype="json"` was
skipped outright.

That mattered most for the devices this project is heading toward: a pulse
sequencer's setpoint is a table, an AWG's channel map is a record, and a
counter's mode is a choice. This checks each declared kind actually
produces the right widget, and that editing one field of a record writes
the whole record rather than the bare field — the bug you would otherwise
only find against hardware.

Run it:

    QT_QPA_PLATFORM=offscreen python scripts/verify_settings_tree.py

Not a pytest test, deliberately — same reason as verify_ui_registry.py:
`tests/` is the headless, Qt-free suite, and importing pymodaq_gui's Qt
stack into it crashes collection with a metaclass conflict.
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

import labpilot.ui.qt_api  # noqa: F401, E402  (pins QT_API before Qt loads)
from labpilot.core.device.parameter import Parameter, ParamRole  # noqa: E402
from labpilot.core.device.schema import DeviceSchema  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402

failures: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✅ {description}")
    else:
        print(f"  ❌ {description}{f' — {detail}' if detail else ''}")
        failures.append(description)


SCHEMA = DeviceSchema(
    name="bench_pulser",
    kind="generic",
    # The dock shows settable-but-not-readable names — config knobs, as
    # opposed to live controls like an actuator's position. So every
    # setting below is `readable=False`, which is what an adapter
    # declaring `settable={...}` with no matching `readable` entry gets.
    parameters=(
        Parameter("running", dtype="bool", role=ParamRole.STATUS),
        Parameter("shots", dtype="i8", settable=True, readable=False,
                  role=ParamRole.SETTING, limits=(1, 1000)),
        Parameter("label", dtype="str", settable=True, readable=False,
                  role=ParamRole.SETTING),
        Parameter("mode", dtype="str", settable=True, readable=False,
                  role=ParamRole.SETTING, choices=("gated", "ungated")),
        Parameter("threshold_v", unit="V", settable=True, readable=False,
                  role=ParamRole.SETTING, limits=(0.0, 5.0)),
        Parameter("gate", settable=True, readable=False, role=ParamRole.SETTING,
                  fields=(
                      Parameter("bin_width_s", unit="s", settable=True,
                                limits=(1e-12, 1.0)),
                      Parameter("gates", dtype="i8", settable=True, limits=(1, None)),
                  )),
        Parameter("sequence", shape=(None,), settable=True, readable=False,
                  role=ParamRole.SETTING, fields=(
                      Parameter("duration_ns", unit="ns", settable=True),
                      Parameter("channel", dtype="i8", settable=True),
                  )),
    ),
)

STAGED = {
    "shots": 25,
    "label": "rabi",
    "mode": "ungated",
    "threshold_v": 1.5,
    "gate": {"bin_width_s": 2e-9, "gates": 50},
}


class _Client:
    """Records writes instead of making them."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict]] = []

    def get_instrument(self, _id):
        return {"custom_settings": dict(STAGED)}

    def write(self, instrument_id, values, persist=False):
        self.writes.append((instrument_id, values))


def main() -> int:
    app = QApplication.instance() or QApplication([])
    from components.base import InstrumentContext  # noqa: PLC0415
    from components.settings_tree import SettingsTreeComponent  # noqa: PLC0415

    client = _Client()
    window = QMainWindow()
    instrument = type("I", (), {"id": "bench_pulser", "kind": "generic",
                                "dimensionality": "GENERIC"})()
    ctx = InstrumentContext(
        instrument=instrument, client=client, schema=SCHEMA.model_dump(),
        value_key=None, axis_key=None, units="", axis_units="",
    )

    component = SettingsTreeComponent(window, ctx)
    component.build()

    tree = getattr(component, "dock_widget", None)
    check("the settings dock is built at all", tree is not None)
    if tree is None:
        return 1

    # Walk the parametertree's model rather than the widgets: that is what
    # decides the editor, and it is what a wrong dtype corrupts. With
    # showTop=False the built group's children are the top-level items.
    # showTop=False hides the root group but still keeps it as the one
    # top-level item, so the built parameters are its children.
    widget = tree.widget()
    root = widget.topLevelItem(0).param
    by_name = {p.name(): p for p in root.children()}

    print("\n1. Each declared dtype gets the right widget")
    expected = {
        "shots": "int", "label": "str", "mode": "list",
        "threshold_v": "float", "gate": "group",
    }
    for name, want in expected.items():
        got = by_name.get(name)
        check(f"{name} renders as {want}",
              got is not None and got.opts.get("type") == want,
              f"got {got.opts.get('type') if got is not None else 'nothing'}")

    print("\n2. Declared metadata reaches the widget")
    check("an enumerated setting offers its choices",
          list(by_name["mode"].opts.get("limits") or []) == ["gated", "ungated"])
    check("the staged value is selected, not the first choice",
          by_name["mode"].value() == "ungated")
    check("a limit becomes the spin box's range",
          tuple(by_name["shots"].opts.get("limits") or ()) == (1, 1000))
    check("a unit becomes the suffix",
          by_name["threshold_v"].opts.get("suffix") == " V")
    check("an integer setting keeps its integer value",
          by_name["shots"].value() == 25)

    print("\n3. A record is a group of its own fields")
    gate = by_name.get("gate")
    gate_fields = {c.name(): c for c in gate.children()} if gate is not None else {}
    check("the record's fields are its children",
          sorted(gate_fields) == ["bin_width_s", "gates"])
    check("a field carries its own unit", gate_fields["bin_width_s"].opts.get("suffix") == " s")
    check("a field carries its own dtype", gate_fields["gates"].opts.get("type") == "int")
    check("the staged record fills its fields", gate_fields["gates"].value() == 50)

    print("\n4. A table of records is left to a dedicated component")
    check("the sequence table is not rendered as a row", "sequence" not in by_name)

    print("\n5. Editing one field writes the whole record")
    client.writes.clear()
    gate_fields["gates"].setValue(64)
    app.processEvents()
    check("exactly one write went out", len(client.writes) == 1,
          f"{len(client.writes)} writes")
    if client.writes:
        _, values = client.writes[0]
        check("it is addressed to the record, not the field", "gate" in values,
              f"wrote {list(values)}")
        check("it carries every field of the record",
              values.get("gate") == {"bin_width_s": 2e-9, "gates": 64},
              f"wrote {values.get('gate')}")

    print("\n6. An ordinary setting still writes itself")
    client.writes.clear()
    by_name["shots"].setValue(30)
    app.processEvents()
    check("a plain setting writes its own name",
          client.writes and client.writes[0][1] == {"shots": 30},
          f"wrote {client.writes}")

    print("\n" + "=" * 70)
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All settings-tree checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
