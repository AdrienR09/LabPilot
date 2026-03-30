"""ImageWindow - Real-time image display with histogram and ROI.

Specialized Qt window for displaying 2D scientific images with:
- Live frame updates from EventBus (cameras, detectors)
- Intensity histogram with adjustable levels
- ROI (Region of Interest) selection and statistics
- False color mapping with multiple colormaps
- Export to TIFF/PNG functionality
- Pixel-level inspection and coordinates
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pyqtgraph as pg
    from PyQt6.QtGui import QAction, QCloseEvent
    from PyQt6.QtWidgets import QToolBar

    from labpilot_core.core.events import Event

from labpilot_core.qt.windows._base import LabPilotWindow

__all__ = ["ImageWindow"]

log = logging.getLogger(__name__)


class ImageWindow(LabPilotWindow):
    """Real-time image display window.

    Features:
    - pyqtgraph ImageView with built-in histogram and colormap
    - Live updates with ImageItem.setImage() per READING event
    - ROI selection with statistics overlay (mean, max, std)
    - Toolbar with colormap selector, false-color toggle, export
    - Pixel coordinate display and zoom functionality
    - Auto-scaling and manual level adjustment

    Example:
        >>> window = ImageWindow(
        ...     window_id="cam_main",
        ...     title="Live Camera",
        ...     source="camera.frame",
        ...     colormap="inferno",
        ...     show_roi=True
        ... )
    """

    def __init__(
        self,
        window_id: str,
        title: str,
        source: str,
        colormap: str = "inferno",
        show_histogram: bool = True,
        show_roi: bool = False,
    ) -> None:
        """Initialize image window.

        Args:
            window_id: Unique window identifier.
            title: Window title.
            source: Data source ("device.parameter").
            colormap: Initial colormap name.
            show_histogram: Whether to show intensity histogram.
            show_roi: Whether to show ROI selection overlay.
        """
        # Initialize Qt main window
        from PyQt6.QtWidgets import QMainWindow
        QMainWindow.__init__(self)

        # Initialize LabPilot window
        LabPilotWindow.__init__(self, window_id, [source])

        # Store parameters
        self.source = source
        self.colormap = colormap
        self.show_histogram = show_histogram
        self.show_roi = show_roi

        # Window setup
        self.setWindowTitle(title)
        self.resize(900, 700)

        # Data storage
        self.current_frame: np.ndarray | None = None
        self.frame_stats: dict[str, float] = {}

        # UI components (will be initialized in _setup_ui)
        self.image_view: pg.ImageView | None = None
        self.roi_item: pg.ROI | None = None
        self.toolbar: QToolBar | None = None

        # Actions
        self.colormap_actions: dict[str, QAction] = {}
        self.autoscale_action: QAction | None = None
        self.roi_action: QAction | None = None
        self.export_action: QAction | None = None

        # Initialize UI
        self._setup_ui()
        self._apply_labpilot_style()

        log.info(f"Created image window: {window_id} for source: {source}")

    def _setup_ui(self) -> None:
        """Setup Qt UI components."""
        try:
            import pyqtgraph as pg
            from PyQt6.QtWidgets import QVBoxLayout, QWidget

            # Create central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            # Create image view widget
            self.image_view = pg.ImageView()

            # Configure histogram display
            if not self.show_histogram:
                self.image_view.ui.histogram.hide()
                self.image_view.ui.roiBtn.hide()
                self.image_view.ui.menuBtn.hide()

            # Set initial colormap
            self._set_colormap(self.colormap)

            layout.addWidget(self.image_view)

            # Create ROI if requested
            if self.show_roi:
                self._setup_roi()

            # Create toolbar
            self._setup_toolbar()

        except ImportError:
            log.error("pyqtgraph not available - image window will not function")
            raise
        except Exception as e:
            log.error(f"Failed to setup image window UI: {e}")
            raise

    def _setup_roi(self) -> None:
        """Setup ROI (Region of Interest) overlay."""
        try:
            import pyqtgraph as pg

            if self.image_view is None:
                return

            # Create rectangular ROI
            self.roi_item = pg.RectROI(
                pos=(50, 50),
                size=(100, 100),
                pen=pg.mkPen(color='#ff0044', width=2)
            )

            # Add ROI to image view
            self.image_view.addItem(self.roi_item)

            # Connect ROI change signal
            self.roi_item.sigRegionChanged.connect(self._update_roi_stats)

            log.debug("Setup ROI overlay")

        except Exception as e:
            log.error(f"Failed to setup ROI: {e}")

    def _setup_toolbar(self) -> None:
        """Setup window toolbar with actions."""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QAction
            from PyQt6.QtWidgets import QToolBar

            self.toolbar = QToolBar("Image Controls")
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

            # Colormap selection
            self._setup_colormap_actions()

            self.toolbar.addSeparator()

            # Auto-scale
            self.autoscale_action = QAction("Auto Scale", self)
            self.autoscale_action.triggered.connect(self._auto_scale)
            self.toolbar.addAction(self.autoscale_action)

            # ROI toggle
            self.roi_action = QAction("ROI", self)
            self.roi_action.setCheckable(True)
            self.roi_action.setChecked(self.show_roi)
            self.roi_action.triggered.connect(self._toggle_roi)
            self.toolbar.addAction(self.roi_action)

            # Export
            self.export_action = QAction("Export TIFF", self)
            self.export_action.triggered.connect(self._export_tiff)
            self.toolbar.addAction(self.export_action)

        except Exception as e:
            log.error(f"Failed to setup toolbar: {e}")

    def _setup_colormap_actions(self) -> None:
        """Setup colormap selection actions."""
        try:
            from PyQt6.QtGui import QAction, QActionGroup

            # Available colormaps (pyqtgraph built-ins)
            colormaps = [
                "thermal", "flame", "yellowy", "bipolar", "spectrum",
                "cyclic", "greyclip", "grey", "viridis", "inferno",
                "plasma", "magma"
            ]

            # Create action group for exclusive selection
            colormap_group = QActionGroup(self)

            for cmap_name in colormaps:
                action = QAction(cmap_name.title(), self)
                action.setCheckable(True)
                action.setChecked(cmap_name == self.colormap)
                action.triggered.connect(lambda checked, name=cmap_name: self._set_colormap(name))

                colormap_group.addAction(action)
                self.toolbar.addAction(action)
                self.colormap_actions[cmap_name] = action

        except Exception as e:
            log.error(f"Failed to setup colormap actions: {e}")

    def _set_colormap(self, colormap_name: str) -> None:
        """Set image colormap.

        Args:
            colormap_name: Name of colormap to apply.
        """
        try:
            if self.image_view is None:
                return

            import pyqtgraph as pg

            # Set colormap on histogram widget
            self.image_view.setColorMap(pg.colormap.get(colormap_name, source='matplotlib'))
            self.colormap = colormap_name

            log.debug(f"Set colormap: {colormap_name}")

        except Exception as e:
            log.error(f"Failed to set colormap {colormap_name}: {e}")

    def _auto_scale(self) -> None:
        """Auto-scale image levels to fit data."""
        try:
            if self.image_view is not None and self.current_frame is not None:
                self.image_view.autoLevels()
                log.debug("Auto-scaled image levels")
        except Exception as e:
            log.error(f"Failed to auto-scale: {e}")

    def _toggle_roi(self) -> None:
        """Toggle ROI visibility."""
        try:
            roi_enabled = self.roi_action.isChecked()

            if roi_enabled and self.roi_item is None:
                self._setup_roi()
            elif not roi_enabled and self.roi_item is not None:
                if self.image_view is not None:
                    self.image_view.removeItem(self.roi_item)
                self.roi_item = None

            self.show_roi = roi_enabled
            log.debug(f"ROI visibility: {roi_enabled}")

        except Exception as e:
            log.error(f"Failed to toggle ROI: {e}")

    def _update_roi_stats(self) -> None:
        """Update ROI statistics display."""
        try:
            if (self.roi_item is None or
                self.current_frame is None or
                self.image_view is None):
                return

            # Get ROI bounds
            roi_bounds = self.roi_item.parentBounds()
            x1, y1 = int(roi_bounds.topLeft().x()), int(roi_bounds.topLeft().y())
            x2, y2 = int(roi_bounds.bottomRight().x()), int(roi_bounds.bottomRight().y())

            # Clip to image bounds
            h, w = self.current_frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                return

            # Extract ROI data
            roi_data = self.current_frame[y1:y2, x1:x2]

            # Calculate statistics
            self.frame_stats.update({
                'roi_mean': float(np.mean(roi_data)),
                'roi_max': float(np.max(roi_data)),
                'roi_std': float(np.std(roi_data)),
                'roi_sum': float(np.sum(roi_data)),
            })

            # Update window title with stats
            stats_str = f"Mean: {self.frame_stats['roi_mean']:.1f}, Max: {self.frame_stats['roi_max']:.0f}"
            title_base = self.windowTitle().split(' [')[0]  # Remove existing stats
            self.setWindowTitle(f"{title_base} [{stats_str}]")

        except Exception as e:
            log.error(f"Failed to update ROI stats: {e}")

    def _export_tiff(self) -> None:
        """Export current frame to TIFF file."""
        try:
            if self.current_frame is None:
                log.warning("No frame to export")
                return

            from PyQt6.QtWidgets import QFileDialog

            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Frame TIFF",
                f"frame_{self.window_id}.tiff",
                "TIFF files (*.tiff *.tif);;PNG files (*.png);;All files (*.*)"
            )

            if not file_path:
                return

            # Export using numpy/PIL
            try:
                from PIL import Image

                # Convert to uint16 if needed
                if self.current_frame.dtype != np.uint16:
                    # Scale to uint16 range
                    frame_norm = self.current_frame.astype(float)
                    frame_norm = (frame_norm - frame_norm.min()) / (frame_norm.max() - frame_norm.min())
                    frame_uint16 = (frame_norm * 65535).astype(np.uint16)
                else:
                    frame_uint16 = self.current_frame

                # Save with PIL
                img = Image.fromarray(frame_uint16)
                img.save(file_path)

            except ImportError:
                # Fallback to numpy save
                np.save(file_path.replace('.tiff', '.npy'), self.current_frame)

            log.info(f"Exported frame to: {file_path}")

        except Exception as e:
            log.error(f"Failed to export TIFF: {e}")

    def _update_from_event(self, event: Event) -> None:
        """Update image from EventBus event (called in Qt thread).

        Args:
            event: Event containing frame data.
        """
        try:
            # Extract data from event
            data = self._parse_source_data(event, self.source)
            if data is None:
                return

            # Handle different data formats
            if isinstance(data, dict):
                # Data dict with frame
                frame = data.get('frame') or data.get('image') or data.get('data')
            elif isinstance(data, np.ndarray):
                # Raw frame array
                frame = data
            else:
                log.warning(f"Unsupported data format: {type(data)}")
                return

            if frame is None:
                return

            # Convert to numpy array
            frame = np.asarray(frame)

            # Ensure 2D
            if frame.ndim == 1:
                # Try to reshape square
                size = int(np.sqrt(len(frame)))
                if size * size == len(frame):
                    frame = frame.reshape(size, size)
                else:
                    log.warning(f"Cannot reshape 1D array of length {len(frame)} to 2D")
                    return
            elif frame.ndim > 2:
                # Take first 2D slice
                frame = frame[..., 0] if frame.shape[-1] == 1 else frame[:, :, 0]

            # Store frame
            self.current_frame = frame

            # Update image display
            if self.image_view is not None:
                # Set image data (transpose for correct orientation)
                self.image_view.setImage(frame.T, autoLevels=False, autoRange=False)

            # Update ROI stats if active
            if self.roi_item is not None:
                self._update_roi_stats()

            log.debug(f"Updated image display: {frame.shape} {frame.dtype}")

        except Exception as e:
            log.error(f"Failed to update image from event: {e}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        log.info(f"Closing image window: {self.window_id}")

        # Call parent close handler
        LabPilotWindow.closeEvent(self, event)
