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
lands on a round number rather than 19.87 ns. Double-clicking an empty
stretch of a lane adds a pulse there. Everything that is not a time is
typed — a 2.87 GHz carrier is not something to find by dragging.

The typing happens in `self.inspector`, which this widget **builds but
does not place**: it is a per-pulse settings form, it belongs with the
other settings, and stacking it under the canvas cost the canvas half its
height for rows that are blank until something is selected. The editor
puts it in its own column (`pulse_editor.py`).

## Everything about a pulse is on the pulse

Its name, its shape, whether it drives its channel at all, and whether
the measurement sweeps it. That last one used to be a separate mechanism
— shaded regions floated over the drawing and dragged into place — and
the whole of it collapses into one field on the object you already have
selected. A swept pulse is outlined in amber and its span shaded across
every lane, because what it is about to do is push everything after it
along, and that is the one thing a still picture cannot show.

A dumb view, the same convention `axes_control.py` follows: it holds no
client and makes no network call. It emits `sigTimelineChanged` with the
timeline as plain data, and `workflow_window.py` wires that to the PUT
that stores the parameter.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, ClassVar

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labpilot.core.pulse.library import GATE, LASER, MW
from labpilot.core.pulse.shapes import SHAPES
from labpilot.core.pulse.tracks import (
    DURATION,
    FREQUENCY,
    LINEAR,
    LOG,
    Pulse,
    SweepAxis,
    Timeline,
    Track,
    blank_pulse,
)
from labpilot.ui.desktop.components.widgets import IconButton

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

    #: Drawn on a swept pulse, in the amber the old sweep regions used.
    SWEPT = "#ffb300"

    def __init__(self, pulse: Pulse, lane: int, colour: str, snap: float) -> None:
        super().__init__(
            pos=(pulse.start, lane - 0.35),
            size=(max(pulse.duration, snap), 0.7),
            # A swept pulse is outlined in amber, because what it is about
            # to do — grow, and push everything after it along — is the
            # one thing about a drawing that a still picture cannot show.
            pen=pg.mkPen(
                self.SWEPT if pulse.sweep else colour,
                width=3 if pulse.sweep else 2,
                style=Qt.PenStyle.DashLine if pulse.sweep else Qt.PenStyle.SolidLine,
            ),
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
        # A timing block asserts nothing, so it is drawn hollow: on the
        # readout lane that is the difference between a gate the counter
        # opens for and a delay it does not, and reading it off the canvas
        # beats clicking each one to find out.
        self.brush = (
            pg.mkBrush(pg.mkColor(colour).darker(160)) if pulse.drives
            else pg.mkBrush(pg.mkColor(colour).darker(300))
        )

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


def _sized(box: pg.SpinBox) -> pg.SpinBox:
    """Give a `pg.SpinBox` the height it actually needs.

    Its `sizeHint()` is zero high, so a form layout hands it whatever is
    left over and the text ends up clipped between the rows either side.
    Every spin box in this file goes through this.
    """
    box.setMinimumHeight(box.minimumSizeHint().height())
    return box


def _pair(left: QWidget, right: QWidget) -> QWidget:
    """Two controls on one form row, for the ones that are read together."""
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(left, 1)
    row.addWidget(right, 1)
    return holder


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
        kinds: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.timeline = timeline or Timeline()
        self._channels = list(channels or [])
        self._readout = readout
        #: Lane name -> what it is for. A rig may have two microwave lines
        #: and two counters, so what a lane can do is read off its *kind*
        #: rather than off its name or its position.
        self._kinds = dict(kinds or {})
        self._snap = 10e-9
        self._items: list[PulseItem] = []
        self._regions: list[pg.LinearRegionItem] = []
        self._selected: PulseItem | None = None
        self._silent = False
        #: Lanes the last rebuild drew. The y-range is only reset when this
        #: changes, so adding a channel reframes and moving a pulse does not.
        self._lanes_drawn = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(self._toolbar())
        layout.addWidget(self._canvas(), 1)
        # The inspector is built but deliberately *not* placed here. It is
        # a per-pulse settings form, it belongs with the other settings,
        # and stacking it under the canvas cost the canvas half its height
        # for rows that are blank until something is selected. The editor
        # puts it in its own column — see pulse_editor.py.
        self.inspector = self._inspector()
        # Through `set_channels` rather than straight to `rebuild`, so a
        # declared channel with nothing drawn on it still gets a lane —
        # otherwise a new sequence opens with nowhere to put the laser.
        self.set_channels(self._channels or self.timeline.channels)
        self.fit_view()

    # --- Chrome -----------------------------------------------------------

    def _toolbar(self) -> QWidget:
        """Only what acts on the canvas as a whole.

        No track picker and no Add button: a pulse is added by
        double-clicking the lane and the moment you want it, which needs
        neither — and picking a track from a list, on a canvas that is
        already showing you the tracks, was the slower way to say the
        same thing.
        """
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)

        hint = QLabel("Double-click a lane to add a pulse")
        hint.setStyleSheet("color: #888;")
        row.addWidget(hint)

        remove = IconButton("Delete", "list-remove")
        remove.setToolTip("Remove the selected pulse.")
        remove.clicked.connect(self.remove_selected)
        row.addWidget(remove)

        fit = IconButton("Fit", "zoom-fit-best")
        fit.setToolTip(
            "Frame the whole sequence. Editing never reframes on its own: "
            "you zoom in to place an edge, and rescaling under the cursor "
            "would throw that away."
        )
        fit.clicked.connect(lambda _checked=False: self.fit_view())
        row.addWidget(fit)

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
        self.duration = _sized(pg.SpinBox(
            value=self.timeline.duration, bounds=(0.0, None), suffix="s",
            siPrefix=True, step=100e-9, dec=True, minStep=1e-12,
        ))
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
        # A plain widget, not a group box: it lives in a tab already
        # labelled "Pulse", and a frame titled "Selected pulse" inside one
        # titled "Pulse" is a box drawn around a box.
        box = QWidget()
        form = QFormLayout(box)
        form.setContentsMargins(8, 8, 8, 8)

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

        self.drives_check = QCheckBox("")
        self.drives_check.toggled.connect(self._drives_changed)
        form.addRow("Output", self.drives_check)

        self.sweep_combo = QComboBox()
        self.sweep_combo.setToolTip(
            "What this pulse contributes to the measurement's x-axis.\n\n"
            "Its length: the pulse grows point by point and everything "
            "after it shifts — a Rabi's drive, a Ramsey's free evolution, "
            "a gate held open longer. Any drawn interval has a length, so "
            "this is offered on every pulse.\n\n"
            "The MW frequency: the drawing never changes and the bound "
            "microwave source steps between passes — a pulsed ODMR. Only a "
            "microwave pulse can carry it, because only a drive has a "
            "carrier; a laser line and a counter gate are on/off.\n\n"
            "Mark several pulses to sweep them together — a Ramsey's tau "
            "appears once per arm and they are one axis."
        )
        self.sweep_combo.currentIndexChanged.connect(self._sweep_changed)
        form.addRow("Sweep", self.sweep_combo)

        self.axis_form = QWidget()
        self.axis_layout = QFormLayout(self.axis_form)
        self.axis_layout.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.axis_form)
        self._build_axis_form()

        self.hint = QLabel("Nothing selected — click a pulse, or add one.")
        self.hint.setStyleSheet("color: #888;")
        self.hint.setWordWrap(True)
        form.addRow(self.hint)

        return box

    def _build_axis_form(self) -> None:
        """Where the shared axis is edited: from the pulse you marked.

        The values live on the timeline, not on this pulse, because every
        marked pulse follows the same axis — so typing a point count here
        changes it for all of them, which is what the label says.

        Paired onto two rows rather than five: from/to are read together
        and so are points/spacing, and a settings column is short.
        """
        self.axis_start = self._value_box()
        self.axis_stop = self._value_box()
        self.axis_layout.addRow("From / to", _pair(self.axis_start, self.axis_stop))

        self.axis_points = QSpinBox()
        self.axis_points.setRange(1, 1_000_000)
        self.axis_points.setValue(50)
        self.axis_points.valueChanged.connect(lambda _: self._axis_edited())

        self.axis_spacing = QComboBox()
        self.axis_spacing.addItem("Linear", LINEAR)
        self.axis_spacing.addItem("Logarithmic", LOG)
        self.axis_spacing.setToolTip(
            "A T1 decay spans decades, so linear spacing wastes almost "
            "every point. Log spacing becomes one block per point, since "
            "no constant increment produces a geometric series."
        )
        self.axis_spacing.currentIndexChanged.connect(lambda _: self._axis_edited())
        self.axis_layout.addRow(
            "Points", _pair(self.axis_points, self.axis_spacing)
        )

        self.axis_name = QLineEdit()
        self.axis_name.setPlaceholderText("tau")
        self.axis_name.setToolTip("What the measurement's x-axis is called.")
        self.axis_name.editingFinished.connect(self._axis_edited)
        self.axis_layout.addRow("Axis name", self.axis_name)

    def _value_box(self) -> pg.SpinBox:
        box = _sized(pg.SpinBox(value=0.0, bounds=(0.0, None), siPrefix=True,
                                dec=True, minStep=1e-12))
        box.sigValueChanged.connect(lambda _: self._axis_edited())
        return box

    def _time_box(self) -> pg.SpinBox:
        box = _sized(pg.SpinBox(
            value=0.0, bounds=(0.0, None), suffix="s", siPrefix=True,
            step=self._snap, dec=True, minStep=1e-12,
        ))
        box.sigValueChanged.connect(lambda _: self._edited())
        return box

    # --- Building the canvas ----------------------------------------------

    def set_kinds(self, kinds: dict[str, str]) -> None:
        """What each lane is for.

        Decides two things the canvas shows: which lane is marked as the
        measurement, and which pulses are offered a frequency sweep. A rig
        with two microwave lines gets it on both; one that calls its
        counter `apd_b` still does not, because a gate has no carrier.
        """
        self._kinds = dict(kinds)
        readout = next(
            (name for name, kind in self._kinds.items() if kind == GATE),
            next((name for name, kind in self._kinds.items() if kind == LASER), ""),
        )
        self.set_readout(readout)

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
        """A different sequence entirely — so the view reframes, which an
        ordinary edit deliberately does not."""
        self.timeline = timeline
        self.set_channels(self._channels or timeline.channels)
        self.fit_view()

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
        if len(tracks) != self._lanes_drawn:
            self.plot.setYRange(-0.8, max(len(tracks) - 0.2, 0.8))
            self._lanes_drawn = len(tracks)

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
        self._show_selection()

    def fit_view(self) -> None:
        """Frame the whole sequence.

        Called when a *new* sequence arrives, and from the Fit button —
        never on an ordinary edit. Re-framing on every edit meant that
        nudging one pulse rescaled the canvas under the cursor, which is
        the opposite of what dragging something is supposed to do: you
        zoom in to place an edge precisely, and the zoom is exactly what
        gets thrown away.
        """
        end = self.timeline.end or 1e-6
        self.plot.setXRange(-0.02 * end, end * 1.02)
        self.plot.setYRange(-0.8, max(len(self.timeline.tracks) - 0.2, 0.8))
        self._lanes_drawn = len(self.timeline.tracks)

    def _draw_sweep(self) -> None:
        """Shade each swept pulse's span across every lane.

        Not a control any more — the pulse itself is the control now — but
        still worth drawing: what a swept pulse does is push everything
        after it along, and a band down the whole canvas is what says the
        rest of the sequence moves with it.
        """
        for pulse in self.timeline.swept:
            if pulse.sweep != DURATION:
                continue
            item = pg.LinearRegionItem(
                values=(pulse.start, pulse.stop),
                brush=pg.mkBrush(255, 193, 7, 35),
                pen=pg.mkPen(None),
                movable=False,
            )
            item.setZValue(-10)
            self.plot.addItem(item)
            self._regions.append(item)

    def _lane_label(self, track: Track) -> str:
        """One line, not two: `pg.AxisItem` renders a tick label as a
        single line and a newline in one silently loses the whole label,
        which is how the measurement lane ended up with no name at all."""
        name = track.label or track.channel
        return f"{name} ⟵ measured" if track.channel == self._readout else name

    # --- Edits -------------------------------------------------------------

    def add_pulse(self, channel: str) -> bool:
        """A new pulse on `channel`, after whatever is already there.

        The scripted form of the double-click. Kept because a test and a
        console session need a way in that is not a mouse event, not
        because the dock offers a button for it.
        """
        track = self.timeline.track(channel)
        return self.add_pulse_at(
            self.timeline.channels.index(channel), _snap(track.end or 0.0, self._snap)
        )

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

    def set_sweep(self, **fields: Any) -> None:
        """Change the shared axis every marked pulse follows."""
        current = (self.timeline.sweep or SweepAxis()).to_dict()
        current.update(fields)
        self.timeline.sweep = SweepAxis.from_dict(current)
        self._changed()

    def sweep_selected(self, quantity: str) -> None:
        """Mark or unmark the selected pulse as swept.

        Switching quantity clears the other kind from every *other* pulse
        as well: a measurement has one x-axis, so a drawing with one pulse
        sweeping its length and another sweeping the frequency describes
        nothing. Refusing it at save time and leaving it on screen would
        be the worse half of that trade.
        """
        if self._selected is None:
            return
        chosen = self._selected.pulse
        track = self.timeline.tracks[self._selected.lane]
        if chosen not in track.pulses:
            return

        # Marked first, and by identity: clearing the others beforehand
        # replaced the selected pulse too when it was the one changing
        # quantity, and the mark then landed on an object no longer in
        # the track.
        self._update_selected(sweep=quantity)
        if quantity:
            length = self._selected.pulse.duration
            for other in self.timeline.tracks:
                for index, pulse in enumerate(other.pulses):
                    if pulse is self._selected.pulse or not pulse.sweep:
                        continue
                    if pulse.sweep != quantity:
                        other.pulses[index] = replace(pulse, sweep="")
                    elif quantity == DURATION:
                        # Siblings on one axis take the same value at each
                        # point, so a newly marked pulse joins at the
                        # length the axis already has rather than being
                        # refused at save time.
                        length = pulse.duration
            if quantity == DURATION:
                self._match_swept_lengths(length)
        self._seed_axis(quantity)
        self._changed()

    def _seed_axis(self, quantity: str) -> None:
        """Give a freshly marked axis endpoints worth showing.

        A duration sweep's first value is the pulse someone drew, so only
        the far end needs a guess — ten times the length, which is a
        visible sweep rather than a flat line. A frequency sweep has
        nothing drawn to read, so both ends come from the NV zero-field
        splitting, the one number every such rig starts from.
        """
        axis = self.timeline.sweep
        if quantity == DURATION:
            first = self.timeline.swept[0].duration if self.timeline.swept else 0.0
            if axis is None or axis.stop <= first:
                self.timeline.sweep = replace(
                    axis or SweepAxis(), start=0.0, stop=first * 10 or 1e-6,
                )
        elif quantity == FREQUENCY and (axis is None or axis.stop < 1e6):
            self.timeline.sweep = replace(
                axis or SweepAxis(), start=2.82e9, stop=2.92e9,
            )

    def _update_selected(self, **fields: Any) -> None:
        """Replace the selected pulse with one differing in `fields`."""
        if self._selected is None:
            return
        track = self.timeline.tracks[self._selected.lane]
        if self._selected.pulse not in track.pulses:
            return
        position = track.pulses.index(self._selected.pulse)
        track.pulses[position] = replace(track.pulses[position], **fields)
        self._selected.pulse = track.pulses[position]

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

    def _edited(self) -> None:
        """The inspector changed something about the selected pulse."""
        if self._silent or self._selected is None:
            return
        start = float(self.pulse_start.value())
        length = max(float(self.pulse_length.value()), 0.0)
        self._update_selected(
            start=start, stop=start + length, name=self.pulse_name.text()
        )
        # Resizing a swept pulse moves the axis's first value with it, and
        # its siblings have to follow: they all take the same value at each
        # point, so leaving them behind would make the sequence unplayable
        # the moment you dragged one edge.
        if self._selected is not None and self._selected.pulse.sweep == DURATION:
            self._match_swept_lengths(length)
        self._changed()

    def _match_swept_lengths(self, length: float) -> None:
        for track in self.timeline.tracks:
            for index, pulse in enumerate(track.pulses):
                if pulse.sweep == DURATION and abs(pulse.duration - length) > 1e-15:
                    track.pulses[index] = replace(pulse, stop=pulse.start + length)
                    # Resizing the pulse someone has selected leaves the
                    # selection pointing at an object no longer in the
                    # track, and the rebuild then finds nothing to
                    # reselect — the inspector empties itself mid-edit.
                    if self._selected is not None and self._selected.pulse is pulse:
                        self._selected.pulse = track.pulses[index]

    def _drives_changed(self, checked: bool) -> None:
        if self._silent:
            return
        self._update_selected(drives=bool(checked))
        self._changed()

    def _sweep_changed(self) -> None:
        if self._silent:
            return
        self.sweep_selected(self.sweep_combo.currentData() or "")

    def _axis_edited(self) -> None:
        if self._silent:
            return
        self.set_sweep(
            points=int(self.axis_points.value()),
            start=float(self.axis_start.value()),
            stop=float(self.axis_stop.value()),
            spacing=self.axis_spacing.currentData(),
            name=self.axis_name.text().strip(),
        )

    def _shape_changed(self) -> None:
        if self._silent or self._selected is None:
            return
        name = self.shape_combo.currentData() or ""
        # A shape's parameters belong to the shape: a Gauss inheriting a
        # Chirp's start_frequency would be a silent wrong answer.
        self._update_selected(value=SHAPES[name]() if name else True)
        self._changed()

    def _shape_param_changed(self, parameter: str, value: float) -> None:
        if self._selected is None or not self._selected.pulse.analog:
            return
        # Through `_update_selected` rather than rebuilding the pulse from
        # its positional fields: a rebuilt one silently loses every field
        # the constructor call does not mention, which is how typing a
        # carrier frequency used to unmark a swept pulse.
        current = self._selected.pulse.value
        shape = type(current)
        fields = {p.name: getattr(current, p.name) for p in shape.params}
        fields[parameter] = float(value)
        self._update_selected(value=shape(**fields))
        self._changed(rebuild=False)

    # --- Selection ---------------------------------------------------------

    def _show_selection(self) -> None:
        pulse = self._selected.pulse if self._selected else None
        lane = self._selected.lane if self._selected else -1
        self._silent = True
        try:
            for widget in (self.pulse_name, self.pulse_start, self.pulse_length,
                           self.shape_combo, self.drives_check, self.sweep_combo):
                widget.setEnabled(pulse is not None)
            self.hint.setVisible(pulse is None)
            self.axis_form.setVisible(pulse is not None and bool(pulse.sweep))
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
            self._show_drives(pulse, lane)
            self._fill_sweep_combo(lane)
            self.sweep_combo.setCurrentIndex(
                max(self.sweep_combo.findData(pulse.sweep), 0)
            )
            self._show_axis(pulse)
        finally:
            self._silent = False

    def _fill_sweep_combo(self, lane: int) -> None:
        """Only what this pulse's lane can actually sweep.

        A length is a property of any drawn interval, so every pulse is
        offered one — a drive, a gate, a gap. A *carrier* is a property of
        a drive, so the frequency is offered only on a microwave lane:
        a laser line and a counter gate are on/off, with nothing to tune.
        Offering it there and refusing it at save time would be the worse
        half of that trade.
        """
        channel = (
            self.timeline.tracks[lane].channel
            if 0 <= lane < len(self.timeline.tracks) else ""
        )
        drive = self._kinds.get(channel) == MW
        self.sweep_combo.clear()
        self.sweep_combo.addItem("Fixed", "")
        self.sweep_combo.addItem("Sweep its length", DURATION)
        if drive:
            self.sweep_combo.addItem("Sweep the MW frequency", FREQUENCY)

    def _show_drives(self, pulse: Pulse, lane: int) -> None:
        """One checkbox, labelled by what the lane it is on makes it mean.

        On the readout lane it is "does this count as a measurement"; on
        any other it is "does this drive the channel, or just hold time".
        Two questions in the same field because they are the same
        question, and a person reading the inspector should see the one
        that applies to the pulse in front of them.
        """
        readout = (
            0 <= lane < len(self.timeline.tracks)
            and self.timeline.tracks[lane].channel == self._readout
        )
        self.drives_check.setText(
            "Measurement — opens the counter gate" if readout
            else "Drives this channel"
        )
        self.drives_check.setToolTip(
            "Unchecked makes this a timing block: it holds its span of the "
            "timeline and can be swept, but the channel stays low across "
            "it. That is how a gap — a Ramsey's free evolution, a T1's "
            "wait — becomes something you can click, name and sweep."
            + (
                "\n\nOn this lane, unchecked also means the run does not "
                "count it as a readout."
                if readout else ""
            )
        )
        self.drives_check.setChecked(pulse.drives)

    def _show_axis(self, pulse: Pulse) -> None:
        """The shared axis, in the units the marked quantity is measured
        in — seconds for a length, hertz for a carrier."""
        if not pulse.sweep:
            return
        axis = self.timeline.sweep or SweepAxis()
        frequency = pulse.sweep == FREQUENCY
        for box in (self.axis_start, self.axis_stop):
            box.setOpts(suffix="Hz" if frequency else "s")

        self.axis_start.setValue(axis.start or (0.0 if frequency else pulse.duration))
        self.axis_stop.setValue(axis.stop)
        self.axis_points.setValue(axis.points)
        self.axis_spacing.setCurrentIndex(
            max(self.axis_spacing.findData(axis.spacing), 0)
        )
        self.axis_name.setText(axis.name)
        self.axis_name.setPlaceholderText("frequency" if frequency else "tau")
        self.axis_start.setToolTip(
            "Where the sweep starts. Leave at zero for a length sweep to "
            "take the pulse as you drew it."
            if not frequency else "What the source emits at the first point."
        )
        marked = len(self.timeline.swept)
        self.axis_form.setToolTip(
            f"One axis, shared by {marked} marked pulse(s) — editing it "
            f"here changes it for all of them."
        )

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
            box = _sized(pg.SpinBox(
                value=float(getattr(pulse.value, parameter.name)),
                suffix=parameter.unit or None,
                siPrefix=bool(parameter.unit),
                dec=True, minStep=1e-12,
            ))
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


