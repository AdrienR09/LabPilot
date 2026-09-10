"""Live/last-result views for a workflow's `RESULT_UI` declaration (see
core/workflow/instrument_roles.py) — plain pyqtgraph widgets, deliberately
NOT `UIComponent`/`InstrumentContext`-based like the per-instrument blocks
in this package: these render workflow-level progress data polled via
`backend_client.WorkflowStatePoller`, not a single instrument's readings,
so there's no `ctx` to hang off of. Built directly on pyqtgraph the same
way `hyperspectral_viewer.py` is, for the same reason: no per-ROI pipeline
needed, just "draw this array".

Modeled closely on the real qudi scanning GUI
(github.com/Ulm-IQO/qudi-iqo-modules/tree/main/src/qudi/gui/scanning and
github.com/Ulm-IQO/qudi-core/tree/main/src/qudi/util/widgets/plotting),
pulled and read directly rather than approximated from memory: qudi's
`Scan2DWidget` (a toggle-scan/save/channel toolbar row over an image +
adjustable colorbar, with a live cursor-position label) is the one
reusable unit its `ScanDockWidget` wraps once per axis pair — `_ScanImagePanel`
below is that same unit, shared by both `Image2DResultView` (one pane) and
`NDScanResultView` (one per axis pair, see that class).
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, ClassVar, Optional

import numpy as np
import pyqtgraph as pg
from components.base import ComponentMeta
from components.nd_math import (
    compute_1d_projection,
    compute_panel_projection,
    parse_flat_data,
)
from components.widgets import dock
from PyQt6.QtCore import QObject, QRectF, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGraphicsRectItem,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph.graphicsItems.GradientEditorItem import Gradients

pg.setConfigOption("imageAxisOrder", "row-major")  # match numpy's (row, col) convention

__all__ = [
    "Image2DResultView", "SpectrumResultView", "NDScanResultView", "OdmrResultView",
    "PulseSequenceResultView", "ResultViewAdapter",
    "Image2DResultViewAdapter", "SpectrumResultViewAdapter", "OdmrResultViewAdapter",
    "NDScanResultViewAdapter", "PulseSequenceResultViewAdapter",
]


def _image_rect(x_values: list[float], y_values: list[float]) -> Optional[QRectF]:
    """The QRectF an ImageItem's `setRect` should use so a pixel's center
    sits exactly on its real (x_values[i], y_values[j]) position — half a
    pixel is added on each side, matching qudi's own
    `ScanImageItem.set_image_extent` (qudi-legacy/qtwidgets/
    scan_plotwidget.py). None if there are too few points on either axis
    to derive a pixel size yet."""
    if not x_values or not y_values or len(x_values) < 2 or len(y_values) < 2:
        return None
    x0, x1 = x_values[0], x_values[-1]
    y0, y1 = y_values[0], y_values[-1]
    dx = (x1 - x0) / (len(x_values) - 1) / 2
    dy = (y1 - y0) / (len(y_values) - 1) / 2
    return QRectF(x0 - dx, y0 - dy, (x1 - x0) + 2 * dx, (y1 - y0) + 2 * dy)


class _Crosshair:
    """qudi's own crosshair (`qudi.util.widgets.plotting.marker.InfiniteCrosshairRectangle`,
    read directly from source): two perpendicular draggable `pg.InfiniteLine`s
    plus a resizable central `pg.ROI` box with corner handles, in qudi's
    exact default colors — green (#00ff00) normal, yellow (#ffff00) on
    hover/drag — kept in sync exactly like that class's line/ROI
    callbacks: dragging any one of the three moves the other two;
    dragging a corner handle resizes the box without moving its center.

    `on_change(x, y)` fires synchronously on every drag tick (for a
    position label or coupling other crosshairs — see NDScanResultView).
    `on_move(x, y)` fires debounced (~30ms after the last tick), meant for
    the actual actuator write, so a drag doesn't write-storm real
    hardware. `Image2DResultView` owns exactly one of these;
    `NDScanResultView` owns one per 2D projection panel.

    `show_box=False` (the Optimizer dock's own panes use this — see
    workflow_window.py's `_build_optimizer_panel`) omits the resizable ROI
    box entirely, leaving just the two lines as a plain, non-interactive
    marker: that dock's own box used to duplicate the SAME range-defining
    role the corresponding main scan panel's own crosshair box already
    has, which is genuinely confusing (two different boxes, only one of
    which actually did anything) — now there is exactly one resizable box
    per axis pair (the main panel's), and the Optimizer dock only ever
    marks where a fit converged. `color`, if given (the Optimizer dock
    again — a distinct magenta instead of the interactive green), makes
    that "this one is just a result indicator, not the same crosshair you
    can drag to set a target" visually unambiguous rather than relying on
    the reader to infer it from context.
    """

    _PEN = pg.mkPen("#00ff00", width=1)
    _HOVER_PEN = pg.mkPen("#ffff00", width=2)

    def __init__(
        self,
        view: pg.ViewBox,
        on_move: Optional[Callable[[float, float], None]] = None,
        on_change: Optional[Callable[[float, float], None]] = None,
        show_box: bool = True,
        color: Optional[str] = None,
        on_size_changed: Optional[Callable[[float, float], None]] = None,
        x_bounds: Optional[tuple[float, float]] = None,
        y_bounds: Optional[tuple[float, float]] = None,
    ) -> None:
        self._on_move = on_move
        self._on_change = on_change
        # The actuator's own declared axis range — qudi clamps its own
        # crosshair the same way (InfiniteLine(bounds=...)/RectangleROI's
        # _clip_area, qudi-core/util/widgets/plotting/roi.py), rejecting
        # an out-of-range drag position live rather than after the fact.
        # None means unbounded (e.g. before the first frame establishes a
        # real extent — see Image2DResultView.update_data/set_bounds).
        self._x_bounds = x_bounds
        self._y_bounds = y_bounds
        # Fires with the box's new (half_width_x, half_width_y) whenever
        # its resize handles are dragged — NDScanResultView couples this
        # across every panel sharing an axis (the same per-axis "selected
        # range" the new Channels dock's 1D region selectors edit): the
        # green rectangle IS that range, not just a cosmetic box.
        self._on_size_changed = on_size_changed
        pen = pg.mkPen(color, width=1) if color else self._PEN
        hover_pen = self._HOVER_PEN if color is None else pg.mkPen(color, width=2)
        self.h = pg.InfiniteLine(angle=0, movable=True, pen=pen, hoverPen=hover_pen)
        self.v = pg.InfiniteLine(angle=90, movable=True, pen=pen, hoverPen=hover_pen)
        view.addItem(self.h, ignoreBounds=True)
        view.addItem(self.v, ignoreBounds=True)

        self.roi: Optional[pg.ROI] = None
        self._box_size_initialized = False
        if show_box:
            # qudi's own crosshair (marker.Rectangle) defaults to
            # size=(1, 1) — matched here so the box is visibly there (not
            # a zero-size, invisible ROI) the instant the crosshair is
            # created, even before any real scan extent is known.
            # update_box_size() below replaces this placeholder with a
            # properly-proportioned size as soon as a real extent IS
            # known — but only once, tracked via _box_size_initialized
            # rather than inferred from size > 0, since the default is no
            # longer 0.
            self.roi = pg.ROI((-0.5, -0.5), (1, 1), pen=pen, hoverPen=hover_pen, movable=True, resizable=True)
            self.roi.addScaleHandle([1, 1], [0, 0])
            self.roi.addScaleHandle([0, 0], [1, 1])
            self.roi.addScaleHandle([1, 0], [0, 1])
            self.roi.addScaleHandle([0, 1], [1, 0])
            view.addItem(self.roi, ignoreBounds=True)
            self.roi.sigRegionChanged.connect(self._on_roi_dragged)

        self._live_write_timer = QTimer()
        self._live_write_timer.setSingleShot(True)
        self._live_write_timer.setInterval(30)
        self._live_write_timer.timeout.connect(self._commit_pending_move)
        self._pending: Optional[tuple[float, float]] = None

        self.h.sigDragged.connect(self._on_line_dragged)
        self.v.sigDragged.connect(self._on_line_dragged)

    def pos(self) -> tuple[float, float]:
        return self.v.value(), self.h.value()

    def set_bounds(self, x_bounds: Optional[tuple[float, float]], y_bounds: Optional[tuple[float, float]]) -> None:
        """Set/replace the clamp range — e.g. Image2DResultView calling
        this once its first frame establishes a real extent, which
        isn't known yet at add_crosshair() time."""
        self._x_bounds = x_bounds
        self._y_bounds = y_bounds

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        if self._x_bounds is not None:
            lo, hi = self._x_bounds
            x = min(max(x, min(lo, hi)), max(lo, hi))
        if self._y_bounds is not None:
            lo, hi = self._y_bounds
            y = min(max(y, min(lo, hi)), max(lo, hi))
        return x, y

    def set_pos(self, x: float, y: float) -> None:
        x, y = self._clamp(x, y)
        self.h.blockSignals(True)
        self.v.blockSignals(True)
        self.h.setPos(y)
        self.v.setPos(x)
        self.h.blockSignals(False)
        self.v.blockSignals(False)
        self._sync_roi(x, y)

    def _sync_roi(self, x: float, y: float) -> None:
        if self.roi is None:
            return
        size = self.roi.size()
        self.roi.blockSignals(True)
        self.roi.setPos(x - size[0] / 2, y - size[1] / 2)
        self.roi.blockSignals(False)

    def update_box_size(self, x_values: Optional[list[float]], y_values: Optional[list[float]]) -> None:
        """Scales the central ROI box to a fraction of the current panel's
        real extent on first layout — qudi's own crosshair does the
        equivalent against the ViewBox's visible range and then leaves the
        box resizable by the user (its corner handles) from there on;
        matched here by only setting an initial size, never overriding a
        size the user has since dragged. A no-op until two points exist on
        both axes, or once already initialized once, or there's no box at
        all (`show_box=False`)."""
        if self.roi is None or self._box_size_initialized:
            return
        if not x_values or not y_values or len(x_values) < 2 or len(y_values) < 2:
            return
        x_span = max(x_values) - min(x_values)
        y_span = max(y_values) - min(y_values)
        box = max(min(x_span, y_span) * 0.06, 1e-9)
        x, y = self.pos()
        self.roi.blockSignals(True)
        self.roi.setSize((box, box))
        self.roi.setPos(x - box / 2, y - box / 2)
        self.roi.blockSignals(False)
        self._box_size_initialized = True

    def set_box_half_widths(self, x_half: float, y_half: float) -> None:
        """Explicitly sets the box's half-widths along x/y independently
        (not forced square) — used to harmonize a box's size with another
        panel's, for whichever axis they share (NDScanResultView's own
        per-axis `_box_half_width` state), overriding whatever
        `update_box_size`'s auto-init produced. Counts as "initialized"
        (blocks any later auto-init from firing) since this is a
        deliberate external size, not a placeholder."""
        if self.roi is None:
            return
        x, y = self.pos()
        self.roi.blockSignals(True)
        self.roi.setSize((2 * x_half, 2 * y_half))
        self.roi.setPos(x - x_half, y - y_half)
        self.roi.blockSignals(False)
        self._box_size_initialized = True

    def set_visible(self, visible: bool) -> None:
        self.h.setVisible(visible)
        self.v.setVisible(visible)
        if self.roi is not None:
            self.roi.setVisible(visible)

    def _on_line_dragged(self, _line=None) -> None:
        x, y = self.pos()
        clamped_x, clamped_y = self._clamp(x, y)
        if (clamped_x, clamped_y) != (x, y):
            # Snap the dragged line back within bounds — blockSignals so
            # this reposition doesn't re-enter this same handler.
            self.h.blockSignals(True)
            self.v.blockSignals(True)
            self.h.setPos(clamped_y)
            self.v.setPos(clamped_x)
            self.h.blockSignals(False)
            self.v.blockSignals(False)
            x, y = clamped_x, clamped_y
        self._sync_roi(x, y)
        if self._on_change is not None:
            self._on_change(x, y)
        self._schedule_move(x, y)

    def _on_roi_dragged(self) -> None:
        size = self.roi.size()
        pos = self.roi.pos()
        x, y = pos[0] + size[0] / 2, pos[1] + size[1] / 2
        x, y = self._clamp(x, y)
        self.h.blockSignals(True)
        self.v.blockSignals(True)
        self.h.setPos(y)
        self.v.setPos(x)
        self.h.blockSignals(False)
        self.v.blockSignals(False)
        self._sync_roi(x, y)
        if self._on_change is not None:
            self._on_change(x, y)
        if self._on_size_changed is not None:
            self._on_size_changed(size[0] / 2, size[1] / 2)
        self._schedule_move(x, y)

    def _schedule_move(self, x: float, y: float) -> None:
        # Restarting an already-running single-shot timer coalesces a burst
        # of drag events into one write ~30ms after the most recent one —
        # live-feeling without write-storming a real instrument on every
        # intermediate drag frame.
        self._pending = (x, y)
        self._live_write_timer.start()

    def _commit_pending_move(self) -> None:
        if self._on_move is not None and self._pending is not None:
            self._on_move(*self._pending)


class _ColorBarControls(QWidget):
    """A pyMoDAQ-`Viewer2D`-style colorbar sidebar for one `pg.ImageItem`:
    a draggable histogram + gradient (`pg.HistogramLUTWidget`) with a
    colormap picker above it and explicit numeric min/max fields below —
    every name in `_COLORMAPS` is one of pyqtgraph's own bundled
    presets (`GradientEditorItem.Gradients`), so no extra dependency
    (e.g. matplotlib) is required just to offer familiar maps like
    viridis/inferno/plasma/magma alongside qudi-style thermal/bipolar
    ones.

    Editing a level here (dragging the histogram, or typing into a
    spinbox) emits `levelsEdited` — `_ScanImagePanel` listens for that to
    flip its own auto-level off, the same way dragging a level by hand in
    pyMoDAQ implicitly pins it; otherwise the very next auto-leveled
    frame would silently overwrite whatever the user just set.
    """

    levelsEdited = pyqtSignal()

    _COLORMAPS = sorted(Gradients.keys())

    def __init__(
        self,
        image_item: pg.ImageItem,
        default_colormap: str = "viridis",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.image_item = image_item
        # Capped overall width — a colorbar sidebar is a secondary control,
        # not a plot; it shouldn't compete with the image for space.
        self.setMaximumWidth(100)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(self._COLORMAPS)
        if default_colormap in self._COLORMAPS:
            self.colormap_combo.setCurrentText(default_colormap)
        self.colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
        layout.addWidget(self.colormap_combo)

        self.histogram = pg.HistogramLUTWidget()
        self.histogram.setImageItem(image_item)
        self.histogram.setFixedWidth(70)
        self.histogram.item.gradient.loadPreset(self.colormap_combo.currentText())
        self.histogram.item.sigLevelsChanged.connect(self._on_histogram_levels_changed)
        layout.addWidget(self.histogram, 1)

        # Min/Max stacked (not side by side) and prefix-labeled instead of
        # a separate QLabel each — keeps the whole sidebar narrow.
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setPrefix("min ")
        self.min_spin.setRange(-1e12, 1e12)
        self.min_spin.setDecimals(4)
        self.min_spin.setKeyboardTracking(False)
        self.min_spin.setMaximumWidth(90)
        layout.addWidget(self.min_spin)
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setPrefix("max ")
        self.max_spin.setRange(-1e12, 1e12)
        self.max_spin.setDecimals(4)
        self.max_spin.setKeyboardTracking(False)
        self.max_spin.setMaximumWidth(90)
        layout.addWidget(self.max_spin)

        self.min_spin.valueChanged.connect(self._on_spin_changed)
        self.max_spin.valueChanged.connect(self._on_spin_changed)

        self._syncing = False
        self.refresh_levels()

    def _on_colormap_changed(self, name: str) -> None:
        self.histogram.item.gradient.loadPreset(name)

    def _on_histogram_levels_changed(self) -> None:
        if self._syncing:
            return
        self._sync_spins_from_histogram()
        self.levelsEdited.emit()

    def _on_spin_changed(self, _value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.histogram.item.setLevels(self.min_spin.value(), self.max_spin.value())
        finally:
            self._syncing = False
        self.levelsEdited.emit()

    def _sync_spins_from_histogram(self) -> None:
        self._syncing = True
        try:
            lo, hi = self.histogram.item.getLevels()
            self.min_spin.setValue(lo)
            self.max_spin.setValue(hi)
        finally:
            self._syncing = False

    def refresh_levels(self) -> None:
        """Call after the image item's levels change from outside (e.g.
        an auto-leveled setImage() call) to keep the spinboxes showing
        the real current range — does NOT emit levelsEdited, since this
        reflects an automatic change, not a user edit."""
        self._sync_spins_from_histogram()


class _ScanImagePanel(QWidget):
    """One qudi `Scan2DWidget`-equivalent pane (read directly from
    `gui/scanning/scan_widget.py`): a [Channel] toolbar row over an
    auto-leveled image, and a live cursor-position label below. The
    single reusable unit both `Image2DResultView` (one pane) and
    `NDScanResultView` (one per axis pair) are built from — qudi's own
    `Scan2DWidget` is likewise instantiated once per `ScanDockWidget`,
    however many axis pairs exist.

    A `_ColorBarControls` sidebar sits to the right of the image (a
    pyMoDAQ-`Viewer2D`-style colormap picker + draggable histogram +
    numeric min/max fields) — see that class's docstring. Images
    auto-level every frame by default; editing a level by hand (drag or
    spinbox) pins this panel out of auto-level until `set_auto_level`
    (driven by the workflow window's own Settings menu) turns it back on.

    Used to have its own per-panel Toggle Scan/Save buttons (qudi's
    Scan2DWidget convention) — dropped: Toggle Scan only ever mirrored the
    single shared Execute/Stop toolbar action (workflow_window.py's
    `_build_workflow_toolbar`), and its checked state could drift out of
    sync with the real run state after certain settings-dialog round
    trips; Save (PNG export) is now one toolbar action
    (`_on_save_all`) covering every panel at once instead of a button
    duplicated on each one.
    """

    def __init__(
        self,
        x_label: str = "",
        y_label: str = "",
        channel_label: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Channel:"))
        self.channel_combobox = QComboBox()
        if channel_label:
            self.channel_combobox.addItem(channel_label)
        self.channel_combobox.setEnabled(False)  # exactly one channel today — see class docstring
        toolbar.addWidget(self.channel_combobox)
        layout.addLayout(toolbar)

        self.plot_widget = pg.PlotWidget()
        plot_item = self.plot_widget.getPlotItem()
        if x_label:
            plot_item.setLabel("bottom", x_label)
        if y_label:
            plot_item.setLabel("left", y_label)
        self.image_item = pg.ImageItem()
        # A large panel image (e.g. a 2000x2000 projection) is expensive
        # to rasterize at full resolution every frame regardless of how
        # cheaply the underlying array was computed — pyqtgraph downsamples
        # to the actual on-screen pixel count instead when this is set,
        # which is a pure rendering-side win, orthogonal to the
        # NDProjectionComputer background-thread work above it.
        self.image_item.setAutoDownsample(True)
        plot_item.addItem(self.image_item)

        # The image, its colorbar, and any extra controls (e.g.
        # NDScanResultView's per-axis range selectors) sit side by side,
        # in that order — extra controls to the RIGHT of the colorbar,
        # not below anything (see add_extra_controls).
        content_row = QHBoxLayout()
        content_row.addWidget(self.plot_widget, 1)
        self.colorbar = _ColorBarControls(self.image_item)
        self.colorbar.levelsEdited.connect(self._on_levels_edited)
        content_row.addWidget(self.colorbar)
        layout.addLayout(content_row, 1)
        self._content_row = content_row

        self.position_label = QLabel("")
        layout.addWidget(self.position_label)

        self._crosshair: Optional[_Crosshair] = None
        self._move_callback: Optional[Callable[[float, float], None]] = None
        self._auto_level = True
        self._last_x_values: Optional[list[float]] = None
        self._last_y_values: Optional[list[float]] = None
        self._extra_controls: Optional[QWidget] = None

    def _on_levels_edited(self) -> None:
        # A manual level edit implicitly pins this one panel out of
        # auto-level — otherwise the very next auto-leveled frame would
        # silently undo it. Local to this panel only; doesn't touch the
        # workflow window's shared Settings-menu toggle, which still wins
        # (re-enabling auto-level for every panel) if switched back on.
        self._auto_level = False

    # ---- extension point (e.g. NDScanResultView's per-panel "other axes"
    # projection-range selectors, merged directly into this panel's own
    # dock rather than a separate global one) ----

    def add_extra_controls(self, widget: Optional[QWidget]) -> None:
        """Embeds `widget` to the RIGHT of the image, replacing whatever
        was embedded before (safe to call again, e.g. once more axes are
        discovered and a caller needs to rebuild what it shows). Pass
        None to just remove whatever's currently embedded."""
        if self._extra_controls is not None:
            self._content_row.removeWidget(self._extra_controls)
            self._extra_controls.deleteLater()
            self._extra_controls = None
        if widget is not None:
            self._extra_controls = widget
            self._content_row.addWidget(widget)

    # ---- save (called from workflow_window.py's toolbar Save action,
    # see _on_save_all — no per-panel button anymore) ----

    def save_image_as_png(self, path: str) -> None:
        import pyqtgraph.exporters as pg_exporters
        exporter = pg_exporters.ImageExporter(self.plot_widget.getPlotItem())
        exporter.export(path)

    # ---- image + extent + levels ----

    def set_image(self, array: np.ndarray, first_frame: bool) -> None:
        self.image_item.setImage(array, autoLevels=self._auto_level)
        if self._auto_level:
            # Keep the colorbar's numeric fields showing the real current
            # range when auto-level just picked a new one — harmless
            # no-op the rest of the time (levels unchanged).
            self.colorbar.refresh_levels()
        if first_frame:
            self.plot_widget.getPlotItem().getViewBox().autoRange()

    def set_auto_level(self, auto_level: bool) -> None:
        """Driven by the workflow window's own Settings menu (see
        NDScanResultView.set_auto_level) — off freezes the image at
        whatever levels it last had instead of rescaling every frame."""
        self._auto_level = auto_level

    def set_extent(self, x_values: Optional[list[float]], y_values: Optional[list[float]]) -> None:
        self._last_x_values = x_values
        self._last_y_values = y_values
        rect = _image_rect(x_values, y_values)
        if rect is not None:
            if self.image_item.image is not None:
                self.image_item.setRect(rect)
            else:
                # pyqtgraph's own ImageItem.setRect() docstring: "This
                # method cannot be used before an image is assigned" —
                # NDScanResultView builds every axis-pair panel (and
                # calls set_extent on it) eagerly, before any scan has
                # run and so before set_image() has ever been called on
                # it (see _add_panel); calling setRect here crashed
                # immediately (TypeError: unsupported operand type(s)
                # for /: 'float' and 'NoneType', inside pyqtgraph's own
                # setRect, dividing by self.width() which is None with
                # no image set). But just skipping it left the
                # ViewBox's visible range at pyqtgraph's tiny (0,0)-(1,1)
                # default while the crosshair was created at a real
                # coordinate (e.g. the axis range's midpoint) —
                # correctly positioned, just entirely outside the
                # visible viewport, so it looked like it had vanished.
                # Setting the ViewBox's own range directly (rather than
                # the ImageItem's transform) needs no image and gets the
                # real axis extent on screen immediately; set_image()'s
                # own first-frame autoRange() call supersedes this once
                # real data arrives.
                self.plot_widget.getPlotItem().getViewBox().setRange(rect, padding=0)
        if self._crosshair is not None:
            self._crosshair.update_box_size(x_values, y_values)

    # ---- crosshair ----

    def add_crosshair(
        self,
        on_move: Optional[Callable[[float, float], None]] = None,
        on_change: Optional[Callable[[float, float], None]] = None,
        show_box: bool = True,
        color: Optional[str] = None,
        on_size_changed: Optional[Callable[[float, float], None]] = None,
        x_bounds: Optional[tuple[float, float]] = None,
        y_bounds: Optional[tuple[float, float]] = None,
    ) -> None:
        view = self.plot_widget.getPlotItem().getViewBox()
        self._move_callback = on_move
        self._crosshair = _Crosshair(
            view, on_move=on_move, on_change=on_change or self._update_position_label,
            show_box=show_box, color=color, on_size_changed=on_size_changed,
            x_bounds=x_bounds, y_bounds=y_bounds,
        )
        if on_move is not None:
            view.scene().sigMouseClicked.connect(self._on_scene_clicked)
        # Give the box a properly-proportioned size immediately if this
        # panel's real extent is already known (e.g. NDScanResultView's
        # eager panels, sized from AXIS_RANGES before any scan has run) —
        # otherwise it keeps _Crosshair's qudi-matching (1, 1) placeholder
        # until the first real set_extent() call replaces it.
        self._crosshair.update_box_size(self._last_x_values, self._last_y_values)

    def set_crosshair_bounds(
        self, x_bounds: Optional[tuple[float, float]], y_bounds: Optional[tuple[float, float]],
    ) -> None:
        """Updates the crosshair's clamp range — e.g. once
        Image2DResultView's first frame establishes a real extent, not
        known yet at add_crosshair() time. A no-op before add_crosshair()."""
        if self._crosshair is not None:
            self._crosshair.set_bounds(x_bounds, y_bounds)

    def set_crosshair_box_size(self, x_half: float, y_half: float) -> None:
        """Explicit external box half-widths — NDScanResultView harmonizes
        these across every panel sharing an axis (see class docstring's
        `crosshair_box_size`/`_Crosshair.set_box_half_widths`)."""
        if self._crosshair is not None:
            self._crosshair.set_box_half_widths(x_half, y_half)

    def _update_position_label(self, x: float, y: float) -> None:
        self.position_label.setText(f"x = {x:.4g}, y = {y:.4g}")

    def set_crosshair_pos(self, x: float, y: float) -> None:
        if self._crosshair is None:
            return
        self._crosshair.set_pos(x, y)

    def crosshair_box_size(self) -> Optional[tuple[float, float]]:
        """The crosshair's central ROI box's current (width, height) —
        dragging its resize handles on a main scan panel is what defines
        the optimizer's search range for that axis pair (see
        workflow_window.py's `_on_toggle_optimize`, which reads this from
        `NDScanResultView.panels`, not from the Optimizer dock's own
        panes — those show `show_box=False`, a plain marker with no box
        of their own, so there is exactly one resizable box per axis
        pair, not two disconnected ones). None before add_crosshair(), or
        if this panel's crosshair has no box at all."""
        if self._crosshair is None or self._crosshair.roi is None:
            return None
        w, h = self._crosshair.roi.size()
        return float(w), float(h)

    def show_crosshair(self) -> None:
        if self._crosshair is not None:
            self._crosshair.set_visible(True)

    def hide_crosshair(self) -> None:
        if self._crosshair is not None:
            self._crosshair.set_visible(False)

    def _on_scene_clicked(self, event: Any) -> None:
        if self._crosshair is None or self._move_callback is None:
            return
        view_pos = self.plot_widget.getPlotItem().getViewBox().mapSceneToView(event.scenePos())
        x, y = view_pos.x(), view_pos.y()
        self._crosshair.set_pos(x, y)
        self._update_position_label(x, y)
        self._move_callback(x, y)


class _OptimizerCurvePanel(QWidget):
    """One 1D step of an optimize sequence — data-vs-position curve plus a
    vertical marker at the fit's found center, qudi's own `OptimizerDockWidget`
    1D pane (`XYPlotItem`/`fit_plot_item`, `UI_FRAMEWORK_DESIGN.md` §2.6)
    minus the fit *curve* overlay (this panel marks the fit center directly
    rather than reconstructing/plotting the fit function's shape — a
    deliberately smaller version of qudi's pane, sufficient to see where
    the optimizer converged without needing the full fit curve redrawn).

    Used for whichever step of an `OptimizerSequence` decomposition is a
    single leftover axis (e.g. 3 axes -> `[('x','y'), ('z',)]` — this pane
    is qudi's own confocal case's `('z',)` step exactly); every 2-axis step
    uses `_ScanImagePanel` instead."""

    def __init__(
        self,
        axis_label: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.plot_widget = pg.PlotWidget()
        if axis_label:
            self.plot_widget.setLabel("bottom", axis_label)
        self.curve = self.plot_widget.plot(pen="c", symbol="o", symbolSize=6)
        self.marker = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#00ff00", width=2))
        self.marker.setVisible(False)
        self.plot_widget.addItem(self.marker, ignoreBounds=True)
        layout.addWidget(self.plot_widget, 1)

        self.position_label = QLabel("")
        layout.addWidget(self.position_label)

    def set_data(self, x: list[float], y: list[float]) -> None:
        self.curve.setData(x, y)

    def set_fit_center(self, x: Optional[float]) -> None:
        if x is None:
            self.marker.setVisible(False)
            return
        self.marker.setPos(x)
        self.marker.setVisible(True)

    def set_result_text(self, text: str) -> None:
        self.position_label.setText(text)


class Image2DResultView(QWidget):
    """Thin wrapper around one `_ScanImagePanel` (`RESULT_UI["type"] ==
    "image2d"`) — see that class for the actual qudi-style toolbar/image/
    colorbar/position-label composition. Cells not yet scanned may still
    be `None` mid-run — rendered as NaN (blank) rather than crashing on a
    mixed None/float array.

    The image is drawn at its true physical extent (`ImageItem.setRect`,
    the same technique qudi's own `ScanImageItem.set_image_extent` uses)
    rather than at raw pixel indices, so the optional crosshair
    (`add_crosshair`) below operates in the scan's real coordinate units
    and can be dragged continuously, not snapped to the nearest scanned
    pixel — opt-in per `RESULT_UI["crosshair"]` (see omniscan.py),
    since it only makes sense when the scan axes are also the workflow's
    real live 2D position (not true for e.g. grating_spectrometer's image).
    """

    def __init__(
        self,
        value_label: str = "Value",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = _ScanImagePanel(channel_label=value_label)
        layout.addWidget(self.panel)

        self._got_first_frame = False
        # Axis value arrays from the most recent update_data() call — the
        # array's row index maps to _x_values, column index to _y_values
        # (matching how a raster builds `image[i][j]`, i over
        # x positions, j over y). Used only to compute the image's real
        # extent (ImageItem.setRect) on each update.
        self._x_values: Optional[list[float]] = None
        self._y_values: Optional[list[float]] = None

    def update_data(self, value_2d: Any, x_values: Any = None, y_values: Any = None) -> None:
        if not value_2d:
            return
        rows = [[np.nan if v is None else float(v) for v in row] for row in value_2d]
        array = np.array(rows, dtype=float)
        if array.size == 0:
            return
        if x_values:
            self._x_values = list(x_values)
        if y_values:
            self._y_values = list(y_values)
        first = not self._got_first_frame
        self._got_first_frame = True
        self.panel.set_image(array, first_frame=first)
        self.panel.set_extent(self._x_values, self._y_values)
        # The real extent (and so the crosshair's valid range) usually
        # isn't known yet at add_crosshair() time — the first frame here
        # is what actually establishes it.
        self.panel.set_crosshair_bounds(self._axis_bounds(self._x_values), self._axis_bounds(self._y_values))

    @staticmethod
    def _axis_bounds(values: Optional[list[float]]) -> Optional[tuple[float, float]]:
        if not values:
            return None
        return min(values), max(values)

    def add_crosshair(self, on_move: Optional[Callable[[float, float], None]] = None) -> None:
        """Adds a qudi-scanner-style crosshair (see `_Crosshair`).
        Dragging it — or clicking anywhere on the image — calls
        `on_move(x, y)` with the crosshair's real (x, y), live while the
        drag is happening (debounced) so the actuator visibly tracks the
        drag in real time, not just once it's released. Clamped to the
        scan's own real extent once known (see update_data) — qudi's own
        crosshair can't be dragged past the scanner's declared axis range
        either."""
        self.panel.add_crosshair(
            on_move=on_move,
            x_bounds=self._axis_bounds(self._x_values), y_bounds=self._axis_bounds(self._y_values),
        )
        self.panel.set_extent(self._x_values, self._y_values)

    def set_crosshair_pos(self, x: float, y: float) -> None:
        """Moves the crosshair to real (x, y) — e.g. from a live-polled
        actuator position. A no-op before add_crosshair()."""
        self.panel.set_crosshair_pos(x, y)

    def show_crosshair(self) -> None:
        self.panel.show_crosshair()

    def hide_crosshair(self) -> None:
        """Hidden while a scan is actively running — dragging a live
        position marker while the scan itself is driving the actuator
        around would be confusing and would fight the scan's own moves,
        matching qudi's own scanner GUI (its crosshair only appears once a
        scan is idle)."""
        self.panel.hide_crosshair()

    def set_auto_level(self, auto_level: bool) -> None:
        self.panel.set_auto_level(auto_level)


class SpectrumResultView(QWidget):
    """Renders a growing 1D trace (`RESULT_UI["type"] == "spectrum"`),
    plus an optional fit-curve overlay + center marker — same precedent
    as `_OptimizerCurvePanel.set_fit_center` below, just alongside the
    raw-data curve rather than replacing it. Opt-in per
    `RESULT_UI["fit_x_key"/"fit_y_key"/"fit_center_key"]` (see
    odmr_sweep.py); a template that doesn't declare them just never calls
    set_fit(), leaving the overlay hidden."""

    def __init__(self, x_label: str = "", y_label: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.plot_widget = pg.PlotWidget()
        if x_label:
            self.plot_widget.setLabel("bottom", x_label)
        if y_label:
            self.plot_widget.setLabel("left", y_label)
        self.curve = self.plot_widget.plot(pen="c")
        self.fit_curve = self.plot_widget.plot(pen=pg.mkPen("#ff8800", width=2, style=Qt.PenStyle.DashLine))
        self.fit_marker = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#ff8800", width=1, style=Qt.PenStyle.DotLine))
        self.fit_marker.setVisible(False)
        self.plot_widget.addItem(self.fit_marker, ignoreBounds=True)
        layout.addWidget(self.plot_widget)

    def update_data(self, x_values: Any, y_values: Any) -> None:
        if not x_values or not y_values:
            return
        self.curve.setData(list(x_values), list(y_values))

    def set_fit(self, x_values: Any, y_values: Any, center: Optional[float]) -> None:
        if not x_values or not y_values:
            self.clear_fit()
            return
        self.fit_curve.setData(list(x_values), list(y_values))
        if center is None:
            self.fit_marker.setVisible(False)
        else:
            self.fit_marker.setPos(center)
            self.fit_marker.setVisible(True)

    def clear_fit(self) -> None:
        self.fit_curve.setData([], [])
        self.fit_marker.setVisible(False)

    # No crosshair on a 1D trace — no-ops so workflow_window.py can call
    # these polymorphically across every result-view type.
    def show_crosshair(self) -> None:
        pass

    def hide_crosshair(self) -> None:
        pass

    def set_auto_level(self, auto_level: bool) -> None:
        pass


class OdmrResultView(QWidget):
    """Renders `RESULT_UI["type"] == "odmr"` — qudi's own ODMR GUI shape:
    the averaged spectrum (+ fit overlay) stacked above a "matrix" image
    where each row is one repeat's raw, unaveraged trace (qudi's
    `OdmrPlotWidget`: a spectrum plot over a scan-line accumulation image,
    sharing one colorbar for the image). Built entirely by composing the
    two pieces that already do each half — `SpectrumResultView` on top,
    `_ScanImagePanel` (with its own colorbar) below — in a `QSplitter` so
    a user can resize the split, rather than a fresh plotting
    implementation.
    """

    def __init__(
        self,
        x_label: str = "",
        y_label: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.spectrum = SpectrumResultView(x_label, y_label)
        self.matrix_panel = _ScanImagePanel(x_label=x_label, y_label="Repeat", channel_label="Counts")
        splitter.addWidget(self.spectrum)
        splitter.addWidget(self.matrix_panel)
        splitter.setSizes([2, 1])  # spectrum gets more room by default — matrix is a secondary view
        layout.addWidget(splitter)

        self._got_first_matrix_frame = False

    def update_data(self, x_values: Any, y_values: Any, matrix: Any = None, repeats_done: Any = None) -> None:
        self.spectrum.update_data(x_values, y_values)
        if not matrix:
            return
        rows = [[np.nan if v is None else float(v) for v in row] for row in matrix]
        array = np.array(rows, dtype=float)
        if array.size == 0:
            return
        first = not self._got_first_matrix_frame
        self._got_first_matrix_frame = True
        self.matrix_panel.set_image(array, first_frame=first)
        # X = frequency (same axis as the spectrum above), Y = repeat index.
        self.matrix_panel.set_extent(list(x_values) if x_values else None, list(range(len(rows))))

    def set_fit(self, x_values: Any, y_values: Any, center: Optional[float]) -> None:
        self.spectrum.set_fit(x_values, y_values, center)

    def clear_fit(self) -> None:
        self.spectrum.clear_fit()

    # No crosshair on either sub-panel here (the matrix's Y axis is repeat
    # index, not a real actuator position) — no-ops so workflow_window.py
    # can call these polymorphically across every result-view type.
    def show_crosshair(self) -> None:
        pass

    def hide_crosshair(self) -> None:
        pass

    def set_auto_level(self, auto_level: bool) -> None:
        self.matrix_panel.set_auto_level(auto_level)


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    n = max(1, int(n))
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


class _NDProjectionWorker(QObject):
    """Runs on NDProjectionComputer's background QThread. Does the
    O(array-size) flat-list parsing + per-panel/per-tab nanmean reductions
    that used to run directly on the GUI thread inside update_data()/
    _refresh_projections()/_compute_1d_projection() — for a large ND scan
    that could block the GUI for seconds at a time (the reshape alone
    measured ~0.1-0.2s per ~5M elements). numpy releases the GIL for these
    C-level operations, so running them here lets Qt's event loop on the
    GUI thread keep responding (repainting, handling clicks) concurrently
    instead of freezing for the duration.

    Every call is pure: takes/returns plain numpy arrays and Python
    containers (see components/nd_math.py), never touches a Qt widget —
    that's the caller's job, back on the GUI thread, once `resultReady`
    delivers the (already-computed, cheap-to-apply) result.
    """

    resultReady = pyqtSignal(object)  # dict — see NDProjectionComputer.submit()'s docstring

    @pyqtSlot(object)
    def compute(self, request: dict) -> None:
        # Skip stale work: if a newer request has already been submitted
        # by the time this one reaches the front of the queue, computing
        # this one is pure waste — the GUI only cares about the latest.
        # `request_id`/`latest_id_holder` are plain-int-attribute reads,
        # safe across threads under the GIL (no torn reads on a single
        # attribute), same reasoning as workflow_result.py's other
        # cross-thread coalescing.
        holder = request["latest_id_holder"]
        if request["request_id"] != holder.latest_request_id:
            return

        array = request.get("array")
        if array is None:
            array = parse_flat_data(request["flat_data"], request["shape"])
            if array is None:
                return
        if request["request_id"] != holder.latest_request_id:
            return  # superseded while we were parsing — don't bother projecting

        active = request["active"]
        axis_positions = request["axis_positions"]
        selections = request["selections"]

        panels: dict[tuple, np.ndarray] = {}
        for name_i, name_j in request["panel_keys"]:
            projected = compute_panel_projection(array, active, name_i, name_j, axis_positions, selections)
            if projected is not None:
                panels[(name_i, name_j)] = projected

        tabs: dict[str, tuple[list, list]] = {}
        for name in request["tab_keys"]:
            x, y = compute_1d_projection(array, active, name, axis_positions, selections)
            if x and y:
                tabs[name] = (x, y)

        self.resultReady.emit({
            "request_id": request["request_id"], "array": array, "active": active,
            "panels": panels, "tabs": tabs,
        })


class NDProjectionComputer(QObject):
    """Owns one background QThread that _NDProjectionWorker runs on — one
    instance per NDScanResultView, created/torn down alongside it.

    `submit()` is cheap (a dict + one queued signal emit) and always safe
    to call from the GUI thread, however often — coalesces automatically
    via `latest_request_id`: only the most recently submitted request's
    computation actually runs to completion and gets emitted, any still-
    queued older ones are skipped as soon as the worker notices they're
    stale.
    """

    resultReady = pyqtSignal(object)
    _computeRequested = pyqtSignal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.latest_request_id = 0
        self._thread = QThread()
        self._worker = _NDProjectionWorker()
        self._worker.moveToThread(self._thread)
        self._worker.resultReady.connect(self.resultReady)
        self._computeRequested.connect(self._worker.compute)
        self._thread.start()

    def submit(self, request: dict) -> None:
        self.latest_request_id += 1
        request = dict(request)
        request["request_id"] = self.latest_request_id
        request["latest_id_holder"] = self
        self._computeRequested.emit(request)

    def stop(self) -> None:
        self._thread.quit()
        self._thread.wait(1000)


class NDScanResultView:
    """Renders an N-dimensional scan array (`RESULT_UI["type"] ==
    "ndscan"`, see core/workflow_templates/omniscan.py) as one 2D
    mean-projection image PER PAIR OF AXES, each its own `_ScanImagePanel`
    in its own `QDockWidget` on the parent window — pyMoDAQ's and
    qudi-legacy's own N-dimensional-scan approach (an N-D dataset isn't
    directly viewable, so project it down onto every axis pair instead of
    picking one fixed 2D/3D slice ahead of time), combined with qudi's
    *own* real scanner GUI structure, read directly from
    `gui/scanning/scannergui.py`'s `on_activate`: every axis pair's
    `ScanDockWidget` is built EAGERLY, from the scanner's hardware-declared
    axes, before any scan has ever run — not lazily from the first
    frame's data as an earlier pass here did. This class does the same
    (`_build_panels`, called from `__init__`) for the ACTUATOR's own axes
    (`axis_ranges`, this workflow's AXIS_RANGES — known immediately), so
    every one of those panels — and its qudi-style "Toggle Scan" button —
    exists from the start, exactly like qudi's. (Without this, there
    would be no way to start the very first scan at all, since a
    lazily-built panel's own toggle button is the only thing that starts
    one.)

    A bound detector can be 0D, 1D, or 2D (see omniscan.py's
    `detector_axes()`) — its OWN internal axes (e.g. a spectrometer's
    wavelength axis, a camera's row/col pixel axes) aren't known until a
    real reading has actually happened. Unlike an earlier pass here,
    these detector-internal axes are NOT given their own projection
    panels once discovered (`_ensure_detector_axes` used to build one per
    new axis pair — multidimensional detector data isn't plotted for now,
    per explicit request) — they're still registered (`_axis_names`/
    `_axis_positions`, so HDF5 export and the Channels dock's per-axis
    1D tabs below cover them), just not visualized as extra 2D panels. A
    panel between two ACTUATOR axes gets the qudi-style crosshair
    (`add_crosshair`); a detector axis never contributes one — dragging
    it has nothing to move (see `actuator_axis_count` throughout).

    Every panel is placed as a plain tab in the window's LEFT dock area
    (no split-then-tabify) — "the crosshair with axes projection docked
    tabs on the left side", the Optimizer dock (workflow_window.py) split
    below the first of them. (qudi also builds a 1D "line scan" dock per
    individual axis alongside every 2D pair — out of scope here: our
    engine has no independent single-axis-only scan mode to back one with
    real data, so that dock would be decorative. A single *declared* axis
    still gets a plain curve dock as a minimal fallback.)

    Panels are keyed by axis NAME pair, not position-in-array index — the
    declared actuator axis set (fixed at construction) and whichever
    SUBSET a given run actually scanned (`axis_names` in `update_data`,
    which can vary run to run as SCAN_AXES is edited) are different things
    now that panels exist independently of any run ever having happened.
    A panel whose pair isn't part of the most recent run's `axis_names`
    simply isn't updated that tick — it keeps showing its last image,
    same as qudi's own dock for a not-currently-scanning axis pair.

    For 3+ total axes (actuator + detector-internal), each projection
    panel's "other axes" are averaged only over a per-axis *selected*
    range rather than always the full range — the true hyperspex-style
    piece (github.com/AdrienR09/hyperspex's coupled image/spectrum
    windows), now genuinely one 1D plot per dimension rather than a blank
    range strip: a separate "Channels" dock (`_build_channel_dock`) holds
    one TAB per axis (actuator or detector-internal alike), each a real
    `pg.PlotWidget` showing that axis's own data — averaged over every
    OTHER axis's current selection — with a draggable `pg.LinearRegionItem`
    over the curve to narrow ITS OWN selection. For an actuator axis, that
    same selection IS the crosshair's green box on its 2D panel(s)
    (`_box_half_width`, kept in sync across every panel sharing that axis
    exactly the way crosshair *position* already was — resizing the box
    on the X-Y panel updates the "x"/"y" channel tabs' regions too, and
    vice versa: dragging a channel tab's region moves and resizes the
    matching 2D panel's box). A detector-internal axis has no box (never
    shown in any 2D panel), so its channel tab's region is the only way
    to narrow it. Either direction submits a refresh (`_submit_projection_request`)
    covering every 2D panel and the currently-VISIBLE channel tab (not
    every tab — switching tabs triggers its own refresh for whichever one
    just became visible, see `_build_channel_dock`'s `currentChanged`
    connection) to the background `NDProjectionComputer`.

    An optional crosshair (`add_crosshair`, opt-in per
    `RESULT_UI["crosshair"]` — see omniscan.py) puts one on every
    actuator-actuator panel (delegated to that panel's own
    `_ScanImagePanel.add_crosshair`), all coupled through one shared
    position: dragging any panel's crosshair updates that panel's two
    axes, and every other panel sharing either axis moves to match
    (`_on_panel_changed`) — the same coupling the channel tabs above use,
    generalized from "which range is selected" to "where is the
    actuator". Hidden while a scan is running (`hide_crosshair`), same
    reasoning as Image2DResultView's.

    The shared position is the *target* (commanded) position, not a live
    actuator read-back — seeded at construction from HOLD_POSITIONS (or
    each axis's range midpoint), then updated only by user drag/click or
    an explicit target-setting action elsewhere, never by polling. This
    means it never moves during an active scan on its own (see
    `set_position`) — workflow_window.py additionally hides/locks it then.

    Public surface (`update_data`/`add_crosshair`/`set_position`/
    `show_crosshair`/`hide_crosshair`/`set_auto_level`) matches
    Image2DResultView/SpectrumResultView so workflow_window.py can treat
    every RESULT_UI type polymorphically despite this one managing several
    docks instead of being one widget.
    """

    def __init__(
        self,
        window: QWidget,
        axis_ranges: dict[str, tuple],
        value_label: str = "Value",
        hold_positions: Optional[dict[str, float]] = None,
        extra_dock_below=None,
        on_position_changed: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self.window = window
        self.value_label = value_label
        # Fires live (every drag tick, not debounced) whenever the
        # crosshair's target changes on ANY panel — workflow_window.py
        # wires this to AxesControlWidget.set_target so dragging the
        # crosshair moves the matching slider too ("there is no link
        # between the crosshair and the slider... you move the crosshair
        # and [it] should reflect into the slider position"), the
        # opposite direction of set_position() below (which AxesControlWidget's
        # own slider drag calls to move the crosshair).
        self._on_position_changed = on_position_changed
        # A caller-built QDockWidget (workflow_window.py's Optimizer dock)
        # to split below the very first scan panel, at the moment it's
        # placed — before any other panel gets tabbed into it. Splitting
        # against it any later (once 2+ panels are already tabbed
        # together) just tabs the new dock in instead of splitting it
        # below (see workflow_window.py's _add_optimizer_dock docstring).
        self._extra_dock_below = extra_dock_below

        # Fixed at construction — the actuator's own declared axes, the
        # only ones ever eligible for a crosshair (see class docstring).
        # `_axis_names` starts equal to this and grows once detector-
        # internal axes are discovered (_ensure_detector_axes).
        self._actuator_axis_names = list(axis_ranges.keys())
        self._axis_names = list(self._actuator_axis_names)
        self._axis_positions: dict[str, list[float]] = {
            name: _linspace(*axis_ranges[name]) for name in self._actuator_axis_names
        }
        self._detector_axes_known = False

        self._array: Optional[np.ndarray] = None
        self._array_axis_names: Optional[list[str]] = None  # which axes the CURRENT array actually covers
        # A fresh update_data() frame not yet handed to the background
        # computer — see _submit_projection_request(). None once consumed;
        # a re-projection request with no new data (a crosshair/region
        # drag) reuses self._array/_array_axis_names instead.
        self._pending_flat_data: Optional[list] = None
        self._pending_shape: Optional[list[int]] = None
        self._pending_active: Optional[list[str]] = None

        self._auto_level = True
        self._curve = None  # single-declared-axis fallback only — see class docstring
        self._panel_docks: dict[tuple[str, str], object] = {}
        self._panels: dict[tuple[str, str], _ScanImagePanel] = {}
        self._panel_has_data: dict[tuple[str, str], bool] = {}
        self._first_dock = None

        # The single per-axis "selected range" every projection/1D-curve
        # computation reads from (see components/nd_math.py, run on the
        # background NDProjectionComputer — _submit_projection_request).
        # For an actuator axis it's DERIVED from _position +/-
        # _box_half_width (the crosshair's own green box — kept in sync
        # across every panel sharing that axis, see _resync_box_sizes);
        # for a detector-internal axis (no box, never shown in any 2D
        # panel) it's set directly by that axis's own Channels-dock tab
        # region (_on_channel_region_changed).
        self._box_half_width: dict[str, float] = {}
        self._selection: dict[str, tuple[float, float]] = {}

        # {axis_name: {"plot_item":..., "curve":..., "region":...}} — one
        # tab per axis in the "Channels" dock (_build_channel_dock), a
        # real 1D projection (not a blank range strip) with a draggable
        # region over it.
        self._channel_tabs: dict[str, dict] = {}
        self._channel_tab_widget: Optional[QTabWidget] = None
        self._channel_dock = None

        # _submit_projection_request() re-slices and nanmean-averages the
        # FULL ND array (up to millions of elements) across every 2D panel
        # / the visible Channels-dock tab — genuinely expensive for a
        # large scan (measured ~0.1-0.2s per ~5M elements just for the
        # initial reshape). _on_panel_changed and _on_panel_box_resized
        # fire on EVERY mouse-move tick during a crosshair drag or box
        # resize (by design, for live visual feedback) — submitting a
        # request directly from them on every tick would flood the
        # background computer with stale work. This timer coalesces
        # bursts of ticks into one submission ~50ms after the last one,
        # the same debounce pattern _live_write_timer already uses for
        # hardware writes. The crosshair/box's own repositioning stays
        # undebounced (cheap Qt-item moves) so dragging itself still feels
        # instant; the actual reduction work now also runs on a background
        # thread (see NDProjectionComputer) rather than blocking the GUI
        # thread regardless of how it's paced.
        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._submit_projection_request)

        self._computer = NDProjectionComputer()
        self._computer.resultReady.connect(self._on_projection_ready)

        self._crosshair_enabled = False
        self._crosshair_on_move: Optional[Callable[[dict], None]] = None
        # Target position, not a live read-back — see class docstring.
        # Seeded now so the crosshair starts somewhere sensible the
        # instant add_crosshair() is called, rather than at (0, 0).
        hold_positions = hold_positions or {}
        self._position: dict[str, float] = {
            name: hold_positions.get(name, (min(positions) + max(positions)) / 2)
            for name, positions in self._axis_positions.items()
        }

        self._build_panels(self._actuator_axis_names)

    def _add_panel(self, name_i: str, name_j: str) -> None:
        """Builds one axis-pair's dock/panel and tabs it into every other
        panel in the window's LEFT dock area (see class docstring) — no
        split-then-tabify, every panel is a plain tab. Only adds a
        crosshair if both axes are the actuator's own (see class
        docstring) and a crosshair has actually been requested
        (`add_crosshair` already called)."""
        title = f"{name_i.title()}-{name_j.title()} Scan"
        panel = _ScanImagePanel(x_label=name_i, y_label=name_j, channel_label=self.value_label)
        panel.set_auto_level(self._auto_level)
        panel.set_extent(self._axis_positions[name_i], self._axis_positions[name_j])

        d = dock(title, self.window)
        d.setWidget(panel)
        self.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, d)
        if self._first_dock is None:
            self._first_dock = d
            if self._extra_dock_below is not None:
                self.window.splitDockWidget(d, self._extra_dock_below, Qt.Orientation.Vertical)
        else:
            self.window.tabifyDockWidget(self._first_dock, d)

        self._panel_docks[(name_i, name_j)] = d
        self._panels[(name_i, name_j)] = panel

        is_actuator_pair = name_i in self._actuator_axis_names and name_j in self._actuator_axis_names
        if is_actuator_pair and self._crosshair_enabled:
            self._add_panel_crosshair(name_i, name_j, panel)

    def _add_panel_crosshair(self, name_i: str, name_j: str, panel: _ScanImagePanel) -> None:
        """Adds this panel's crosshair (the shared-position coupling, see
        class docstring) and harmonizes its box's half-widths with
        whatever `_box_half_width` already knows for `name_i`/`name_j`
        (from another panel sharing one of these axes, or a Channels-dock
        tab region) — so the SAME axis's selected range always looks the
        same size everywhere it appears as a box, not independently
        auto-initialized per panel. If NEITHER axis has a known
        half-width yet, lets the box auto-init from this panel's own
        extent (`_Crosshair.update_box_size`'s existing qudi-matching
        default) and records the result for future panels/tabs to match."""
        panel.add_crosshair(
            on_move=lambda x, y, ni=name_i, nj=name_j: self._on_panel_moved(ni, nj, x, y),
            on_change=lambda x, y, ni=name_i, nj=name_j: self._on_panel_changed(ni, nj, x, y),
            on_size_changed=lambda w, h, ni=name_i, nj=name_j: self._on_panel_box_resized(ni, nj, w, h),
            # The actuator's own declared AXIS_RANGES — known up front
            # (unlike Image2DResultView), so bounds apply from the start.
            x_bounds=(min(self._axis_positions[name_i]), max(self._axis_positions[name_i])),
            y_bounds=(min(self._axis_positions[name_j]), max(self._axis_positions[name_j])),
        )
        hw_i = self._box_half_width.get(name_i)
        hw_j = self._box_half_width.get(name_j)
        if hw_i is not None or hw_j is not None:
            hw_i = hw_i if hw_i is not None else self._axis_span(name_i) * 0.03
            hw_j = hw_j if hw_j is not None else self._axis_span(name_j) * 0.03
            panel.set_crosshair_box_size(hw_i, hw_j)
            self._box_half_width[name_i] = hw_i
            self._box_half_width[name_j] = hw_j
        else:
            size = panel.crosshair_box_size()
            if size is not None:
                self._box_half_width[name_i] = size[0] / 2
                self._box_half_width[name_j] = size[1] / 2
        self._update_selection_from_box(name_i)
        self._update_selection_from_box(name_j)

    def _axis_span(self, name: str) -> float:
        positions = self._axis_positions.get(name)
        if not positions:
            return 1.0
        return max(max(positions) - min(positions), 1e-9)

    def _update_selection_from_box(self, name: str) -> None:
        """Recomputes `_selection[name]` from `_position[name]` +/-
        `_box_half_width[name]` — only meaningful for an actuator axis
        (the only ones with a crosshair/box at all); a no-op if either
        piece isn't known yet."""
        half = self._box_half_width.get(name)
        center = self._position.get(name)
        if half is not None and center is not None:
            self._selection[name] = (center - half, center + half)

    def _build_panels(self, axis_names: list[str]) -> None:
        if len(axis_names) <= 1:
            name = axis_names[0] if axis_names else "axis0"
            plot_widget = pg.PlotWidget()
            plot_widget.setLabel("bottom", name)
            plot_widget.setLabel("left", self.value_label)
            self._curve = plot_widget.plot(pen="c")
            d = dock(f"{name.title()} Scan", self.window)
            d.setWidget(plot_widget)
            self.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, d)
            self._first_dock = d
            return

        for name_i, name_j in itertools.combinations(axis_names, 2):
            self._add_panel(name_i, name_j)

        if self._first_dock is not None:
            self._first_dock.raise_()

        if self._crosshair_enabled:
            self._resync_crosshairs()

        self._build_channel_dock()

    def _ensure_detector_axes(self, axis_names: list[str], axis_positions: Optional[list], actuator_axis_count: Optional[int]) -> None:
        """Registers a bound detector's own internal axes (e.g. a
        spectrometer's wavelength axis, a camera's row/col pixel axes)
        the first time `update_data` reveals more axes than the actuator
        alone declares — only knowable from real data, not a static
        declaration like AXIS_RANGES. Deliberately does NOT build a 2D
        projection panel for any pair involving one of these axes:
        multidimensional detector data isn't plotted as extra images, just
        stored (`_axis_names`/`_axis_positions`, used by HDF5 export) and
        made navigable via its own tab in the Channels dock (rebuilt here
        to include it). Runs at most once — a detector's own
        dimensionality doesn't change between runs."""
        if self._detector_axes_known or actuator_axis_count is None or len(axis_names) <= actuator_axis_count:
            return
        self._detector_axes_known = True
        new_names = axis_names[actuator_axis_count:]
        new_positions = axis_positions[actuator_axis_count:] if axis_positions else []
        for name, positions in zip(new_names, new_positions):
            self._axis_positions[name] = list(positions)
            self._axis_names.append(name)

        self._build_channel_dock()

    # ---- Channels dock: one 1D projection + region selector per axis ----

    def _build_channel_dock(self) -> None:
        """(Re)builds the "Channels" dock — one tab per axis in
        `_axis_names` (actuator or detector-internal alike), each a real
        `pg.PlotWidget` (not a blank range strip) showing that axis's own
        1D projection (`components.nd_math.compute_1d_projection`) with a draggable
        `pg.LinearRegionItem` over the curve for that axis's own
        selection ("for each dimension you show a 1D plot of the average
        data over this rectangle, and you can keep that dynamic range
        selection over the 1D plot... into tabs where you can select
        [the] dimension in a tab"). Safe to call again (e.g. once
        `_ensure_detector_axes` reveals more axes) — rebuilds from
        scratch each time rather than trying to patch in new tabs, since
        a fresh `pg.PlotWidget`/region pair per axis is cheap and this
        only happens up to once per detector-axis-discovery."""
        if len(self._axis_names) < 2:
            return  # nothing to project over yet
        if self._channel_dock is None:
            self._channel_tab_widget = QTabWidget()
            # Only the VISIBLE tab's 1D projection is ever computed (see
            # _submit_projection_request) — recomputing every tab on every
            # refresh multiplies the already-expensive nanmean reduction
            # by the axis count for tabs nobody's looking at. Switching
            # tabs needs its own fresh request since the newly-shown one
            # may be stale (last computed whenever it was last visible).
            self._channel_tab_widget.currentChanged.connect(lambda _i: self._submit_projection_request())
            self._channel_dock = dock("Channels", self.window)
            self._channel_dock.setWidget(self._channel_tab_widget)
            self.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._channel_dock)
        else:
            self._channel_tab_widget.clear()
        self._channel_tabs = {}

        for name in self._axis_names:
            positions = self._axis_positions[name]
            lo, hi = min(positions), max(positions)
            self._box_half_width.setdefault(name, self._axis_span(name) * 0.03)
            self._selection.setdefault(name, self._selection_default(name, lo, hi))

            plot_widget = pg.PlotWidget()
            plot_widget.setLabel("bottom", name)
            plot_widget.setLabel("left", self.value_label)
            curve = plot_widget.plot(pen="c")
            region = pg.LinearRegionItem(values=self._selection[name])
            region.setBounds((lo, hi))
            plot_widget.addItem(region)
            region.sigRegionChangeFinished.connect(
                lambda _r, name=name, region=region: self._on_channel_region_changed(name, region)
            )
            self._channel_tabs[name] = {"plot_item": plot_widget, "curve": curve, "region": region}
            self._channel_tab_widget.addTab(plot_widget, name)

        self._submit_projection_request()

    def _selection_default(self, name: str, lo: float, hi: float) -> tuple[float, float]:
        """An actuator axis's default selection is centered on its
        current target, +/- its (already-known-or-defaulted) box
        half-width — matching whatever its 2D panel's crosshair box
        already shows; a detector-internal axis (no box, no position) just
        starts at its full range."""
        if name in self._actuator_axis_names:
            center = self._position.get(name, (lo + hi) / 2)
            half = self._box_half_width.get(name, (hi - lo) * 0.03)
            return (center - half, center + half)
        return (lo, hi)

    def _on_channel_region_changed(self, name: str, region: pg.LinearRegionItem) -> None:
        """A Channels-dock tab's own region was dragged — "the ROIs that
        you can move across the plot". For an actuator axis, this is
        just another way to set the SAME position+box-half-width the
        crosshair already controls (so dragging this region moves and
        resizes the matching 2D panel(s), and vice versa); a detector-
        internal axis has no crosshair at all, so this is the only way to
        narrow it."""
        lo, hi = region.getRegion()
        self._selection[name] = (lo, hi)
        if name in self._actuator_axis_names:
            center, half = (lo + hi) / 2, (hi - lo) / 2
            self._position[name] = center
            self._box_half_width[name] = half
            self._resync_crosshairs()
            self._resync_box_sizes()
            if self._on_position_changed is not None:
                self._on_position_changed(name, center)
        self._submit_projection_request()

    def _active_channel_tab_name(self) -> Optional[str]:
        """Which Channels-dock axis tab is actually visible right now —
        only this one's 1D projection gets (re)computed on a refresh (see
        _submit_projection_request); the rest stay showing whatever they
        last had until the user actually switches to them (the
        currentChanged connection in _build_channel_dock)."""
        if self._channel_tab_widget is None:
            return None
        widget = self._channel_tab_widget.currentWidget()
        for name, tab in self._channel_tabs.items():
            if tab["plot_item"] is widget:
                return name
        return None

    def _submit_projection_request(self) -> None:
        """Hands the current state to the background NDProjectionComputer
        — either a fresh update_data() frame (self._pending_flat_data,
        set just before this is called) or a re-projection of the
        already-parsed self._array with a changed selection (crosshair
        drag, channel region drag, tab switch, add_crosshair, ...).
        Either way the O(array-size) work happens off the GUI thread;
        _on_projection_ready applies the (cheap) result once it's back."""
        tab_name = self._active_channel_tab_name()
        request: dict[str, Any] = {
            "axis_positions": dict(self._axis_positions),
            "selections": dict(self._selection),
            "panel_keys": list(self._panels.keys()),
            "tab_keys": [tab_name] if tab_name else [],
        }
        if self._pending_flat_data is not None:
            request["flat_data"] = self._pending_flat_data
            request["shape"] = self._pending_shape
            request["active"] = self._pending_active
            self._pending_flat_data = None
            self._pending_shape = None
            self._pending_active = None
        elif self._array is not None and self._array_axis_names is not None:
            request["array"] = self._array
            request["active"] = self._array_axis_names
        else:
            return  # nothing to project yet — no frame has ever arrived
        self._computer.submit(request)

    def _on_projection_ready(self, result: dict) -> None:
        """Applies an NDProjectionComputer result — cheap, GUI-thread-only
        widget updates; all the expensive numpy work already happened on
        the background thread."""
        if result["request_id"] != self._computer.latest_request_id:
            return  # a newer request was submitted before this one came back — drop it
        self._array = result["array"]
        self._array_axis_names = result["active"]
        for (name_i, name_j), projected in result["panels"].items():
            panel = self._panels.get((name_i, name_j))
            if panel is None:
                continue
            first = not self._panel_has_data.get((name_i, name_j), False)
            self._panel_has_data[(name_i, name_j)] = True
            panel.set_image(projected, first_frame=first)
            panel.set_extent(self._axis_positions[name_i], self._axis_positions[name_j])
        for name, (x, y) in result["tabs"].items():
            tab = self._channel_tabs.get(name)
            if tab is None:
                continue
            tab["curve"].setData(x, [float("nan") if v is None else v for v in y])
            selection = self._selection.get(name)
            if selection is not None:
                region = tab["region"]
                region.blockSignals(True)
                region.setRegion(selection)
                region.blockSignals(False)

    def update_data(
        self, flat_data: Any, shape: Any, axis_names: Any = None, axis_positions: Any = None,
        actuator_axis_count: Any = None,
    ) -> None:
        if not flat_data or not shape:
            return
        shape = [int(s) for s in shape]
        if len(flat_data) != int(np.prod(shape)):
            return  # mid-scan partial frame whose size doesn't match its own declared shape yet — skip

        active = list(axis_names) if axis_names else self._axis_names[: len(shape)]
        axis_positions = list(axis_positions) if axis_positions else None
        self._ensure_detector_axes(
            active, axis_positions, int(actuator_axis_count) if actuator_axis_count is not None else None
        )
        if axis_positions:
            # A run's actual range can be narrower than (or offset from)
            # the eagerly-declared AXIS_RANGES this view was built from
            # (e.g. edited in Axes Control since) — keep our cached
            # positions fresh so extents/selectors track the real thing.
            for name, positions in zip(active, axis_positions):
                self._axis_positions[name] = list(positions)

        if len(active) <= 1:
            # Small/rare fallback (a single declared axis, no projection
            # panels involved at all) — parsed synchronously; nowhere near
            # the expensive multi-panel/multi-tab case this class exists
            # for, so no need to route it through the background computer.
            array = parse_flat_data(flat_data, shape)
            if array is None:
                return
            self._array = array
            self._array_axis_names = active
            if self._curve is not None:
                x = self._axis_positions.get(active[0], list(range(shape[0]))) if active else list(range(shape[0]))
                self._curve.setData(x, array)
            return

        self._pending_flat_data = flat_data
        self._pending_shape = shape
        self._pending_active = active
        self._submit_projection_request()

    # ---- crosshair: one per actuator-actuator panel, coupled through a shared position ----

    def add_crosshair(self, on_move: Callable[[dict], None]) -> None:
        """Adds a synced crosshair to every actuator-actuator projection
        panel (never a panel involving a detector-internal axis — see
        class docstring) — dragging any one panel's crosshair moves that
        panel's two axes; every other panel sharing either axis updates
        to match (see `_on_panel_changed`). `on_move(changes)` is called
        (debounced) with just the `{axis_name: value}` pair that changed
        — e.g. `{"x": 1.2, "y": -0.4}` — not the whole position, the same
        2-key-write contract as `Image2DResultView.add_crosshair`. Panels
        already exist (built eagerly in `__init__`), so this applies
        immediately — no deferral needed."""
        self._crosshair_enabled = True
        self._crosshair_on_move = on_move
        for (name_i, name_j), panel in self._panels.items():
            if panel._crosshair is not None:
                continue
            if name_i in self._actuator_axis_names and name_j in self._actuator_axis_names:
                self._add_panel_crosshair(name_i, name_j, panel)
        self._resync_crosshairs()
        self._submit_projection_request()

    def _schedule_refresh(self) -> None:
        """Coalesces bursts of drag-tick-driven refreshes — see
        `_refresh_timer`'s docstring in __init__."""
        self._refresh_timer.start()

    def _on_panel_changed(self, name_i: str, name_j: str, x: float, y: float) -> None:
        self._position[name_i] = x
        self._position[name_j] = y
        self._update_selection_from_box(name_i)
        self._update_selection_from_box(name_j)
        self._resync_crosshairs(skip=(name_i, name_j))
        self._schedule_refresh()
        if self._on_position_changed is not None:
            self._on_position_changed(name_i, x)
            self._on_position_changed(name_j, y)

    def _on_panel_moved(self, name_i: str, name_j: str, x: float, y: float) -> None:
        if self._crosshair_on_move is not None:
            self._crosshair_on_move({name_i: x, name_j: y})

    def _on_panel_box_resized(self, name_i: str, name_j: str, half_i: float, half_j: float) -> None:
        """A panel's crosshair box was resized — "the size of the square
        in the crosshair... should define the scanning range" (now, more
        generally, the SELECTED range for that axis wherever it's
        projected/plotted). Harmonizes both axes' half-widths across
        every OTHER panel that shares either one, updates `_selection`,
        and refreshes every 2D panel and every Channels-dock tab that
        projects over either axis — the box IS the selection, not a
        cosmetic decoration of it."""
        self._box_half_width[name_i] = half_i
        self._box_half_width[name_j] = half_j
        self._update_selection_from_box(name_i)
        self._update_selection_from_box(name_j)
        self._resync_box_sizes(skip=(name_i, name_j))
        self._schedule_refresh()

    def _resync_box_sizes(self, skip: Optional[tuple[str, str]] = None) -> None:
        for (name_i, name_j), panel in self._panels.items():
            if (name_i, name_j) == skip:
                continue
            hw_i = self._box_half_width.get(name_i)
            hw_j = self._box_half_width.get(name_j)
            if hw_i is not None and hw_j is not None:
                panel.set_crosshair_box_size(hw_i, hw_j)

    def _resync_crosshairs(self, skip: Optional[tuple[str, str]] = None) -> None:
        for (name_i, name_j), panel in self._panels.items():
            x = self._position.get(name_i)
            y = self._position.get(name_j)
            if x is not None and y is not None:
                panel.position_label.setText(f"{name_i} = {x:.4g}, {name_j} = {y:.4g}")
            if (name_i, name_j) == skip or x is None or y is None:
                continue
            panel.set_crosshair_pos(x, y)

    def set_position(self, positions: dict[str, float]) -> None:
        """Explicit target-position update (e.g. HOLD_POSITIONS changed
        elsewhere) — repositions every panel's crosshair to match. NOT
        driven by live actuator polling (see class docstring: this
        tracks the commanded target, not a read-back), so it's never
        called during an active scan — the crosshair just stays wherever
        it last was. A no-op before add_crosshair()."""
        if not self._crosshair_enabled:
            return
        self._position.update(positions)
        for name in positions:
            self._update_selection_from_box(name)
        self._resync_crosshairs()
        self._submit_projection_request()

    def show_crosshair(self) -> None:
        for panel in self._panels.values():
            panel.show_crosshair()

    def hide_crosshair(self) -> None:
        for panel in self._panels.values():
            panel.hide_crosshair()

    def set_auto_level(self, auto_level: bool) -> None:
        self._auto_level = auto_level
        for panel in self._panels.values():
            panel.set_auto_level(auto_level)

    def stop(self) -> None:
        """Shuts down the background projection thread — call once, when
        this view's window is closing (see workflow_window.py's
        closeEvent). Not needed between runs of the same window."""
        self._computer.stop()

    @property
    def panels(self) -> dict[tuple[str, str], _ScanImagePanel]:
        """{(axis_i, axis_j): panel} for every currently-built 2D panel —
        e.g. used by workflow_window.py's "Save All" action."""
        return dict(self._panels)

    @property
    def first_dock(self):
        """The first scan-panel QDockWidget built, if any — used by
        workflow_window.py to split the Optimizer dock directly below the
        left-hand scan-panel tab group."""
        return self._first_dock

    def axis_box_full_width(self, name: str) -> Optional[float]:
        """This axis's current selected-range full width (its crosshair
        box's full width, for an actuator axis; its Channels-dock tab
        region's full width otherwise) — `OptimizerSettingsDialog` reads
        this to pre-fill its own Range field, so the dialog and the green
        rectangle always agree on what's currently selected."""
        selection = self._selection.get(name)
        if selection is None:
            return None
        lo, hi = selection
        return hi - lo

    def set_axis_box_full_width(self, name: str, full_width: float) -> None:
        """External range update for one axis (`OptimizerSettingsDialog`'s
        own Range field) — "there is a link between what you put in the
        settings window and... the green rectangle": pushes straight into
        the same `_box_half_width`/`_selection` state the crosshair box
        and Channels-dock tab region both read from, then resyncs both
        (a no-op for the box on an axis with no panel at all — e.g. a
        detector-internal axis, where only the Channels-dock tab shows
        the effect)."""
        half = max(full_width, 1e-9) / 2
        self._box_half_width[name] = half
        if name in self._actuator_axis_names:
            self._update_selection_from_box(name)
            self._resync_box_sizes()
        else:
            lo, hi = self._selection.get(name, (0.0, 0.0))
            center = (lo + hi) / 2
            self._selection[name] = (center - half, center + half)
        self._submit_projection_request()


# ---- RESULT_UI["type"] -> result-view dispatch ----
#
# Registered through `components/base.py`'s one registry, in the "result"
# context. workflow_window.py's `_add_result_view`/`_on_execution_state`
# used to be two separately hand-maintained if/elif chains over the same
# four type strings; both do one lookup instead, and adding a fifth result
# kind means adding one adapter subclass here.
#
# These briefly had a registry and a metaclass of their own, on the
# grounds that a result view has no per-instrument `InstrumentContext` and
# so is structurally unlike a `UIComponent`. That much is true, and it is
# why this stays a separate base class with its own build/update shape —
# but a different shape is not a different *question*, and the question a
# registry answers ("which class does this `type` string mean?") is the
# same one in both cases. See base.py.


class ResultViewAdapter(metaclass=ComponentMeta):
    """One subclass per `RESULT_UI["type"]` string, auto-registered the
    moment it is defined — adding a 5th result kind means adding one
    adapter subclass here, not editing workflow_window.py's dispatch."""

    #: Registered under ("result", component_type) — see base.ComponentMeta.
    context: str = "result"

    #: The `RESULT_UI["type"]` string this adapter handles — must be set
    #: on every concrete subclass (an empty string never registers).
    component_type: str = ""

    #: True only for a view that manages its own QDockWidget(s) directly
    #: on the window (currently just NDScanResultView) — workflow_window.py
    #: skips wrapping the returned view in its own generic "Result" dock
    #: when this is set.
    manages_own_docks: bool = False

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        """Constructs and returns the view widget (or None to build
        nothing — e.g. NDScanResultViewAdapter when the workflow declares
        no AXIS_RANGES). `window` is the owning WorkflowWindow, needed by
        NDScanResultViewAdapter to attach docks and read
        omniscan-specific window state; every other adapter ignores it."""
        raise NotImplementedError

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        """Applies one `report_progress()`/`last_results` snapshot
        (`source`) to `view`, using `result_ui`'s `*_key` names (or a
        dataclass-derived equivalent — see core/workflow/result_types.py)
        to pull the right fields out of it."""
        raise NotImplementedError


class Image2DResultViewAdapter(ResultViewAdapter):
    component_type = "image2d"

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        return Image2DResultView(result_ui.get("value_label", "Value"))

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        view.update_data(
            source.get(result_ui.get("value_key")),
            source.get(result_ui.get("x_key")),
            source.get(result_ui.get("y_key")),
        )


class SpectrumResultViewAdapter(ResultViewAdapter):
    component_type = "spectrum"

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        return SpectrumResultView(result_ui.get("x_label", ""), result_ui.get("y_label", ""))

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        view.update_data(source.get(result_ui.get("x_key")), source.get(result_ui.get("y_key")))
        fit_x_key = result_ui.get("fit_x_key")
        fit_y_key = result_ui.get("fit_y_key")
        fit_center_key = result_ui.get("fit_center_key")
        if fit_x_key and fit_y_key:
            view.set_fit(
                source.get(fit_x_key), source.get(fit_y_key),
                source.get(fit_center_key) if fit_center_key else None,
            )


class OdmrResultViewAdapter(ResultViewAdapter):
    component_type = "odmr"

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        return OdmrResultView(result_ui.get("x_label", ""), result_ui.get("y_label", ""))

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        matrix_key = result_ui.get("matrix_key")
        repeat_key = result_ui.get("repeat_key")
        view.update_data(
            source.get(result_ui.get("x_key")), source.get(result_ui.get("y_key")),
            source.get(matrix_key) if matrix_key else None,
            source.get(repeat_key) if repeat_key else None,
        )
        fit_x_key = result_ui.get("fit_x_key")
        fit_y_key = result_ui.get("fit_y_key")
        fit_center_key = result_ui.get("fit_center_key")
        if fit_x_key and fit_y_key:
            view.set_fit(
                source.get(fit_x_key), source.get(fit_y_key),
                source.get(fit_center_key) if fit_center_key else None,
            )


class NDScanResultViewAdapter(ResultViewAdapter):
    component_type = "ndscan"
    manages_own_docks = True

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        if not window._omniscan_axis_ranges:
            window.status_bar.showMessage(
                "This workflow declares an ndscan result but no AXIS_RANGES — nothing to show"
            )
            return None
        crosshair = result_ui.get("crosshair")
        extra_dock = window._build_optimizer_panel(crosshair) if crosshair else None
        return NDScanResultView(
            window, window._omniscan_axis_ranges, result_ui.get("value_label", "Value"),
            hold_positions=window._omniscan_hold_positions, extra_dock_below=extra_dock,
            on_position_changed=lambda axis, value: (
                window.axes_control.set_target(axis, value) if window.axes_control is not None else None
            ),
        )

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        actuator_axis_count_key = result_ui.get("actuator_axis_count_key")
        view.update_data(
            source.get(result_ui.get("value_key")), source.get(result_ui.get("shape_key")),
            source.get(result_ui.get("axis_names_key")), source.get(result_ui.get("axis_positions_key")),
            source.get(actuator_axis_count_key) if actuator_axis_count_key else None,
        )


class PulseSequenceResultView(QWidget):
    """The timing diagram a sequence editor draws — one lane per channel.

    Boxes, not samples, and that is a deliberate limit rather than a
    shortcut. A 2.87 GHz drive inside a 100 ns pi pulse is 287 carrier
    cycles: sampling it for a plot either aliases into a meaningless
    smear or costs more points than the widget can carry, and neither
    answers the question the author actually has, which is *when is each
    channel doing something, and how hard*. So each element is a filled
    box in its channel's lane, exact at any zoom, and the analog ones are
    drawn to the shape's amplitude and labelled with the shape's name.
    Qudi's own editor draws the same picture.

    One point of the sweep at a time. A 50-point Rabi drawn end to end is
    a solid bar with no information in it; the point being previewed is
    the editor's own `PREVIEW_POINT` parameter.

    Segments arrive over the wire as plain dicts (`Segment.to_dict()` in
    core/pulse/sampling.py), so this view holds no pulse objects and needs
    nothing from `core.pulse` imported into the Qt process.
    """

    #: Lane colours, cycled per channel. The laser gets green and the
    #: microwave red wherever those channels are present, because that is
    #: what every optics bench and every NV paper already uses.
    _BY_NAME: ClassVar[dict[str, str]] = {
        "laser": "#4caf50",
        "green": "#4caf50",
        "mw": "#e53935",
        "microwave": "#e53935",
        "gate": "#42a5f5",
        "trigger": "#ffb300",
    }
    _CYCLE = ("#ab47bc", "#26a69a", "#ff7043", "#8d6e63", "#78909c")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.summary = QLabel("No sequence yet")
        self.summary.setStyleSheet("color: #888;")
        layout.addWidget(self.summary)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.showGrid(x=True, y=False, alpha=0.2)
        self.plot_widget.setMouseEnabled(x=True, y=False)
        self.plot_widget.getPlotItem().hideButtons()
        layout.addWidget(self.plot_widget, 1)

        self._axis = self.plot_widget.getAxis("left")
        self._channels: list[str] = []

    def _colour(self, channel: str, index: int) -> str:
        return self._BY_NAME.get(channel, self._CYCLE[index % len(self._CYCLE)])

    def update_data(self, segments: Any, channels: Any = None, duration: Any = None) -> None:
        """Redraw from one result frame.

        Everything is rebuilt each time rather than diffed: a sequence is
        a few dozen boxes and the editor produces one frame per edit, so
        there is nothing here worth the incremental-update machinery the
        live scan views need.
        """
        segments = list(segments or ())
        self.plot_widget.clear()

        if not segments:
            self.summary.setText("No sequence yet")
            self._axis.setTicks(None)
            return

        # Lane order: the channels the result names, so it stays stable
        # across edits even when an element stops using one of them.
        names = list(channels or ())
        for segment in segments:
            if segment.get("channel") not in names:
                names.append(segment.get("channel"))

        lanes = {name: len(names) - 1 - index for index, name in enumerate(names)}
        for index, name in enumerate(names):
            colour = self._colour(name, index)
            base = lanes[name]
            pen = pg.mkPen(colour, width=1)
            brush = pg.mkBrush(pg.mkColor(colour).darker(180))
            # A baseline per lane, so a channel that is low for this whole
            # point still shows as a lane rather than as empty space.
            self.plot_widget.plot(
                [0.0, float(duration or 0.0)], [base, base],
                pen=pg.mkPen(colour, width=1, style=Qt.PenStyle.DotLine),
            )
            for segment in segments:
                if segment.get("channel") != name:
                    continue
                start = float(segment.get("start", 0.0))
                stop = float(segment.get("stop", 0.0))
                height = 0.72
                box = QGraphicsRectItem(
                    QRectF(start, base, max(stop - start, 0.0), height)
                )
                box.setPen(pen)
                box.setBrush(brush)
                self.plot_widget.addItem(box)

        self._axis.setTicks([[(lanes[name], name) for name in names]])
        self.plot_widget.setYRange(-0.4, len(names) - 0.1, padding=0)
        if duration:
            self.plot_widget.setXRange(0.0, float(duration), padding=0.02)

        analog = sorted({s["shape"] for s in segments if s.get("shape")})
        self.summary.setText(
            f"{len(names)} channel(s), {len(segments)} pulse(s), "
            f"{float(duration or 0.0) * 1e6:.3f} us per point"
            + (f" — analog: {', '.join(analog)}" if analog else "")
        )

    # No crosshair on a timing diagram — no-ops so workflow_window.py can
    # call these polymorphically across every result-view type.
    def show_crosshair(self) -> None:
        pass

    def hide_crosshair(self) -> None:
        pass

    def set_auto_level(self, auto_level: bool) -> None:
        pass


class PulseSequenceResultViewAdapter(ResultViewAdapter):
    component_type = "pulse_sequence"

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        return PulseSequenceResultView()

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        view.update_data(
            source.get(result_ui.get("segments_key", "segments")),
            source.get(result_ui.get("channels_key", "channels")),
            source.get(result_ui.get("duration_key", "point_duration")),
        )


class PulsedResultView(QWidget):
    """What a pulsed measurement produced: the curve, and where it came from.

    Two plots, because a pulsed result is two things and showing only the
    first is how a wrong answer survives:

    - **the curve** — one point per swept tau, with Poisson error bars and
      the fit drawn over it. This is the measurement;
    - **the raw record**, summed over every readout, with the extracted
      window shaded on it. This is the step that goes wrong quietly. A
      window that starts fifty nanoseconds early mixes in dark counts and
      costs contrast; one that starts fifty late throws away the photons
      that carry the spin state. Neither raises anything — the curve just
      comes out flatter and the T2 comes out short — so the only defence
      is being able to see it.

    Everything arrives as plain lists (`Extraction.to_dict()` and
    `Analysis.to_dict()`), so this holds no pulse objects and needs
    nothing from `core.pulse` in the Qt process.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.summary = QLabel("No measurement yet")
        self.summary.setStyleSheet("color: #888;")
        layout.addWidget(self.summary)

        self.curve_plot = pg.PlotWidget()
        self.curve_plot.showGrid(x=True, y=True, alpha=0.2)
        self.curve_plot.addLegend(offset=(-10, 10))
        layout.addWidget(self.curve_plot, 3)

        self.record_plot = pg.PlotWidget()
        self.record_plot.setLabel("bottom", "Time in readout", units="s")
        self.record_plot.setLabel("left", "Counts")
        self.record_plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.record_plot, 2)

        self._points = self.curve_plot.plot(
            [], [], pen=pg.mkPen("#42a5f5", width=2),
            symbol="o", symbolSize=5, symbolBrush="#42a5f5", name="measured",
        )
        self._fit_curve = self.curve_plot.plot(
            [], [], pen=pg.mkPen("#e53935", width=2, style=Qt.PenStyle.DashLine),
            name="fit",
        )
        self._errors = pg.ErrorBarItem(x=np.array([]), y=np.array([]), pen="#42a5f5")
        self.curve_plot.addItem(self._errors)

        self._record = self.record_plot.plot([], [], pen=pg.mkPen("#9e9e9e", width=1))
        # Shaded rather than two lines: the window is a region, and a
        # region is what someone has to judge by eye against the pulse.
        self._window = pg.LinearRegionItem(brush=(76, 175, 80, 40), movable=False)
        self._window.setZValue(-10)
        self.record_plot.addItem(self._window)
        self._window.hide()

    def update_data(self, source: dict) -> None:
        tau = _as_list(source.get("tau"))
        curve = _as_list(source.get("curve"))
        analysis = source.get("analysis") or {}
        extraction = source.get("extraction") or {}

        self.curve_plot.setLabel("left", analysis.get("label") or "signal",
                                 units=analysis.get("unit") or None)
        self.curve_plot.setLabel("bottom", source.get("sweep_name") or "tau", units="s")

        pairs = [(x, y) for x, y in zip(tau, curve) if y is not None and np.isfinite(y)]
        xs = np.asarray([p[0] for p in pairs], dtype=float)
        ys = np.asarray([p[1] for p in pairs], dtype=float)
        self._points.setData(xs, ys)

        errors = _as_list(source.get("errors"))[: len(pairs)]
        if len(errors) == len(xs) and len(xs):
            self._errors.setData(
                x=xs, y=ys, height=2 * np.nan_to_num(np.asarray(errors, dtype=float))
            )
            self._errors.show()
        else:
            self._errors.hide()

        fit = source.get("fit")
        if isinstance(fit, dict) and fit.get("curve"):
            self._fit_curve.setData(np.asarray(tau, dtype=float),
                                    np.asarray(fit["curve"], dtype=float))
        else:
            self._fit_curve.setData([], [])

        profile = _as_list(extraction.get("profile"))
        width = float(extraction.get("bin_width_s") or 0.0)
        if profile and width > 0:
            self._record.setData(np.arange(len(profile)) * width,
                                 np.asarray(profile, dtype=float))
            start, stop = extraction.get("window_s") or (0.0, 0.0)
            self._window.setRegion((float(start), float(stop)))
            self._window.setVisible(bool(extraction.get("found")))
        self.summary.setText(self._summary(source, analysis, extraction, fit))

    @staticmethod
    def _summary(source: dict, analysis: dict, extraction: dict, fit: Any) -> str:
        parts = [
            f"{source.get('sequence', '?')}",
            f"{source.get('completed', 0)}/{source.get('total', 0)} checkpoints",
        ]
        if analysis.get("method"):
            parts.append(f"analysed by {analysis['method']}")
        if extraction.get("method"):
            found = "" if extraction.get("found", True) else " (nothing found yet)"
            parts.append(f"extracted by {extraction['method']}{found}")
        if isinstance(fit, dict):
            if "pi_pulse" in fit:
                parts.append(
                    f"pi = {fit['pi_pulse'] * 1e9:.1f} ns, "
                    f"period = {fit['period'] * 1e9:.1f} ns"
                )
            elif "decay" in fit:
                parts.append(f"decay = {fit['decay'] * 1e6:.2f} us")
        elif source.get("fit_model") not in (None, "", "none"):
            parts.append("fit did not converge")
        return " · ".join(parts)


def _as_list(value: Any) -> list:
    """A wire value as a plain list — `None` and scalars become empty."""
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else []


class PulsedResultViewAdapter(ResultViewAdapter):
    component_type = "pulsed"

    @staticmethod
    def build(window: Any, result_ui: dict) -> Any:
        return PulsedResultView()

    @staticmethod
    def update(view: Any, result_ui: dict, source: dict) -> None:
        view.update_data(source)
