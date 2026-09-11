"""The pulse editor's canvas — one track per instrument, pulses drawn on it.

This is the editor. Not a table with a plot beside it: the timeline *is*
the editing surface. Each instrument gets a lane — laser, microwave, APD
readout, whatever the rig profile declares — and a pulse is a box on that
lane that can be dragged along it and resized by its edges.

## Why the drawing surface is the editor

A pulse sequence is a picture of time. Every paper draws one, every
oscilloscope shows one, and a person setting up a rig thinks "the gate
opens 300 ns after the laser" rather than "element 4 has gate=True". A
table of time slices is what the *pulser* needs, and converting between
the two is `core/pulse/tracks.py`'s whole job precisely so that nobody
editing has to do it in their head.

## What is drawn and what is typed

Dragging sets *when*: position and length, snapped to a grid so an edge
lands on a round number rather than 19.87 ns. Everything that is not a
time is typed, in the inspector under the canvas — a 2.87 GHz carrier is
not something to find by dragging, and neither is a channel name.

## The sweep is drawn too

A sweep region is a shaded span across every lane. Everything after it
shifts as it grows, which is what a swept sequence physically does. There
can be several — a Ramsey's tau appears once per alternating arm and a
Hahn echo's twice — and they move together because they are one axis.

A dumb view, the same convention `axes_control.py` follows: it holds no
client and makes no network call. It emits `sigTimelineChanged` with the
timeline as plain data, and `workflow_window.py` wires that to the PUT
that stores the parameter.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pyqtgraph as pg
from components.widgets import IconButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from labpilot.core.pulse.shapes import SHAPES
from labpilot.core.pulse.tracks import (
    FREQUENCY,
    LINEAR,
    TIME,
    Pulse,
    Region,
    SweepAxis,
    Timeline,
    Track,
    blank_pulse,
)

__all__ = ["PulseTimelineWidget"]

#: Lane colours. The laser gets green and the microwave red wherever
#: those channels are present, because that is what every optics bench and
#: every NV paper already uses; anything else cycles.
_BY_NAME: dict[str, str] = {
    "laser": "#4caf50", "green": "#4caf50",
    "mw": "#e53935", "microwave": "#e53935",
    "gate": "#42a5f5", "apd": "#42a5f5",
    "trigger": "#ffb300",
}
_CYCLE = ("#ab47bc", "#26a69a", "#ff7043", "#8d6e63", "#78909c")

_OFF = "digital"


def colour_for(channel: str, index: int) -> str:
    return _BY_NAME.get(channel, _CYCLE[index % len(_CYCLE)])


class PulseItem(pg.ROI):
    """One drawn pulse: draggable along its lane, resizable by both edges.

    Locked to its lane vertically. A pulse belongs to an instrument, and
    dragging one onto another instrument's track would be a different
    edit — moving a laser pulse onto the microwave line — which is not
    something a stray vertical wobble should be able to do by accident.
    """

    def __init__(self, pulse: Pulse, lane: int, colour: str, snap: float) -> None:
        super().__init__(
            pos=(pulse.start, lane - 0.35),
            size=(max(pulse.duration, snap), 0.7),
            pen=pg.mkPen(colour, width=2),
            movable=True,
            rotatable=False,
            resizable=True,
        )
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.addScaleHandle((0, 0.5), (1, 0.5))
        self.addScaleHandle((1, 0.5), (0, 0.5))
        self.lane = lane
        self.pulse = pulse
        self.snap = snap
        self.brush = pg.mkBrush(pg.mkColor(colour).darker(160))

    def paint(self, painter: Any, *_args: Any) -> None:
        """A filled box, not an outline.

        `pg.ROI` draws its outline only, and an outline reads as a
        selection marquee rather than as a pulse — which is the wrong
        thing entirely on a timeline whose whole subject is when a channel
        is *on*.
        """
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPainter

        rect = QRectF(0, 0, self.state["size"][0], self.state["size"][1]).normalized()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, self._antialias)
        painter.setPen(self.currentPen)
        painter.setBrush(self.brush)
        painter.translate(rect.left(), rect.top())
        painter.scale(rect.width(), rect.height())
        painter.drawRect(0, 0, 1, 1)

    def bounds(self) -> tuple[float, float]:
        """Where this item now sits, snapped to the grid and never
        negative — a pulse dragged left off the canvas becomes one that
        starts at zero, not one the model refuses to build."""
        start = _snap(float(self.pos().x()), self.snap)
        length = _snap(float(self.size().x()), self.snap)
        start = max(start, 0.0)
        return start, start + max(length, self.snap)

    def relock(self) -> None:
        """Put the item back in its own lane after a drag."""
        position = self.pos()
        if abs(position.y() - (self.lane - 0.35)) > 1e-9:
            self.setPos(position.x(), self.lane - 0.35, update=False, finish=False)


def _snap(value: float, grid: float) -> float:
    return round(value / grid) * grid if grid > 0 else value


def _renamed(name: str | None, default_for: str, replacement: str) -> str:
    """`replacement` when the axis still carries the other quantity's
    default name, and `name` untouched when someone has named it
    themselves — so switching quantity does not throw away "detuning"."""
    return replacement if name in (None, "", default_for) else str(name)


class PulseTimelineWidget(QWidget):
    """The editor canvas plus its inspector."""

    sigTimelineChanged = pyqtSignal(object)
    """The whole timeline as plain data, after any edit."""
    sigSelectionChanged = pyqtSignal(object)

    #: Grid steps offered for snapping, in seconds.
    SNAPS: ClassVar[tuple[float, ...]] = (1e-9, 5e-9, 10e-9, 50e-9, 100e-9, 1e-6)

    def __init__(
        self,
        timeline: Timeline | None = None,
        channels: list[str] | None = None,
        readout: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.timeline = timeline or Timeline()
        self._channels = list(channels or [])
        self._readout = readout
        self._snap = 10e-9
        self._items: list[PulseItem] = []
        self._regions: list[pg.LinearRegionItem] = []
        self._selected: PulseItem | None = None
        self._silent = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(self._toolbar())
        layout.addWidget(self._canvas(), 3)
        layout.addWidget(self._inspector())
        # Through `set_channels` rather than straight to `rebuild`, so a
        # declared channel with nothing drawn on it still gets a lane —
        # otherwise a new sequence opens with nowhere to put the laser.
        self.set_channels(self._channels or self.timeline.channels)

    # --- Chrome -----------------------------------------------------------

    def _toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)

        self.track_combo = QComboBox()
        row.addWidget(QLabel("Track"))
        row.addWidget(self.track_combo)

        add = IconButton("Add pulse", "list-add")
        add.clicked.connect(self.add_pulse)
        row.addWidget(add)

        remove = IconButton("Delete", "list-remove")
        remove.clicked.connect(self.remove_selected)
        row.addWidget(remove)

        row.addSpacing(12)
        row.addWidget(QLabel("Snap"))
        self.snap_combo = QComboBox()
        for step in self.SNAPS:
            self.snap_combo.addItem(pg.siFormat(step, suffix="s"), step)
        self.snap_combo.setCurrentIndex(self.SNAPS.index(self._snap))
        self.snap_combo.currentIndexChanged.connect(self._snap_changed)
        self.snap_combo.setToolTip(
            "Dragged edges land on this grid, so a pulse is 20 ns rather "
            "than 19.87 ns."
        )
        row.addWidget(self.snap_combo)

        row.addSpacing(12)
        row.addWidget(QLabel("Length"))
        self.duration = pg.SpinBox(
            value=self.timeline.duration, bounds=(0.0, None), suffix="s",
            siPrefix=True, step=100e-9, dec=True, minStep=1e-12,
        )
        self.duration.setToolTip(
            "The timeline's own end. Longer than the last pulse is normal "
            "and load-bearing: the repolarisation wait is silence, and "
            "silence has no edges to find."
        )
        self.duration.sigValueChanged.connect(self._duration_changed)
        row.addWidget(self.duration)
        row.addStretch(1)
        return bar

    def _canvas(self) -> QWidget:
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.showGrid(x=True, y=False, alpha=0.25)
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.getPlotItem().hideButtons()
        self.plot.setMenuEnabled(False)
        self._axis = self.plot.getAxis("left")
        # Double-click a lane to put a pulse there. The toolbar's Add
        # button drops one after whatever is on the *selected* track,
        # which is the right gesture when the track is chosen from a list
        # and the wrong one when a full-window canvas is showing you the
        # track and the moment you want at the same time.
        self.plot.scene().sigMouseClicked.connect(self._canvas_clicked)
        return self.plot

    def _inspector(self) -> QWidget:
        box = QGroupBox("Selected pulse")
        form = QFormLayout(box)

        self.pulse_name = QLineEdit()
        self.pulse_name.setPlaceholderText("pi/2, readout, ...")
        self.pulse_name.editingFinished.connect(self._edited)
        form.addRow("Name", self.pulse_name)

        times = QWidget()
        row = QHBoxLayout(times)
        row.setContentsMargins(0, 0, 0, 0)
        self.pulse_start = self._time_box()
        self.pulse_length = self._time_box()
        row.addWidget(QLabel("start"))
        row.addWidget(self.pulse_start)
        row.addWidget(QLabel("length"))
        row.addWidget(self.pulse_length)
        form.addRow("Time", times)

        self.shape_combo = QComboBox()
        self.shape_combo.addItem(_OFF, "")
        for name in sorted(SHAPES):
            self.shape_combo.addItem(name, name)
        self.shape_combo.setToolTip(
            "A digital pulse is a level; a shape makes this an analog "
            "waveform with its own parameters."
        )
        self.shape_combo.currentIndexChanged.connect(self._shape_changed)
        form.addRow("Shape", self.shape_combo)

        self.shape_form = QWidget()
        self.shape_layout = QFormLayout(self.shape_form)
        self.shape_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.shape_form)

        self.hint = QLabel("Nothing selected — click a pulse, or add one.")
        self.hint.setStyleSheet("color: #888;")
        form.addRow(self.hint)

        box.setEnabled(True)
        self._inspector_box = box
        return box

    def _time_box(self) -> pg.SpinBox:
        box = pg.SpinBox(
            value=0.0, bounds=(0.0, None), suffix="s", siPrefix=True,
            step=self._snap, dec=True, minStep=1e-12,
        )
        box.sigValueChanged.connect(lambda _: self._edited())
        return box

    # --- Building the canvas ----------------------------------------------

    def set_readout(self, channel: str) -> None:
        """Which lane is the measurement — the gate, or the laser on a rig
        with no gate. Marked on the canvas rather than left to be inferred
        from the channel's name: which readouts a run records, how many
        gates the counter is armed for and what a point *is* all come from
        this one track, and on an ungated rig it is the laser lane, which
        nothing about the word "laser" would tell you."""
        self._readout = channel
        self.rebuild()

    def set_channels(self, channels: list[str]) -> None:
        """The rig's declared channels — one lane each, whether or not
        anything is drawn on them yet."""
        self._channels = list(channels)
        existing = {track.channel for track in self.timeline.tracks}
        for channel in self._channels:
            if channel not in existing:
                self.timeline.tracks.append(Track(channel))
        self.timeline.tracks = [
            track for track in self.timeline.tracks
            if track.channel in set(self._channels) or track.pulses
        ]
        self.rebuild()

    def set_timeline(self, timeline: Timeline) -> None:
        self.timeline = timeline
        self.set_channels(self._channels or timeline.channels)

    def rebuild(self) -> None:
        """Redraw every lane from the timeline. Called after any change
        that moves more than one item — loading, adding, deleting — since
        the lanes themselves may have changed."""
        self.plot.clear()
        self._items = []
        self._regions = []
        self._selected = None

        tracks = self.timeline.tracks
        labels = [self._lane_label(track) for track in tracks]
        self._axis.setTicks([list(enumerate(labels))])
        # Widened by hand: `pg.AxisItem` drops a tick label that does not
        # fit the space it allocated, silently, so the measurement lane —
        # the one lane with a longer label than the rest — was the one
        # that ended up with no name on it at all.
        metrics = QFontMetrics(self._axis.font())
        self._axis.setWidth(
            max((metrics.horizontalAdvance(label) for label in labels), default=40) + 16
        )
        self.plot.setYRange(-0.8, max(len(tracks) - 0.2, 0.8))

        for index, track in enumerate(tracks):
            colour = colour_for(track.channel, index)
            self.plot.addItem(
                pg.InfiniteLine(pos=index, angle=0, pen=pg.mkPen("#3a3a3a", width=1))
            )
            for pulse in track.sorted():
                item = PulseItem(pulse, index, colour, self._snap)
                item.sigRegionChangeFinished.connect(self._item_moved)
                item.sigClicked.connect(self._item_clicked)
                self.plot.addItem(item)
                self._items.append(item)

        self._draw_sweep()
        end = self.timeline.end or 1e-6
        self.plot.setXRange(-0.02 * end, end * 1.02)
        self._refresh_tracks_combo()
        self._show_selection()

    def _draw_sweep(self) -> None:
        sweep = self.timeline.sweep
        if sweep is None:
            return
        for number, region in enumerate(sweep.regions):
            item = pg.LinearRegionItem(
                values=(region.start, region.stop),
                brush=pg.mkBrush(255, 193, 7, 45),
                pen=pg.mkPen("#ffb300", width=1),
                movable=True,
            )
            item.setZValue(-10)
            item.region_index = number
            item.sigRegionChangeFinished.connect(self._region_moved)
            self.plot.addItem(item)
            self._regions.append(item)

    def _lane_label(self, track: Track) -> str:
        """One line, not two: `pg.AxisItem` renders a tick label as a
        single line and a newline in one silently loses the whole label,
        which is how the measurement lane ended up with no name at all."""
        name = track.label or track.channel
        return f"{name} ⟵ measured" if track.channel == self._readout else name

    def _refresh_tracks_combo(self) -> None:
        current = self.track_combo.currentData()
        self.track_combo.blockSignals(True)
        self.track_combo.clear()
        for track in self.timeline.tracks:
            label = track.label or track.channel
            if track.channel == self._readout:
                label = f"{label} (measurement)"
            self.track_combo.addItem(label, track.channel)
        index = self.track_combo.findData(current)
        self.track_combo.setCurrentIndex(max(index, 0))
        self.track_combo.blockSignals(False)

    # --- Edits -------------------------------------------------------------

    def add_pulse(self) -> None:
        """A new pulse on the selected track, after whatever is there."""
        channel = self.track_combo.currentData()
        if channel is None:
            return
        track = self.timeline.track(channel)
        start = _snap(track.end or 0.0, self._snap)
        track.pulses.append(blank_pulse(start, max(self._snap * 10, 100e-9)))
        self._changed()

    def add_pulse_at(self, lane: int, start: float) -> bool:
        """A new pulse on lane `lane`, beginning at `start`.

        Returns False without changing anything when that would overlap a
        pulse already on the lane — a channel has one level at a time, so
        the sequence would be refused at save time, and refusing the
        gesture instead is the version that says so immediately.
        """
        if not 0 <= lane < len(self.timeline.tracks):
            return False
        track = self.timeline.tracks[lane]
        start = max(_snap(start, self._snap), 0.0)
        length = max(self._snap * 10, 100e-9)
        if any(
            pulse.start < start + length and start < pulse.stop
            for pulse in track.pulses
        ):
            return False
        track.pulses.append(blank_pulse(start, length))
        self._changed()
        self._reselect(track.pulses[-1])
        return True

    def _canvas_clicked(self, event: Any) -> None:
        """Double-click on empty canvas: add a pulse on the lane clicked.

        Single clicks are left entirely alone — pulses handle their own,
        and a region drag must not turn into a stray pulse.
        """
        if not event.double() or not self.timeline.tracks:
            return
        point = self.plot.getPlotItem().vb.mapSceneToView(event.scenePos())
        lane = round(float(point.y()))
        if self.add_pulse_at(lane, float(point.x())):
            event.accept()

    def remove_selected(self) -> None:
        if self._selected is None:
            return
        track = self.timeline.tracks[self._selected.lane]
        if self._selected.pulse in track.pulses:
            track.pulses.remove(self._selected.pulse)
        self._changed()

    def add_sweep_region(self) -> None:
        """Mark another interval that grows with the same axis.

        A Ramsey's tau appears once per alternating arm; marking the
        second is how the editor says the two grow together rather than
        being two sweeps kept in step by hand.
        """
        sweep = self.timeline.sweep
        if sweep is not None and sweep.stepped:
            return
        end = self.timeline.end or 1e-6
        length = sweep.length if sweep else max(self._snap * 2, 20e-9)
        start = _snap(end * 0.5, self._snap)
        regions = (*(sweep.regions if sweep else ()), Region(start, start + length))
        self.timeline.sweep = SweepAxis(
            regions=regions,
            points=sweep.points if sweep else 50,
            step=sweep.step if sweep else 20e-9,
            stop_value=sweep.stop_value if sweep else 0.0,
            spacing=sweep.spacing if sweep else LINEAR,
            name=sweep.name if sweep else "tau",
            quantity=TIME,
        )
        self._changed()

    def clear_sweep(self) -> None:
        self.timeline.sweep = None
        self._changed()

    def set_sweep_quantity(self, quantity: str | None) -> None:
        """Switch what this sequence sweeps — nothing, a drawn time, or
        the microwave frequency.

        The two sweeps are different enough to need this: a time sweep
        lives on the canvas as marked regions the pulser stretches, and a
        frequency sweep has nothing to mark because the drawn pattern
        never changes. Everything else about the sequence is identical,
        which is why this is one control rather than a second editor.
        """
        current = self.timeline.sweep.to_dict() if self.timeline.sweep else {}
        if quantity is None:
            self.timeline.sweep = None
        elif quantity == FREQUENCY:
            # A name and a unit carried over from a time sweep would label
            # a gigahertz axis "tau" in seconds, and its endpoints would be
            # nanoseconds — hence the rig defaults, and the `> 1e6` test,
            # which asks whether the stored endpoint is already a frequency.
            self.timeline.sweep = SweepAxis.from_dict({
                **current,
                "quantity": FREQUENCY,
                "regions": [],
                "name": _renamed(current.get("name"), "tau", FREQUENCY),
                "unit": "Hz",
                "start_value": current.get("start_value") or 2.82e9,
                "stop_value": (
                    current["stop_value"]
                    if current.get("stop_value", 0.0) > 1e6 else 2.92e9
                ),
            })
        else:
            end = self.timeline.end or 1e-6
            start = _snap(end * 0.5, self._snap)
            regions = current.get("regions") or [
                {"start": start, "stop": start + max(self._snap * 2, 20e-9)}
            ]
            self.timeline.sweep = SweepAxis.from_dict({
                **current,
                "quantity": TIME,
                "regions": regions,
                "name": _renamed(current.get("name"), FREQUENCY, "tau"),
                "unit": "s",
                "stop_value": (
                    0.0 if current.get("stop_value", 0.0) > 1e6
                    else current.get("stop_value", 0.0)
                ),
            })
        self._changed()

    def set_sweep(self, **fields: Any) -> None:
        """Replace the sweep axis's settings, keeping its regions."""
        sweep = self.timeline.sweep
        if sweep is None:
            return
        current = sweep.to_dict()
        current.update(fields)
        self.timeline.sweep = SweepAxis.from_dict(current)
        self._changed()

    def _snap_changed(self) -> None:
        self._snap = float(self.snap_combo.currentData())
        self.rebuild()

    def _duration_changed(self, box: pg.SpinBox) -> None:
        self.timeline.duration = float(box.value())
        self._changed(rebuild=False)

    def _item_moved(self, item: PulseItem) -> None:
        item.relock()
        start, stop = item.bounds()
        track = self.timeline.tracks[item.lane]
        if item.pulse in track.pulses:
            position = track.pulses.index(item.pulse)
            track.pulses[position] = item.pulse.moved(start, stop)
            item.pulse = track.pulses[position]
        self._changed()

    def _item_clicked(self, item: PulseItem, _event: Any = None) -> None:
        self._selected = item
        self._show_selection()
        self.sigSelectionChanged.emit(item.pulse)

    def _region_moved(self, item: pg.LinearRegionItem) -> None:
        sweep = self.timeline.sweep
        if sweep is None:
            return
        start, stop = (_snap(v, self._snap) for v in item.getRegion())
        if stop <= start:
            stop = start + self._snap
        regions = list(sweep.regions)
        regions[item.region_index] = Region(start, stop)
        # Every region takes the same value each point, so moving one edge
        # resizes the others rather than producing an axis that sweeps two
        # different things under one name.
        length = stop - start
        regions = [
            region if index == item.region_index else Region(region.start, region.start + length)
            for index, region in enumerate(regions)
        ]
        self.timeline.sweep = SweepAxis.from_dict(
            {**sweep.to_dict(), "regions": [r.to_dict() for r in regions]}
        )
        self._changed()

    def _edited(self) -> None:
        """The inspector changed something about the selected pulse."""
        if self._silent or self._selected is None:
            return
        track = self.timeline.tracks[self._selected.lane]
        if self._selected.pulse not in track.pulses:
            return
        start = float(self.pulse_start.value())
        length = max(float(self.pulse_length.value()), 0.0)
        position = track.pulses.index(self._selected.pulse)
        track.pulses[position] = Pulse(
            start, start + length, self._selected.pulse.value, self.pulse_name.text()
        )
        self._changed()

    def _shape_changed(self) -> None:
        if self._silent or self._selected is None:
            return
        name = self.shape_combo.currentData() or ""
        track = self.timeline.tracks[self._selected.lane]
        if self._selected.pulse not in track.pulses:
            return
        position = track.pulses.index(self._selected.pulse)
        current = track.pulses[position]
        # A shape's parameters belong to the shape: a Gauss inheriting a
        # Chirp's start_frequency would be a silent wrong answer.
        value = SHAPES[name]() if name else True
        track.pulses[position] = Pulse(current.start, current.stop, value, current.name)
        self._changed()

    def _shape_param_changed(self, parameter: str, value: float) -> None:
        if self._selected is None:
            return
        track = self.timeline.tracks[self._selected.lane]
        if self._selected.pulse not in track.pulses:
            return
        position = track.pulses.index(self._selected.pulse)
        current = track.pulses[position]
        if not current.analog:
            return
        shape = type(current.value)
        fields = {p.name: getattr(current.value, p.name) for p in shape.params}
        fields[parameter] = float(value)
        track.pulses[position] = Pulse(
            current.start, current.stop, shape(**fields), current.name
        )
        self._changed(rebuild=False)

    # --- Selection ---------------------------------------------------------

    def _show_selection(self) -> None:
        pulse = self._selected.pulse if self._selected else None
        self._silent = True
        try:
            for widget in (self.pulse_name, self.pulse_start, self.pulse_length,
                           self.shape_combo):
                widget.setEnabled(pulse is not None)
            self.hint.setVisible(pulse is None)
            if pulse is None:
                self.pulse_name.setText("")
                self._build_shape_form(None)
                return
            self.pulse_name.setText(pulse.name)
            self.pulse_start.setValue(pulse.start)
            self.pulse_length.setValue(pulse.duration)
            shape = type(pulse.value).__name__ if pulse.analog else ""
            self.shape_combo.setCurrentIndex(max(self.shape_combo.findData(shape), 0))
            self._build_shape_form(pulse)
        finally:
            self._silent = False

    def _build_shape_form(self, pulse: Pulse | None) -> None:
        """One row per parameter the selected shape declares.

        From the shape's own `Parameter` objects, so a unit and a limit
        are stated rather than guessed from the parameter's name — and a
        shape added to `core/pulse/shapes.py` gets an editor here with no
        change to this file.
        """
        while self.shape_layout.count():
            item = self.shape_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if pulse is None or not pulse.analog:
            return

        for parameter in type(pulse.value).params:
            box = pg.SpinBox(
                value=float(getattr(pulse.value, parameter.name)),
                suffix=parameter.unit or None,
                siPrefix=bool(parameter.unit),
                dec=True, minStep=1e-12,
            )
            box.sigValueChanged.connect(
                lambda widget, name=parameter.name: self._shape_param_changed(
                    name, float(widget.value())
                )
            )
            label = parameter.name.replace("_", " ")
            self.shape_layout.addRow(label, box)

    # --- Reporting ---------------------------------------------------------

    def _changed(self, rebuild: bool = True) -> None:
        if rebuild:
            keep = self._selected.pulse if self._selected else None
            self.rebuild()
            if keep is not None:
                self._reselect(keep)
        self.sigTimelineChanged.emit(self.timeline.to_dict())

    def _reselect(self, pulse: Pulse) -> None:
        for item in self._items:
            if item.pulse == pulse:
                self._selected = item
                self._show_selection()
                return


