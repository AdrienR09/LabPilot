#!/usr/bin/env python3
"""Verify the pulse sequence editor's UI — the dock and the timing diagram.

Two claims are checked here, and they are the two the free-standing design
rests on:

1. **The editor's controls come from the generator and the rig profile,
   not from a connected pulser.** The Parameters form is built from each
   generator's declared `Parameter` objects, so its units, limits and
   dtypes are stated rather than guessed from a name; and the channel
   columns come from the rig profile's symbolic names, which is the one
   source of truth an offline editor has. Nothing here constructs a
   client, and nothing reads an instrument schema.

2. **The block table is a real editor**, not a read-only view: rows are
   added, reordered and typed into, the columns follow the shapes in play,
   and every edit produces a sequence that still builds.

3. **The timing diagram draws what the sequence actually contains** — one
   lane per channel, one box per element, at one point of the sweep.

Run it:

    QT_QPA_PLATFORM=offscreen python scripts/verify_pulse_editor.py

Not a pytest test, deliberately — same reason as `verify_ui_registry.py`
and `verify_settings_tree.py`: `tests/` is the headless, Qt-free suite,
and importing pymodaq_gui's Qt stack into it crashes collection with a
metaclass conflict.
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

from PyQt6.QtWidgets import QApplication, QSpinBox  # noqa: E402

import labpilot.ui.qt_api  # noqa: F401, E402  (pins QT_API before Qt loads)
from labpilot.core.pulse import timing_diagram  # noqa: E402
from labpilot.core.pulse.table import sequence_from_table, table_from_sequence  # noqa: E402
from labpilot.core.pulse.library import (  # noqa: E402
    GENERATORS,
    RigProfile,
    build,
    generator_parameters,
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{label}{f' ({detail})' if detail else ''}")


DEFAULTS = {
    "GENERATOR": "rabi",
    "SEQUENCE_NAME": "rabi",
    "GENERATOR_PARAMS": {"tau_start": 20e-9, "tau_step": 20e-9, "points": 50},
    "RABI_PERIOD": 200e-9,
    "MW_FREQUENCY": 2.87e9,
    "MW_AMPLITUDE": 0.25,
    "LASER_LENGTH": 3e-6,
    "LASER_DELAY": 700e-9,
    "WAIT_TIME": 1e-6,
    "LASER_CHANNEL": "laser",
    "MW_CHANNEL": "mw",
    "GATE_CHANNEL": "gate",
    "ANALOG_MW": True,
    "PREVIEW_POINT": 0,
}


def main() -> int:
    app = QApplication.instance() or QApplication([])

    from components.pulse_editor import PulseEditorControlWidget
    from components.workflow_result import PulseSequenceResultView

    print("1. The control dock builds with no client and no instrument")
    edits: list[tuple[str, object]] = []
    editor = PulseEditorControlWidget(
        DEFAULTS, parameters_for=generator_parameters, generators=sorted(GENERATORS)
    )
    editor.sigParamChanged.connect(lambda name, value: edits.append((name, value)))
    app.processEvents()
    check("it built", editor is not None)
    check("it offers every generator",
          editor.generator_combo.count() == len(GENERATORS),
          f"{editor.generator_combo.count()} of {len(GENERATORS)}")
    check("it holds no network client", not hasattr(editor, "client"))

    print("\n2. Parameter controls come from the generator's declarations")
    for name in sorted(GENERATORS):
        editor._rebuild_generator_form(name)
        app.processEvents()
        declared = [p.name for p in generator_parameters(name)]
        built = list(editor._generator_widgets)
        check(f"{name}: one control per declared parameter",
              built == declared, f"{built} != {declared}")
        integers = [p.name for p in generator_parameters(name) if p.dtype.startswith("i")]
        for param in integers:
            check(f"{name}: {param} is an integer control",
                  isinstance(editor._generator_widgets[param], QSpinBox),
                  type(editor._generator_widgets[param]).__name__)

    print("\n3. Editing a parameter reports it, without writing anything")
    editor._rebuild_generator_form("rabi")
    edits.clear()
    editor._generator_widgets["points"].setValue(20)
    editor._emit_generator_params()
    app.processEvents()
    check("the edit was reported", any(n == "GENERATOR_PARAMS" for n, _ in edits),
          f"{edits}")
    reported = dict(edits)["GENERATOR_PARAMS"]
    check("it carries the whole parameter set, not the one field",
          set(reported) == {p.name for p in generator_parameters("rabi")},
          f"{sorted(reported)}")
    check("it carries the new value", reported.get("points") == 20, f"{reported}")

    print("\n4. Switching generator replaces the form and its stored params")
    edits.clear()
    editor.generator_combo.setCurrentText("hahn_echo")
    app.processEvents()
    names = [name for name, _ in edits]
    check("the generator change was reported", "GENERATOR" in names, f"{names}")
    check("fresh parameters were sent with it", "GENERATOR_PARAMS" in names, f"{names}")
    check("the form now matches hahn_echo",
          list(editor._generator_widgets) == [p.name for p in generator_parameters("hahn_echo")],
          f"{list(editor._generator_widgets)}")

    print("\n5. Channel columns come from the rig profile, not from a pulser")
    check("three symbolic channels by default",
          editor.channels() == ["laser", "mw", "gate"], f"{editor.channels()}")
    editor._channel_edits["GATE_CHANNEL"].setText("")
    check("an ungated rig drops the gate column",
          editor.channels() == ["laser", "mw"], f"{editor.channels()}")
    editor._channel_edits["LASER_CHANNEL"].setText("green")
    check("a renamed channel follows through",
          editor.channels()[0] == "green", f"{editor.channels()}")

    print("\n6. A digital rig disables the analog drive controls")
    editor.analog_check.setChecked(False)
    app.processEvents()
    check("amplitude is disabled", not editor.amplitude_spin.isEnabled())
    check("it was reported", ("ANALOG_MW", False) in edits, f"{edits[-3:]}")
    editor.analog_check.setChecked(True)
    check("and re-enabled", editor.amplitude_spin.isEnabled())

    print("\n7. The pi/pi-2 hint follows the Rabi period")
    editor._rig_spins["RABI_PERIOD"].setValue(400e-9)
    app.processEvents()
    check("the hint states both derived lengths",
          "200.0 ns" in editor.rabi_hint.text() and "100.0 ns" in editor.rabi_hint.text(),
          editor.rabi_hint.text())

    print("\n8. The block table is a real editor")
    from components.pulse_blocks import PulseBlockEditorWidget

    edits: list = []
    blocks = table_from_sequence(build("ramsey", RigProfile(), points=6))
    table = PulseBlockEditorWidget(blocks, ["laser", "mw", "gate"])
    table.sigBlocksChanged.connect(edits.append)
    app.processEvents()

    headers = [
        table.table.horizontalHeaderItem(i).text()
        for i in range(table.table.columnCount())
    ]
    check("it loaded the generated block",
          table.table.rowCount() == len(blocks[0]["elements"]),
          f"{table.table.rowCount()} rows")
    check("columns include length and increment",
          any("Length" in h for h in headers) and any("Increment" in h for h in headers),
          f"{headers}")
    check("an analog channel grew its shape and parameter columns",
          any("mw shape" in h for h in headers)
          and any("mw frequency" in h for h in headers),
          f"{headers}")
    check("a digital channel is one column",
          sum("laser" in h for h in headers) == 1, f"{headers}")

    print("\n9. Editing the table reports a sequence that still builds")
    before = table.table.rowCount()
    table.table.selectRow(0)
    table.add_element()
    app.processEvents()
    check("adding a row grew the table", table.table.rowCount() == before + 1)
    check("the edit was reported", bool(edits), f"{len(edits)} report(s)")

    table.duplicate_element()
    table.move_element(+1)
    table.remove_element()
    app.processEvents()
    reported = edits[-1]
    check("every command reported a table",
          isinstance(reported, list) and reported, f"{type(reported).__name__}")
    rebuilt = sequence_from_table(
        reported, "edited", alternating=True, validate=False
    )
    check("what the table reports still builds a sequence",
          len(rebuilt.blocks[0].elements) == table.table.rowCount(),
          f"{len(rebuilt.blocks[0].elements)} vs {table.table.rowCount()}")

    print("\n10. Choosing a different shape rebuilds the columns")
    shape_index = next(
        i for i in range(table.table.columnCount())
        if "mw shape" in table.table.horizontalHeaderItem(i).text()
    )
    combo = table.table.cellWidget(0, shape_index)
    check("the shape cell is a combobox", combo is not None,
          f"{type(combo).__name__}")
    if combo is not None:
        combo.setCurrentText("Chirp")
        app.processEvents()
        headers = [
            table.table.horizontalHeaderItem(i).text()
            for i in range(table.table.columnCount())
        ]
        check("a Chirp brought its own parameter columns",
              any("start frequency" in h for h in headers), f"{headers}")

    print("\n11. Blocks can be added and removed")
    table.add_block()
    app.processEvents()
    check("a second block exists", table.block_combo.count() == 2,
          f"{table.block_combo.count()}")
    table.remove_block()
    app.processEvents()
    check("and can be removed", table.block_combo.count() == 1)
    for _ in range(10):
        table.remove_block()
    check("the last block is never removed", table.block_combo.count() == 1)

    print("\n12. The timing diagram draws one lane per channel")
    view = PulseSequenceResultView()
    for name in sorted(GENERATORS):
        sequence = build(name, RigProfile(), points=8)
        segments = [s.to_dict() for s in timing_diagram(sequence, 0)]
        duration = max(s["stop"] for s in segments)
        view.update_data(segments, sorted(sequence.channels), duration)
        app.processEvents()

        ticks = view._axis._tickLevels
        lanes = {label for _, label in (ticks[0] if ticks else [])}
        check(f"{name}: a lane per channel it uses",
              lanes == set(sequence.channels), f"{sorted(lanes)}")
        check(f"{name}: the summary states the pulse count",
              f"{len(segments)} pulse(s)" in view.summary.text(), view.summary.text())

    print("\n13. A later point of the sweep draws a longer diagram")
    sequence = build("rabi", RigProfile(), points=30)
    first = max(s.stop for s in timing_diagram(sequence, 0))
    last = max(s.stop for s in timing_diagram(sequence, 29))
    check("the swept element has grown", last > first, f"{last} !> {first}")

    print("\n14. An empty result leaves the view legible rather than blank")
    view.update_data([], [], 0.0)
    app.processEvents()
    check("it says there is nothing yet", "No sequence" in view.summary.text(),
          view.summary.text())

    print("\n" + "=" * 70)
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All pulse-editor checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
