"""SpectrumWindow - Real-time spectroscopy plotting with pyqtgraph.

Specialized Qt window for displaying wavelength/frequency spectra with:
- Live data updates from EventBus
- Peak finding and annotation
- Log/linear Y-axis toggle
- Export to CSV functionality
- Wavelength calibration overlay
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

__all__ = ["SpectrumWindow"]

log = logging.getLogger(__name__)


class SpectrumWindow(LabPilotWindow):
    """Real-time spectrum plotting window.

    Features:
    - pyqtgraph PlotWidget with wavelength/frequency axis
    - Rolling update with PlotCurveItem.setData() per READING event
    - Optional peak finder overlay with InfiniteLine at peak position
    - Toolbar with log Y toggle, auto-scale, export CSV, colormap
    - Thread-safe updates from EventBus

    Example:
        >>> window = SpectrumWindow(
        ...     window_id="spec_main",
        ...     title="Live Spectrum",
        ...     source="spectrometer.intensities",
        ...     xlabel="Wavelength (nm)",
        ...     show_peak=True
        ... )
    """

    def __init__(
        self,
        window_id: str,
        title: str,
        source: str,
        xlabel: str = "Wavelength (nm)",
        ylabel: str = "Intensity (counts)",
        show_peak: bool = False,
        log_y: bool = False,
    ) -> None:
        """Initialize spectrum window.

        Args:
            window_id: Unique window identifier.
            title: Window title.
            source: Data source ("device.parameter").
            xlabel: X-axis label.
            ylabel: Y-axis label.
            show_peak: Whether to show peak finding overlay.
            log_y: Whether to start with log Y-axis.
        """
        # Initialize Qt main window
        from PyQt6.QtWidgets import QMainWindow
        QMainWindow.__init__(self)

        # Initialize LabPilot window
        LabPilotWindow.__init__(self, window_id, [source])

        # Store parameters
        self.source = source
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.show_peak = show_peak
        self.log_y = log_y

        # Window setup
        self.setWindowTitle(title)
        self.resize(800, 600)

        # Data storage
        self.wavelengths: np.ndarray | None = None
        self.intensities: np.ndarray | None = None
        self.current_peak_pos: float | None = None

        # UI components (will be initialized in _setup_ui)
        self.plot_widget: pg.PlotWidget | None = None
        self.plot_item: pg.PlotCurveItem | None = None
        self.peak_line: pg.InfiniteLine | None = None
        self.toolbar: QToolBar | None = None

        # Actions
        self.log_y_action: QAction | None = None
        self.autoscale_action: QAction | None = None
        self.export_action: QAction | None = None

        # Initialize UI
        self._setup_ui()
        self._apply_labpilot_style()

        log.info(f"Created spectrum window: {window_id} for source: {source}")

    def _setup_ui(self) -> None:
        """Setup Qt UI components."""
        try:
            import pyqtgraph as pg
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QAction
            from PyQt6.QtWidgets import QToolBar, QVBoxLayout, QWidget

            # Create central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            # Create plot widget
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setLabel('bottom', self.xlabel)
            self.plot_widget.setLabel('left', self.ylabel)
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setMouseEnabled(x=True, y=True)

            # Set log Y if requested
            if self.log_y:
                self.plot_widget.setLogMode(x=False, y=True)

            layout.addWidget(self.plot_widget)

            # Create plot curve item
            self.plot_item = pg.PlotCurveItem(
                pen=pg.mkPen(color='#00ff88', width=2),
                name='Spectrum'
            )
            self.plot_widget.addItem(self.plot_item)

            # Create peak line if requested
            if self.show_peak:
                self.peak_line = pg.InfiniteLine(
                    angle=90,
                    pen=pg.mkPen(color='#ff0044', width=2, style=Qt.PenStyle.DashLine),
                    label='Peak'
                )
                self.plot_widget.addItem(self.peak_line)

            # Create toolbar
            self._setup_toolbar()

        except ImportError:
            log.error("pyqtgraph not available - spectrum window will not function")
            raise
        except Exception as e:
            log.error(f"Failed to setup spectrum window UI: {e}")
            raise

    def _setup_toolbar(self) -> None:
        """Setup window toolbar with actions."""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QAction
            from PyQt6.QtWidgets import QToolBar

            self.toolbar = QToolBar("Spectrum Controls")
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

            # Log Y toggle
            self.log_y_action = QAction("Log Y", self)
            self.log_y_action.setCheckable(True)
            self.log_y_action.setChecked(self.log_y)
            self.log_y_action.triggered.connect(self._toggle_log_y)
            self.toolbar.addAction(self.log_y_action)

            # Auto-scale
            self.autoscale_action = QAction("Auto Scale", self)
            self.autoscale_action.triggered.connect(self._auto_scale)
            self.toolbar.addAction(self.autoscale_action)

            # Export CSV
            self.export_action = QAction("Export CSV", self)
            self.export_action.triggered.connect(self._export_csv)
            self.toolbar.addAction(self.export_action)

        except Exception as e:
            log.error(f"Failed to setup toolbar: {e}")

    def _toggle_log_y(self) -> None:
        """Toggle log/linear Y-axis."""
        try:
            if self.plot_widget is not None:
                log_mode = self.log_y_action.isChecked()
                self.plot_widget.setLogMode(x=False, y=log_mode)
                log.debug(f"Set log Y mode: {log_mode}")
        except Exception as e:
            log.error(f"Failed to toggle log Y: {e}")

    def _auto_scale(self) -> None:
        """Auto-scale plot to fit data."""
        try:
            if self.plot_widget is not None:
                self.plot_widget.autoRange()
                log.debug("Auto-scaled spectrum plot")
        except Exception as e:
            log.error(f"Failed to auto-scale: {e}")

    def _export_csv(self) -> None:
        """Export spectrum data to CSV file."""
        try:
            if self.wavelengths is None or self.intensities is None:
                log.warning("No data to export")
                return

            import csv

            from PyQt6.QtWidgets import QFileDialog

            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Spectrum CSV",
                f"spectrum_{self.window_id}.csv",
                "CSV files (*.csv);;All files (*.*)"
            )

            if not file_path:
                return

            # Write CSV
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([self.xlabel.split('(')[0].strip(),
                               self.ylabel.split('(')[0].strip()])
                for x, y in zip(self.wavelengths, self.intensities):
                    writer.writerow([x, y])

            log.info(f"Exported spectrum to: {file_path}")

        except Exception as e:
            log.error(f"Failed to export CSV: {e}")

    def _update_from_event(self, event: Event) -> None:
        """Update plot from EventBus event (called in Qt thread).

        Args:
            event: Event containing spectrum data.
        """
        try:
            # Extract data from event
            data = self._parse_source_data(event, self.source)
            if data is None:
                return

            # Handle different data formats
            if isinstance(data, dict):
                # Data dict with wavelengths and intensities
                wavelengths = data.get('wavelengths')
                intensities = data.get('intensities') or data.get('spectrum')
            elif isinstance(data, np.ndarray):
                # Raw intensity array - generate wavelength axis
                intensities = data
                wavelengths = np.arange(len(data), dtype=float)
            else:
                log.warning(f"Unsupported data format: {type(data)}")
                return

            if wavelengths is None or intensities is None:
                return

            # Convert to numpy arrays
            wavelengths = np.asarray(wavelengths, dtype=float)
            intensities = np.asarray(intensities, dtype=float)

            if len(wavelengths) != len(intensities):
                log.warning(f"Wavelength/intensity size mismatch: {len(wavelengths)} vs {len(intensities)}")
                return

            # Store data
            self.wavelengths = wavelengths
            self.intensities = intensities

            # Update plot
            if self.plot_item is not None:
                self.plot_item.setData(wavelengths, intensities)

            # Update peak if enabled
            if self.show_peak and self.peak_line is not None:
                self._update_peak_position()

            log.debug(f"Updated spectrum plot: {len(wavelengths)} points")

        except Exception as e:
            log.error(f"Failed to update spectrum from event: {e}")

    def _update_peak_position(self) -> None:
        """Update peak line position based on current data."""
        try:
            if self.wavelengths is None or self.intensities is None:
                return

            # Find peak (simple max finding)
            peak_idx = np.argmax(self.intensities)
            peak_wavelength = self.wavelengths[peak_idx]
            peak_intensity = self.intensities[peak_idx]

            # Update peak line
            if self.peak_line is not None:
                self.peak_line.setPos(peak_wavelength)
                self.current_peak_pos = peak_wavelength

            log.debug(f"Peak at {peak_wavelength:.2f}: {peak_intensity:.0f}")

        except Exception as e:
            log.error(f"Failed to update peak position: {e}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        log.info(f"Closing spectrum window: {self.window_id}")

        # Call parent close handler
        LabPilotWindow.closeEvent(self, event)
