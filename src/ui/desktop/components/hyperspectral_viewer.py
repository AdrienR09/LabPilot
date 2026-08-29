"""ND detector combined image + spectrum viewer (hyperspex-style).

Two linked views for a 3D (x, y, spectral) hyperspectral cube — an image
(mean projection over a wavelength band) and a spectrum (mean over a
spatial ROI) — each updating the other exactly like
github.com/AdrienR09/hyperspex: drag the image's rectangular ROI to
change which pixels the spectrum averages over; drag the spectrum's
linear region to change which wavelength band the image averages over.

Built directly on plain pyqtgraph (`ImageView`/`PlotWidget`/`RectROI`/
`LinearRegionItem`) rather than pymodaq's `Viewer2D`/`Viewer1D` — those
route ROI interaction through a more elaborate lineout/filter pipeline
that doesn't map cleanly onto "recompute the other view's full data",
whereas hyperspex's own real implementation is plain pyqtgraph too.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

from components.base import UIComponent
from components.widgets import dock

pg.setConfigOption("imageAxisOrder", "row-major")  # match numpy's (row, col) convention


class HyperspectralViewerComponent(UIComponent):
    component_type = "hyperspectral_viewer"
    default_params = {"image_dock_title": "Image", "spectrum_dock_title": "Spectrum"}

    def build(self) -> None:
        window = self.window
        self._cube = None  # (ny, nx, nw), set on first on_data()

        image_content = QWidget()
        image_layout = QVBoxLayout(image_content)
        image_layout.setContentsMargins(4, 4, 4, 4)
        self.image_view = pg.ImageView()
        self.image_view.ui.roiBtn.hide()
        self.image_view.ui.menuBtn.hide()
        image_layout.addWidget(self.image_view)
        self.image_roi = pg.RectROI([0, 0], [5, 5], pen="r")
        self.image_view.getView().addItem(self.image_roi)
        self.image_roi.sigRegionChangeFinished.connect(self._on_image_roi_changed)

        d_img = dock(self.params["image_dock_title"], window)
        d_img.setWidget(image_content)
        window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, d_img)

        spectrum_content = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_content)
        spectrum_layout.setContentsMargins(4, 4, 4, 4)
        self.spectrum_plot = pg.PlotWidget()
        self.spectrum_curve = self.spectrum_plot.plot(pen="w")
        spectrum_layout.addWidget(self.spectrum_plot)
        self.spectrum_region = pg.LinearRegionItem()
        self.spectrum_plot.addItem(self.spectrum_region)
        self.spectrum_region.sigRegionChangeFinished.connect(self._on_spectrum_region_changed)

        d_spec = dock(self.params["spectrum_dock_title"], window)
        d_spec.setWidget(spectrum_content)
        window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, d_spec)

    # ---- ROI-linked recompute ----

    def _on_image_roi_changed(self) -> None:
        if self._cube is not None:
            self._update_spectrum_from_roi()

    def _on_spectrum_region_changed(self) -> None:
        if self._cube is not None:
            self._update_image_from_band()

    def _update_spectrum_from_roi(self) -> None:
        cube = self._cube
        ny, nx, _nw = cube.shape
        pos = self.image_roi.pos()
        size = self.image_roi.size()
        x0, y0 = int(max(0, pos.x())), int(max(0, pos.y()))
        x1, y1 = int(min(nx, pos.x() + size.x())), int(min(ny, pos.y() + size.y()))
        if x1 <= x0 or y1 <= y0:
            return
        spectrum = cube[y0:y1, x0:x1, :].mean(axis=(0, 1))
        self.spectrum_curve.setData(spectrum)

    def _update_image_from_band(self) -> None:
        cube = self._cube
        nw = cube.shape[2]
        lo, hi = self.spectrum_region.getRegion()
        i0, i1 = int(max(0, lo)), int(min(nw, hi))
        if i1 <= i0:
            i1 = i0 + 1
        image = cube[:, :, i0:i1].mean(axis=2)
        self.image_view.setImage(image, autoRange=False, autoLevels=False)

    def on_data(self, data: dict) -> None:
        ctx = self.ctx
        if ctx.value_key is None or ctx.value_key not in data:
            return
        cube = np.asarray(data[ctx.value_key], dtype=float)
        if cube.ndim != 3:
            return
        first_time = self._cube is None
        self._cube = cube
        ny, nx, nw = cube.shape

        if first_time:
            self.image_roi.setPos([0, 0])
            self.image_roi.setSize([nx, ny])
            self.spectrum_region.setRegion([0, nw])
            self.image_view.setImage(cube.mean(axis=2), autoRange=True, autoLevels=True)
            self.spectrum_curve.setData(cube.mean(axis=(0, 1)))
        else:
            self._update_image_from_band()
            self._update_spectrum_from_roi()
        ctx.set_info(f"cube {cube.shape} · Max: {np.max(cube):.0f}")
