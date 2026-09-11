#!/usr/bin/env python3
"""Verify the pulse sequence editor's UI — the timeline canvas and its dock.

Three claims are checked here, and they are the ones the design rests on:

1. **The editor is the timeline.** One lane per instrument — laser,
   microwave, APD readout — with pulses drawn on the lanes and sweep
   regions shaded across them. Pulses move and resize; a pulse belongs to
   an instrument, so a vertical wobble must not move it to another lane.

2. **The lanes come from the rig profile, not from a connected pulser.**
   An offline editor has no pulser to ask, and a sequence that took its
   channels from one would be tied to one rig's wiring. Nothing here
   constructs a client, and nothing reads an instrument schema.

3. **What is drawn is what gets played.** Every edit produces a timeline
   that still compiles to a valid sequence, and the sweep drawn on the
   canvas is the sweep the run will report.

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
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "src" / "labpilot" / "ui" / "desktop"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DESKTOP))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import labpilot.ui.qt_api  # noqa: F401, E402  (pins QT_API before Qt loads)
from labpilot.core.pulse import timing_diagram  # noqa: E402
from labpilot.core.pulse.library import (  # noqa: E402
    GENERATORS,
    RigProfile,
    build,
)
from labpilot.core.pulse.tracks import (  # noqa: E402
    DURATION,
    FREQUENCY,
    LINEAR,
    LOG,
    SweepAxis,
    Timeline,
    timeline_from_sequence,
)

failures: list[str] = []

NS = 1e-9
US = 1e-6


def close(value: float, expected: float, tolerance: float = 1e-15) -> bool:
    """Times are floats and 250 * 1e-9 is not 2.5e-7 exactly, so every
    comparison here is a tolerance rather than an equality."""
    return abs(value - expected) <= tolerance


#: How the canvas marks the lane a run actually measures.
MEASURED = "measured"


def _lane(label: str) -> str:
    """A lane's channel name, without the mark the readout lane carries."""
    return label.split("\u27f5")[0].strip()


def shown(widget: object) -> bool:
    """Whether a widget would be visible once its window is.

    `isVisible()` is False for every widget here — nothing is ever shown
    in an offscreen harness — so the question to ask is whether it was
    explicitly hidden.
    """
    return not widget.isHidden()


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{label}{f' ({detail})' if detail else ''}")


DEFAULTS = {
    "TIMELINE": {},
    "START_FROM": "rabi",
    "SEQUENCE_NAME": "rabi",
    "ALTERNATING": False,
    "RABI_PERIOD": 200e-9,
    "MW_FREQUENCY": 2.87e9,
    "MW_AMPLITUDE": 0.25,
    "LASER_LENGTH": 3e-6,
    "LASER_DELAY": 700e-9,
    "WAIT_TIME": 1e-6,
    "CHANNELS": [
        {"name": "laser", "kind": "laser"},
        {"name": "mw", "kind": "mw"},
        {"name": "gate", "kind": "gate"},
    ],
    "ANALOG_MW": True,
}


def rabi_timeline(points: int = 12) -> Timeline:
    return timeline_from_sequence(
        build("rabi", RigProfile(), points=points), ("laser", "mw", "gate")
    )


def main() -> int:
    from components.pulse_editor import PulseEditorControlWidget
    from components.pulse_timeline import PulseItem, PulseTimelineWidget
    from components.workflow_result import PulseSequenceResultView

    app = QApplication.instance() or QApplication([])

    print("1. The dock builds from parameters alone — no client, no schema")
    params = dict(DEFAULTS, TIMELINE=rabi_timeline().to_dict())
    dock = PulseEditorControlWidget(params, generators=sorted(GENERATORS))
    app.processEvents()
    check("it holds no client", not hasattr(dock, "client"))
    check(
        "two tabs: the selected pulse, and the rig profile",
        [dock.tabs.tabText(i) for i in range(dock.tabs.count())]
        == ["Pulse", "Rig profile"],
        f"{[dock.tabs.tabText(i) for i in range(dock.tabs.count())]}",
    )
    check(
        "and the folder the file lands in is spelled out",
        "sequences" in dock.path_label.text() and "rabi.json" in dock.path_label.text(),
        dock.path_label.text(),
    )
    check(
        "the canvas is not in a tab at all — it is the window",
        dock.timeline.parent() is not dock.tabs
        and dock.tabs.indexOf(dock.timeline) == -1,
    )

    print("\n2. One lane per instrument, including the APD readout")
    canvas = dock.timeline
    lanes = [_lane(label) for _, label in canvas._axis._tickLevels[0]]
    check("a lane per declared channel", lanes == ["laser", "mw", "gate"], f"{lanes}")
    check("in reading order, laser first", lanes[0] == "laser")
    check(
        "the APD readout has its own lane",
        "gate" in lanes,
        f"{lanes}",
    )

    print("\n2b. One lane is the measurement, and it says so")
    marked = [label for _, label in canvas._axis._tickLevels[0] if MEASURED in label]
    check(
        "the gate lane is marked as the measurement",
        [_lane(label) for label in marked] == ["gate"],
        f"{marked}",
    )
    ungated = PulseEditorControlWidget(
        dict(DEFAULTS, CHANNELS=[
            {"name": "laser", "kind": "laser"}, {"name": "mw", "kind": "mw"},
        ]),
        generators=sorted(GENERATORS),
    )
    app.processEvents()
    ungated_marked = [
        _lane(label) for _, label in ungated.timeline._axis._tickLevels[0]
        if MEASURED in label
    ]
    check(
        "with no gate, the laser lane is the measurement",
        ungated_marked == ["laser"],
        f"{ungated_marked}",
    )

    print("\n3. The lanes come from the rig profile, not from a pulser")
    renamed = dict(DEFAULTS, CHANNELS=[
        {"name": "laser", "kind": "laser"},
        {"name": "microwave", "kind": "mw"},
        {"name": "apd_gate", "kind": "gate"},
    ])
    other = PulseEditorControlWidget(renamed, generators=sorted(GENERATORS))
    app.processEvents()
    check(
        "a renamed channel is a renamed lane",
        [_lane(label) for _, label in other.timeline._axis._tickLevels[0]]
        == ["laser", "microwave", "apd_gate"],
        f"{[label for _, label in other.timeline._axis._tickLevels[0]]}",
    )

    print("\n4. Pulses are drawn as movable items, one per drawn pulse")
    drawn = sum(len(track.pulses) for track in canvas.timeline.tracks)
    check("an item per pulse", len(canvas._items) == drawn, f"{len(canvas._items)}/{drawn}")
    check("every item is movable", all(item.translatable for item in canvas._items))
    check(
        "and resizable from both ends",
        all(len(item.handles) == 2 for item in canvas._items),
        f"{[len(i.handles) for i in canvas._items]}",
    )

    print("\n5. Dragging a pulse moves it, snapped to the grid")
    item = next(i for i in canvas._items if canvas.timeline.tracks[i.lane].channel == "mw")
    edits: list[object] = []
    canvas.sigTimelineChanged.connect(edits.append)
    item.setPos(103 * NS, item.pos().y())
    item.sigRegionChangeFinished.emit(item)
    app.processEvents()
    moved = canvas.timeline.track("mw").pulses[0]
    check("the pulse moved", close(moved.start, 100 * NS), f"{moved.start}")
    check("snapped to the 10 ns grid",
          close(moved.start, round(moved.start / canvas._snap) * canvas._snap))
    check("and the edit was reported", len(edits) >= 1, f"{len(edits)}")

    print("\n6. A pulse cannot be dragged onto another instrument's lane")
    item = next(i for i in canvas._items if canvas.timeline.tracks[i.lane].channel == "mw")
    lane = item.lane
    item.setPos(item.pos().x(), item.pos().y() + 1.0)
    item.sigRegionChangeFinished.emit(item)
    app.processEvents()
    check(
        "it stayed on its own track",
        canvas.timeline.tracks[lane].channel == "mw"
        and len(canvas.timeline.track("mw").pulses) == 1,
    )

    print("\n7. Resizing an edge changes the pulse's length")
    item = next(i for i in canvas._items if canvas.timeline.tracks[i.lane].channel == "mw")
    item.setSize((250 * NS, 0.7))
    item.sigRegionChangeFinished.emit(item)
    app.processEvents()
    check(
        "the length followed the handle",
        close(canvas.timeline.track("mw").pulses[0].duration, 250 * NS),
        f"{canvas.timeline.track('mw').pulses[0].duration}",
    )

    print("\n8. Pulses can be added to a track and deleted from it")
    before = len(canvas.timeline.track("gate").pulses)
    canvas.add_pulse("gate")
    app.processEvents()
    check("a pulse was added", len(canvas.timeline.track("gate").pulses) == before + 1)
    check("it went on the chosen track", canvas.timeline.track("gate").pulses)

    added = canvas.timeline.track("gate").pulses[-1]
    canvas._item_clicked(next(i for i in canvas._items if i.pulse == added))
    canvas.remove_selected()
    app.processEvents()
    check("and can be deleted", len(canvas.timeline.track("gate").pulses) == before)

    print("\n9. The inspector types what dragging cannot set")
    drive = next(i for i in canvas._items if canvas.timeline.tracks[i.lane].channel == "mw")
    canvas._item_clicked(drive)
    app.processEvents()
    check("selecting a pulse enables the inspector", canvas.pulse_name.isEnabled())
    check(
        "an analog pulse offers its shape",
        canvas.shape_combo.currentData() == "Sin",
        f"{canvas.shape_combo.currentData()}",
    )
    rows = canvas.shape_layout.rowCount()
    check(
        "one row per parameter the shape declares",
        rows == 3,  # Sin: amplitude, frequency, phase
        f"{rows}",
    )
    canvas._shape_param_changed("frequency", 2.8e9)
    app.processEvents()
    check(
        "editing one keeps the others",
        canvas.timeline.track("mw").pulses[0].value.frequency == 2.8e9
        and canvas.timeline.track("mw").pulses[0].value.amplitude
        == drive.pulse.value.amplitude,
    )

    print("\n10. A digital pulse becomes analog by naming a shape")
    canvas.add_pulse("gate")
    app.processEvents()
    fresh = canvas.timeline.track("gate").pulses[-1]
    check("a new pulse is digital", fresh.value is True)
    canvas._item_clicked(next(i for i in canvas._items if i.pulse == fresh))
    canvas.shape_combo.setCurrentIndex(canvas.shape_combo.findData("Gauss"))
    app.processEvents()
    check(
        "choosing a shape makes it analog",
        canvas.timeline.track("gate").pulses[-1].analog,
    )
    canvas.remove_selected()

    print("\n11. The sweep is a property of a pulse, drawn on that pulse")
    marked = [p for t in canvas.timeline.tracks for p in t.pulses if p.sweep]
    check("the Rabi's drive is what is marked", len(marked) == 1, f"{len(marked)}")
    check("and it is the microwave pulse", marked[0] in canvas.timeline.track("mw").pulses)
    check("its span is shaded across every lane", len(canvas._regions) == 1,
          f"{len(canvas._regions)}")
    item = next(i for i in canvas._items if i.pulse.sweep)
    check(
        "and the pulse itself is outlined as swept",
        item.currentPen.color().name() == PulseItem.SWEPT,
        item.currentPen.color().name(),
    )

    print("\n12. Marking a second pulse puts it on the same axis")
    other = next(
        i for i in canvas._items
        if canvas.timeline.tracks[i.lane].channel == "gate"
    )
    canvas._item_clicked(other)
    app.processEvents()
    canvas.sweep_combo.setCurrentIndex(canvas.sweep_combo.findData(DURATION))
    app.processEvents()
    lengths = [p.duration for p in canvas.timeline.swept]
    check("both are marked", len(lengths) == 2, f"{lengths}")
    check(
        "and they were made the same length — they are one axis",
        max(lengths) - min(lengths) < 1e-15,
        f"{lengths}",
    )
    canvas.sweep_combo.setCurrentIndex(canvas.sweep_combo.findData(""))
    app.processEvents()
    check("unmarking one leaves the other", len(canvas.timeline.swept) == 1)

    print("\n13. The axis is edited from the pulse that carries it")
    fresh = PulseEditorControlWidget(
        dict(DEFAULTS, TIMELINE=rabi_timeline().to_dict()),
        generators=sorted(GENERATORS),
    )
    app.processEvents()
    canvas = fresh.timeline
    drive = next(i for i in canvas._items if i.pulse.sweep == DURATION)
    canvas._item_clicked(drive)
    app.processEvents()
    check("its axis fields are shown", shown(canvas.axis_form))
    check(
        "the first value is the length that was drawn",
        close(float(canvas.axis_start.value()), drive.pulse.duration),
        f"{canvas.axis_start.value()} vs {drive.pulse.duration}",
    )
    canvas.axis_points.setValue(31)
    app.processEvents()
    check("points reach the timeline", canvas.timeline.sweep.points == 31)
    canvas.axis_spacing.setCurrentIndex(canvas.axis_spacing.findData(LOG))
    app.processEvents()
    check("so does the spacing", canvas.timeline.sweep.spacing == LOG)
    check(
        "and the values the run will take",
        len(canvas.timeline.sweep_values()) == 31,
        f"{len(canvas.timeline.sweep_values())}",
    )

    print("\n13b. A pulse that drives nothing is a gap you can sweep")
    canvas.axis_spacing.setCurrentIndex(canvas.axis_spacing.findData(LINEAR))
    app.processEvents()
    gate = next(
        i for i in canvas._items
        if canvas.timeline.tracks[i.lane].channel == "gate"
    )
    canvas._item_clicked(gate)
    app.processEvents()
    check(
        "the readout lane labels it as a measurement",
        "Measurement" in canvas.drives_check.text(),
        canvas.drives_check.text(),
    )
    canvas.drives_check.setChecked(False)
    app.processEvents()
    sequence = canvas.timeline.to_sequence("after", validate=False)
    check(
        "unchecking it stops gating the counter at all",
        "gate" not in sequence.channels,
        f"{sorted(sequence.channels)}",
    )
    check(
        "so the rig is ungated and the laser pulses are the readouts",
        sequence.readout_channel == "laser",
        sequence.readout_channel,
    )
    check("but the block still holds its time",
          close(canvas.timeline.end, fresh.timeline.timeline.end))
    check(
        "and it is drawn hollow rather than filled",
        next(i for i in canvas._items if not i.pulse.drives).brush.color()
        != next(i for i in canvas._items if i.pulse.drives).brush.color(),
    )

    print("\n13c. Only a drive is offered the frequency sweep")
    modes = [canvas.sweep_combo.itemData(i) for i in range(canvas.sweep_combo.count())]
    check("not on the readout lane", modes == ["", DURATION], f"{modes}")
    laser = next(
        i for i in canvas._items
        if canvas.timeline.tracks[i.lane].channel == "laser"
    )
    canvas._item_clicked(laser)
    app.processEvents()
    modes = [canvas.sweep_combo.itemData(i) for i in range(canvas.sweep_combo.count())]
    check("nor on the laser lane", modes == ["", DURATION], f"{modes}")
    mw = next(
        i for i in canvas._items
        if canvas.timeline.tracks[i.lane].channel == "mw"
    )
    canvas._item_clicked(mw)
    app.processEvents()
    modes = [canvas.sweep_combo.itemData(i) for i in range(canvas.sweep_combo.count())]
    check("but it is on the microwave lane", modes == ["", DURATION, FREQUENCY],
          f"{modes}")

    print("\n13d. Sweeping the frequency leaves the drawing alone")
    before = [
        (p.start, p.stop) for t in canvas.timeline.tracks for p in t.sorted()
    ]
    canvas.sweep_combo.setCurrentIndex(canvas.sweep_combo.findData(FREQUENCY))
    app.processEvents()
    check("the axis becomes a frequency", canvas.timeline.sweep_quantity == FREQUENCY)
    values = canvas.timeline.sweep_values()
    check("in hertz, not seconds", values.unit == "Hz" and values.name == "frequency")
    check("with endpoints a rig would recognise", values.values[0] > 1e9,
          f"{values.values[0]}")
    check(
        "and not one drawn pulse moved",
        before == [
            (p.start, p.stop) for t in canvas.timeline.tracks for p in t.sorted()
        ],
    )
    check("nothing is shaded, because nothing grows", canvas._regions == [])
    sequence = canvas.timeline.to_sequence("odmr", validate=False)
    check(
        "the sequence says an instrument steps it",
        sequence.sweep.stepped and sequence.sweep.parameter == "frequency",
    )

    print("\n13e. Double-clicking a lane puts a pulse on it")
    lane_count = len(canvas.timeline.tracks)
    counts = [len(t.pulses) for t in canvas.timeline.tracks]
    added = canvas.add_pulse_at(lane_count - 1, canvas.timeline.end * 2)
    app.processEvents()
    now = [len(t.pulses) for t in canvas.timeline.tracks]
    check("it lands on the lane that was clicked", added and now[-1] == counts[-1] + 1)
    check("and on no other", now[:-1] == counts[:-1], f"{counts} -> {now}")
    check(
        "a pulse cannot be dropped on top of another",
        not canvas.add_pulse_at(
            lane_count - 1, canvas.timeline.tracks[-1].sorted()[0].start
        ),
    )

    print("\n13f. A rig can declare several channels of a kind")
    many = PulseEditorControlWidget(
        dict(DEFAULTS, CHANNELS=[
            {"name": "green", "kind": "laser"},
            {"name": "red", "kind": "laser"},
            {"name": "mw", "kind": "mw"},
            {"name": "mw2", "kind": "mw"},
            {"name": "apd_a", "kind": "gate"},
            {"name": "apd_b", "kind": "gate"},
            {"name": "trigger", "kind": "other"},
        ]),
        generators=sorted(GENERATORS),
    )
    app.processEvents()
    lanes = [_lane(label) for _, label in many.timeline._axis._tickLevels[0]]
    check(
        "a lane per declared channel, whatever the kinds",
        lanes == ["green", "red", "mw", "mw2", "apd_a", "apd_b", "trigger"],
        f"{lanes}",
    )
    marked = [
        _lane(label) for _, label in many.timeline._axis._tickLevels[0]
        if MEASURED in label
    ]
    check("the first gate is the measurement", marked == ["apd_a"], f"{marked}")

    def offered(canvas, channel: str) -> list:
        lane = canvas.timeline.channels.index(channel)
        canvas.add_pulse(channel)
        canvas._item_clicked(
            next(i for i in canvas._items if i.lane == lane)
        )
        app.processEvents()
        return [canvas.sweep_combo.itemData(i) for i in range(canvas.sweep_combo.count())]

    check(
        "both microwave lanes may sweep a carrier",
        offered(many.timeline, "mw2") == ["", DURATION, FREQUENCY],
    )
    check(
        "the second counter may not — a gate has none",
        offered(many.timeline, "apd_b") == ["", DURATION],
    )
    check(
        "nor may the second laser",
        offered(many.timeline, "red") == ["", DURATION],
    )
    check(
        "and neither may a trigger",
        offered(many.timeline, "trigger") == ["", DURATION],
    )

    print("\n13g. The channel table is what the rig tab edits")
    check(
        "one row per channel",
        many.channel_table.rowCount() == 7,
        f"{many.channel_table.rowCount()}",
    )
    reported: list = []
    many.sigParamChanged.connect(
        lambda name, value: reported.append((name, value))
    )
    many._add_channel_row("shutter", "other")
    app.processEvents()
    check(
        "adding one reports CHANNELS",
        reported and reported[-1][0] == "CHANNELS",
        f"{[n for n, _ in reported]}",
    )
    check(
        "with the kind it was given",
        reported[-1][1][-1] == {"name": "shutter", "kind": "other"},
        f"{reported[-1][1][-1]}",
    )
    check(
        "and the canvas grew a lane for it",
        "shutter" in many.timeline.timeline.channels,
        f"{many.timeline.timeline.channels}",
    )

    print("\n14. Filling from an experiment draws it, and editing survives")
    for name in sorted(GENERATORS):
        sequence = build(name, RigProfile(), points=6)
        fresh.load_timeline(timeline_from_sequence(sequence, [c["name"] for c in fresh.channels()]))
        app.processEvents()
        line = fresh.timeline.timeline
        rebuilt = line.to_sequence(
            name, alternating=sequence.alternating,
            gate_channel=sequence.gate_channel,
        )
        check(
            f"{name}: drawn and still playable",
            rebuilt.points == sequence.points
            and rebuilt.readouts() == sequence.readouts(),
            f"{rebuilt.points}/{sequence.points}, {rebuilt.readouts()}/{sequence.readouts()}",
        )

    print("\n15. What the dock emits is what a workflow stores")
    stored: list[tuple[str, object]] = []
    fresh.sigParamChanged.connect(lambda name, value: stored.append((name, value)))
    fresh.timeline.add_pulse("gate")
    app.processEvents()
    names = [name for name, _ in stored]
    check("the whole timeline is reported", "TIMELINE" in names, f"{names}")
    payload = dict(stored)["TIMELINE"]
    check(
        "as plain data that rebuilds",
        Timeline.from_dict(payload).channels == fresh.timeline.timeline.channels,
    )

    print("\n16. A hand-drawn timeline compiles without a generator anywhere")
    hand = PulseTimelineWidget(Timeline(), ["laser", "mw", "gate"])
    app.processEvents()
    for channel, start, stop in (
        ("mw", 0.0, 20 * NS), ("laser", 20 * NS, 3020 * NS), ("gate", 20 * NS, 3020 * NS)
    ):
        hand.add_pulse(channel)
        pulse = hand.timeline.track(channel).pulses[-1]
        hand._item_clicked(next(i for i in hand._items if i.pulse == pulse))
        hand.pulse_start.setValue(start)
        hand.pulse_length.setValue(stop - start)
        hand._edited()
    hand.timeline.duration = 4 * US
    mark = hand.timeline.track("mw").pulses[0]
    hand.timeline.track("mw").pulses[0] = replace(mark, sweep=DURATION)
    hand.timeline.sweep = SweepAxis(points=9, stop=180 * NS)
    sequence = hand.timeline.to_sequence("hand")
    check("it plays", sequence.readouts() == 9, f"{sequence.readouts()}")
    check("with the drawn sweep", close(sequence.sweep.values[0], 20 * NS))

    print("\n17. The timing diagram draws one lane per channel")
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

    print("\n18. An empty result leaves the view legible rather than blank")
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
