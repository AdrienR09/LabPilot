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
    FREQUENCY,
    LOG,
    TIME,
    Region,
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
    "LASER_CHANNEL": "laser",
    "MW_CHANNEL": "mw",
    "GATE_CHANNEL": "gate",
    "ANALOG_MW": True,
}


def rabi_timeline(points: int = 12) -> Timeline:
    return timeline_from_sequence(
        build("rabi", RigProfile(), points=points), ("laser", "mw", "gate")
    )


def main() -> int:
    from components.pulse_editor import PulseEditorControlWidget
    from components.pulse_timeline import PulseTimelineWidget
    from components.workflow_result import PulseSequenceResultView

    app = QApplication.instance() or QApplication([])

    print("1. The dock builds from parameters alone — no client, no schema")
    params = dict(DEFAULTS, TIMELINE=rabi_timeline().to_dict())
    dock = PulseEditorControlWidget(params, generators=sorted(GENERATORS))
    app.processEvents()
    check("it holds no client", not hasattr(dock, "client"))
    check("the sweep settings are the first tab", dock.tabs.tabText(0) == "Sweep")
    check("the rig profile is the second", dock.tabs.tabText(1) == "Rig")
    check(
        "there is no generator tab and no block table",
        dock.tabs.count() == 2,
        f"{[dock.tabs.tabText(i) for i in range(dock.tabs.count())]}",
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
        dict(DEFAULTS, GATE_CHANNEL=None), generators=sorted(GENERATORS)
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
    renamed = dict(DEFAULTS, GATE_CHANNEL="apd_gate", MW_CHANNEL="microwave")
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
    canvas.track_combo.setCurrentIndex(canvas.track_combo.findData("gate"))
    before = len(canvas.timeline.track("gate").pulses)
    canvas.add_pulse()
    app.processEvents()
    check("a pulse was added", len(canvas.timeline.track("gate").pulses) == before + 1)
    check("it went on the chosen track", canvas.track_combo.currentData() == "gate")

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
    canvas.track_combo.setCurrentIndex(canvas.track_combo.findData("gate"))
    canvas.add_pulse()
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

    print("\n11. The sweep is drawn across every lane")
    check("a region item per marked region", len(canvas._regions) == 1,
          f"{len(canvas._regions)}")
    canvas.add_sweep_region()
    app.processEvents()
    check("another can be added", len(canvas.timeline.sweep.regions) == 2)
    check("and it is drawn too", len(canvas._regions) == 2)

    print("\n12. Regions of one axis stay the same length")
    region = canvas._regions[0]
    region.setRegion((0.0, 500 * NS))
    region.sigRegionChangeFinished.emit(region)
    app.processEvents()
    lengths = [r.length for r in canvas.timeline.sweep.regions]
    check(
        "moving one edge resizes the others",
        max(lengths) - min(lengths) < 1e-15,
        f"{lengths}",
    )
    check("to the length that was dragged", close(lengths[0], 500 * NS),
          f"{lengths[0]}")

    print("\n13. The sweep panel and the canvas agree")
    fresh = PulseEditorControlWidget(
        dict(DEFAULTS, TIMELINE=rabi_timeline().to_dict()),
        generators=sorted(GENERATORS),
    )
    app.processEvents()
    fresh.sweep_points.setValue(31)
    app.processEvents()
    check("points reach the timeline", fresh.timeline.timeline.sweep.points == 31)
    fresh.spacing_combo.setCurrentIndex(fresh.spacing_combo.findData(LOG))
    app.processEvents()
    check("so does the spacing", fresh.timeline.timeline.sweep.spacing == LOG)
    check(
        "a constant step is hidden for a log sweep",
        not shown(fresh.sweep_step) and shown(fresh.sweep_stop),
    )
    fresh.timeline.clear_sweep()
    app.processEvents()
    check("and a sweep can be removed entirely", fresh.timeline.timeline.sweep is None)

    print("\n13b. Switching to a frequency sweep leaves the drawing alone")
    swept = PulseEditorControlWidget(
        dict(DEFAULTS, TIMELINE=rabi_timeline().to_dict()),
        generators=sorted(GENERATORS),
    )
    app.processEvents()
    before = [
        (p.start, p.stop) for track in swept.timeline.timeline.tracks
        for p in track.sorted()
    ]
    swept.quantity_combo.setCurrentIndex(swept.quantity_combo.findData(FREQUENCY))
    app.processEvents()
    axis = swept.timeline.timeline.sweep
    check("the axis becomes a frequency", axis is not None and axis.quantity == FREQUENCY)
    check("in hertz, not seconds", axis.unit == "Hz" and axis.name == "frequency")
    check("nothing is marked on the canvas", axis.regions == ())
    check(
        "and not one drawn pulse moved",
        before == [
            (p.start, p.stop) for track in swept.timeline.timeline.tracks
            for p in track.sorted()
        ],
    )
    check(
        "the region controls have nothing to do, so they are hidden",
        not shown(swept.region_buttons) and shown(swept.sweep_start),
    )
    sequence = swept.timeline.timeline.to_sequence("odmr", alternating=False)
    check(
        "the sequence says an instrument steps it",
        sequence.sweep.stepped and sequence.sweep.parameter == "frequency",
    )
    check(
        "one readout per pass, many points — and it validates",
        sequence.readouts() == 1 and sequence.points == axis.points,
        f"{sequence.readouts()} readout(s), {sequence.points} point(s)",
    )

    print("\n13c. Switching back restores a drawn sweep")
    swept.quantity_combo.setCurrentIndex(swept.quantity_combo.findData(TIME))
    app.processEvents()
    back = swept.timeline.timeline.sweep
    check("time again", back is not None and back.quantity == TIME and back.unit == "s")
    check("with a region to drag", len(back.regions) >= 1)
    check("and the region controls are back", shown(swept.region_buttons))

    print("\n13d. Double-clicking a lane puts a pulse on it")
    lane_count = len(swept.timeline.timeline.tracks)
    counts = [len(t.pulses) for t in swept.timeline.timeline.tracks]
    added = swept.timeline.add_pulse_at(lane_count - 1, swept.timeline.timeline.end * 2)
    app.processEvents()
    now = [len(t.pulses) for t in swept.timeline.timeline.tracks]
    check("it lands on the lane that was clicked", added and now[-1] == counts[-1] + 1)
    check("and on no other", now[:-1] == counts[:-1], f"{counts} -> {now}")
    check(
        "a pulse cannot be dropped on top of another",
        not swept.timeline.add_pulse_at(
            lane_count - 1, swept.timeline.timeline.tracks[-1].sorted()[0].start
        ),
    )

    print("\n14. Filling from an experiment draws it, and editing survives")
    for name in sorted(GENERATORS):
        sequence = build(name, RigProfile(), points=6)
        fresh.load_timeline(timeline_from_sequence(sequence, fresh.channels()))
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
    fresh.timeline.add_pulse()
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
        hand.track_combo.setCurrentIndex(hand.track_combo.findData(channel))
        hand.add_pulse()
        pulse = hand.timeline.track(channel).pulses[-1]
        hand._item_clicked(next(i for i in hand._items if i.pulse == pulse))
        hand.pulse_start.setValue(start)
        hand.pulse_length.setValue(stop - start)
        hand._edited()
    hand.timeline.duration = 4 * US
    hand.timeline.sweep = SweepAxis(
        regions=(Region(0.0, 20 * NS),), points=9, step=20 * NS
    )
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
