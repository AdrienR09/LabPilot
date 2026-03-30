"""
LabPilot Instrument Control Windows - Qudi Style Implementation
Professional scientific Qt interfaces following qudi-iqo-modules patterns
"""

import sys
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSpinBox, QDoubleSpinBox, QSlider, QComboBox, QGroupBox, QGridLayout,
    QSizePolicy, QToolBar, QMainWindow, QStatusBar, QCheckBox, QButtonGroup,
    QDockWidget, QSplitter, QTextEdit, QLineEdit, QProgressBar, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QFont, QAction, QIcon, QPalette, QColor
import pyqtgraph as pg
from main import DashboardInstrument

class QudiStyle:
    """Qudi-inspired color scheme and styling constants"""

    # Qudi dark theme colors
    BG_MAIN = "#2b2b2b"           # Main background
    BG_WIDGET = "#3c3c3c"         # Widget background
    BG_INPUT = "#404040"          # Input field background
    BG_TOOLBAR = "#363636"        # Toolbar background

    TEXT_PRIMARY = "#ffffff"      # Primary text
    TEXT_SECONDARY = "#b0b0b0"    # Secondary text
    TEXT_DISABLED = "#808080"     # Disabled text

    ACCENT_BLUE = "#1f77b4"       # Primary accent (qudi blue)
    ACCENT_ORANGE = "#ff7f0e"     # Secondary accent
    ACCENT_GREEN = "#2ca02c"      # Success/active
    ACCENT_RED = "#d62728"        # Error/warning

    BORDER_LIGHT = "#555555"      # Light borders
    BORDER_DARK = "#2a2a2a"       # Dark borders

    # Plot colors (qudi scientific palette)
    PLOT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

class QudiPlotWidget(pg.PlotWidget):
    """Qudi-style professional scientific plot widget"""

    def __init__(self, title="", xlabel="", ylabel="", parent=None):
        # Configure pyqtgraph for scientific use (qudi style)
        pg.setConfigOptions(
            antialias=True,
            useOpenGL=True,
            background=QudiStyle.BG_MAIN,
            foreground=QudiStyle.TEXT_PRIMARY
        )

        super().__init__(parent, background=QudiStyle.BG_MAIN)

        # Configure plot appearance (qudi professional style)
        self.setBackground(QudiStyle.BG_MAIN)
        self.showGrid(x=True, y=True, alpha=0.2)

        # Set qudi-style labels with proper typography
        label_style = {'color': QudiStyle.TEXT_PRIMARY, 'font-size': '10pt', 'font-family': 'Arial'}
        title_style = {'color': QudiStyle.TEXT_PRIMARY, 'font-size': '12pt', 'font-weight': 'bold'}

        if xlabel:
            self.setLabel('bottom', xlabel, **label_style)
        if ylabel:
            self.setLabel('left', ylabel, **label_style)
        if title:
            self.setTitle(title, **title_style)

        # Configure axes with qudi professional styling
        for axis in ['left', 'bottom', 'top', 'right']:
            ax = self.getAxis(axis)
            ax.setTextPen(QudiStyle.TEXT_PRIMARY)
            ax.setPen(QudiStyle.BORDER_LIGHT)
            ax.setStyle(tickFont=QFont('Arial', 9))

        # Hide right and top axes (qudi style - clean look)
        self.showAxis('right', False)
        self.showAxis('top', False)

        # Enable scientific navigation (qudi standard)
        self.setMouseEnabled(x=True, y=True)
        self.enableAutoRange()

        # Add qudi-style crosshair with improved styling
        crosshair_pen = pg.mkPen(
            color=QudiStyle.TEXT_SECONDARY,
            width=1,
            style=Qt.PenStyle.DashLine
        )
        self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
        self.crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
        self.addItem(self.crosshair_v, ignoreBounds=True)
        self.addItem(self.crosshair_h, ignoreBounds=True)

        # Position label for crosshair (qudi feature)
        self.cursor_label = pg.TextItem(
            text="",
            color=QudiStyle.TEXT_PRIMARY,
            border=QudiStyle.BORDER_LIGHT,
            fill=QudiStyle.BG_WIDGET
        )
        self.addItem(self.cursor_label, ignoreBounds=True)

        # Mouse tracking with position display
        self.scene().sigMouseMoved.connect(self._update_crosshair)

        # Professional context menu (qudi style)
        self.setMenuEnabled(True)

    def _update_crosshair(self, pos):
        """Update crosshair position with coordinate display (qudi style)"""
        if self.sceneBoundingRect().contains(pos):
            mouse_point = self.plotItem.vb.mapSceneToView(pos)
            x, y = mouse_point.x(), mouse_point.y()

            # Update crosshair lines
            self.crosshair_v.setPos(x)
            self.crosshair_h.setPos(y)

            # Update coordinate display (qudi feature)
            self.cursor_label.setText(f"({x:.3f}, {y:.3f})")
            self.cursor_label.setPos(x, y)

class QudiImageView(pg.ImageView):
    """Qudi-style 2D data visualization widget"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Configure qudi appearance
        self.setBackground(QudiStyle.BG_MAIN)

        # Set scientific colormap (qudi prefers viridis/plasma)
        self.ui.histogram.gradient.loadPreset('viridis')

        # Style histogram widget
        self.ui.histogram.setBackground(QudiStyle.BG_WIDGET)

class QudiControlFrame(QGroupBox):
    """Qudi-style control frame with professional styling"""

    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {QudiStyle.BORDER_LIGHT};
                border-radius: 4px;
                margin-top: 0.5em;
                padding: 8px;
                background-color: {QudiStyle.BG_WIDGET};
                color: {QudiStyle.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: {QudiStyle.ACCENT_BLUE};
            }}
        """)

class QudiButton(QPushButton):
    """Qudi-style professional button"""

    def __init__(self, text="", button_type="normal", parent=None):
        super().__init__(text, parent)

        if button_type == "start":
            bg_color = QudiStyle.ACCENT_GREEN
            hover_color = "#249624"
        elif button_type == "stop":
            bg_color = QudiStyle.ACCENT_RED
            hover_color = "#c21e1e"
        elif button_type == "primary":
            bg_color = QudiStyle.ACCENT_BLUE
            hover_color = "#1658a0"
        else:
            bg_color = QudiStyle.BG_INPUT
            hover_color = QudiStyle.BORDER_LIGHT

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                border: 1px solid {QudiStyle.BORDER_LIGHT};
                border-radius: 3px;
                padding: 6px 12px;
                color: {QudiStyle.TEXT_PRIMARY};
                font-weight: bold;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {QudiStyle.BORDER_DARK};
            }}
            QPushButton:disabled {{
                background-color: {QudiStyle.BORDER_DARK};
                color: {QudiStyle.TEXT_DISABLED};
            }}
        """)

class QudiSpinBox(QDoubleSpinBox):
    """Qudi-style scientific spinbox"""

    def __init__(self, minimum=-999999, maximum=999999, decimals=3, suffix="", parent=None):
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setDecimals(decimals)
        if suffix:
            self.setSuffix(f" {suffix}")

        self.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {QudiStyle.BG_INPUT};
                border: 1px solid {QudiStyle.BORDER_LIGHT};
                border-radius: 3px;
                padding: 4px 8px;
                color: {QudiStyle.TEXT_PRIMARY};
                font-family: 'Consolas', 'Monaco', monospace;
                font-weight: bold;
            }}
            QDoubleSpinBox:focus {{
                border-color: {QudiStyle.ACCENT_BLUE};
            }}
        """)

class QudiStatusBar(QStatusBar):
    """Qudi-style status bar"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QStatusBar {{
                background-color: {QudiStyle.BG_TOOLBAR};
                border-top: 1px solid {QudiStyle.BORDER_LIGHT};
                color: {QudiStyle.TEXT_SECONDARY};
                padding: 4px;
            }}
        """)

# ===== INDIVIDUAL INSTRUMENT UIs (QUDI STYLE) =====

class QudiDetector0DWindow(QMainWindow):
    """0D Detector - Professional Counter Interface (Qudi Style)"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.measurement_thread = None
        self.is_measuring = False

        # Data storage
        self.count_rate = 0.0
        self.time_trace = {'time': [], 'counts': []}
        self.total_counts = 0

        self.setup_ui()
        self.setup_simulation()
        self.apply_qudi_theme()

        self.setWindowTitle(f"{instrument.name} - 0D Detector")
        self.setMinimumSize(800, 600)

    def setup_ui(self):
        """Setup qudi-style UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout - qudi style splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        central_widget.setLayout(QVBoxLayout())
        central_widget.layout().addWidget(splitter)

        # Left control panel (qudi style)
        control_panel = self.create_control_panel()
        control_panel.setMaximumWidth(300)
        control_panel.setMinimumWidth(250)

        # Right plot area
        plot_area = self.create_plot_area()

        splitter.addWidget(control_panel)
        splitter.addWidget(plot_area)
        splitter.setSizes([250, 550])

        # Status bar
        self.status_bar = QudiStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def create_control_panel(self) -> QWidget:
        """Create qudi-style control panel"""
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {QudiStyle.BG_WIDGET};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ===== Counter Display =====
        counter_frame = QudiControlFrame("Live Counter")
        counter_layout = QVBoxLayout(counter_frame)

        # Large counter display (qudi style)
        self.counter_display = QLabel("0")
        self.counter_display.setFont(QFont("Consolas", 32, QFont.Weight.Bold))
        self.counter_display.setStyleSheet(f"""
            color: {QudiStyle.ACCENT_BLUE};
            background-color: {QudiStyle.BG_MAIN};
            border: 2px solid {QudiStyle.BORDER_LIGHT};
            padding: 12px;
            border-radius: 6px;
        """)
        self.counter_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Units label
        units_label = QLabel("counts/s")
        units_label.setStyleSheet(f"color: {QudiStyle.TEXT_SECONDARY}; font-size: 10pt;")
        units_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        counter_layout.addWidget(self.counter_display)
        counter_layout.addWidget(units_label)

        # ===== Measurement Controls =====
        measurement_frame = QudiControlFrame("Measurement Control")
        measurement_layout = QGridLayout(measurement_frame)

        # Integration time
        measurement_layout.addWidget(QLabel("Integration Time:"), 0, 0)
        self.integration_time_spin = QudiSpinBox(0.001, 10.0, 3, "s")
        self.integration_time_spin.setValue(0.1)
        measurement_layout.addWidget(self.integration_time_spin, 0, 1)

        # Start/Stop buttons (qudi style)
        self.start_btn = QudiButton("Start Measurement", "start")
        self.stop_btn = QudiButton("Stop Measurement", "stop")
        self.stop_btn.setEnabled(False)

        measurement_layout.addWidget(self.start_btn, 1, 0)
        measurement_layout.addWidget(self.stop_btn, 1, 1)

        # Connect signals
        self.start_btn.clicked.connect(self.start_measurement)
        self.stop_btn.clicked.connect(self.stop_measurement)

        # ===== Statistics =====
        stats_frame = QudiControlFrame("Statistics")
        stats_layout = QGridLayout(stats_frame)

        stats_layout.addWidget(QLabel("Total Counts:"), 0, 0)
        self.total_counts_label = QLabel("0")
        self.total_counts_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        stats_layout.addWidget(self.total_counts_label, 0, 1)

        stats_layout.addWidget(QLabel("Avg Rate:"), 1, 0)
        self.avg_rate_label = QLabel("0 Hz")
        self.avg_rate_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        stats_layout.addWidget(self.avg_rate_label, 1, 1)

        # Add all frames to panel
        layout.addWidget(counter_frame)
        layout.addWidget(measurement_frame)
        layout.addWidget(stats_frame)
        layout.addStretch()

        return panel

    def create_plot_area(self) -> QWidget:
        """Create qudi-style plot area"""
        plot_widget = QudiPlotWidget(
            title="Count Rate vs Time",
            xlabel="Time (s)",
            ylabel="Count Rate (counts/s)"
        )

        # Add plot curves
        self.count_curve = plot_widget.plot(
            pen=pg.mkPen(QudiStyle.ACCENT_BLUE, width=2),
            name="Count Rate"
        )

        # Store reference
        self.plot_widget = plot_widget
        return plot_widget

    def setup_simulation(self):
        """Setup measurement simulation"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_measurement)
        self.start_time = None

    def start_measurement(self):
        """Start measurement (qudi style)"""
        self.is_measuring = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Clear previous data
        self.time_trace = {'time': [], 'counts': []}
        self.total_counts = 0

        # Start simulation
        self.start_time = 0
        interval_ms = int(self.integration_time_spin.value() * 1000)
        self.timer.start(interval_ms)

        self.status_bar.showMessage("Measuring...")

    def stop_measurement(self):
        """Stop measurement"""
        self.is_measuring = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        self.timer.stop()
        self.status_bar.showMessage("Stopped")

    def update_measurement(self):
        """Update measurement data (simulated)"""
        if not self.is_measuring:
            return

        # Simulate realistic detector data
        base_rate = 10000  # Base count rate
        noise = np.random.poisson(base_rate * self.integration_time_spin.value())
        self.count_rate = noise / self.integration_time_spin.value()

        # Update display
        self.counter_display.setText(f"{self.count_rate:.0f}")

        # Update time trace
        current_time = len(self.time_trace['time']) * self.integration_time_spin.value()
        self.time_trace['time'].append(current_time)
        self.time_trace['counts'].append(self.count_rate)

        # Update statistics
        self.total_counts += noise
        self.total_counts_label.setText(f"{self.total_counts}")

        if len(self.time_trace['counts']) > 0:
            avg_rate = np.mean(self.time_trace['counts'])
            self.avg_rate_label.setText(f"{avg_rate:.1f} Hz")

        # Update plot (keep last 100 points for performance)
        if len(self.time_trace['time']) > 100:
            self.time_trace['time'] = self.time_trace['time'][-100:]
            self.time_trace['counts'] = self.time_trace['counts'][-100:]

        self.count_curve.setData(self.time_trace['time'], self.time_trace['counts'])

    def apply_qudi_theme(self):
        """Apply qudi dark theme"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {QudiStyle.BG_MAIN};
                color: {QudiStyle.TEXT_PRIMARY};
            }}
            QWidget {{
                background-color: {QudiStyle.BG_MAIN};
                color: {QudiStyle.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {QudiStyle.TEXT_PRIMARY};
            }}
        """)

class QudiDetector1DWindow(QMainWindow):
    """1D Detector - Spectrometer Interface (Qudi Style)"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.is_acquiring = False

        # Spectrometer data
        self.wavelengths = np.linspace(400, 800, 1024)  # nm
        self.spectrum = np.zeros_like(self.wavelengths)
        self.integration_time = 1.0  # seconds

        self.setup_ui()
        self.setup_simulation()
        self.apply_qudi_theme()

        self.setWindowTitle(f"{instrument.name} - 1D Spectrometer")
        self.setMinimumSize(1000, 700)

    def setup_ui(self):
        """Setup qudi-style spectrometer UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main splitter layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        central_widget.setLayout(QVBoxLayout())
        central_widget.layout().addWidget(splitter)

        # Control panel
        control_panel = self.create_spectrometer_controls()
        control_panel.setMaximumWidth(320)

        # Plot area
        plot_area = self.create_spectrum_plot()

        splitter.addWidget(control_panel)
        splitter.addWidget(plot_area)
        splitter.setSizes([320, 680])

        # Status bar
        self.status_bar = QudiStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Configure and start acquisition")

    def create_spectrometer_controls(self) -> QWidget:
        """Create spectrometer control panel"""
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {QudiStyle.BG_WIDGET};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ===== Acquisition Settings =====
        acq_frame = QudiControlFrame("Acquisition Settings")
        acq_layout = QGridLayout(acq_frame)

        # Integration time
        acq_layout.addWidget(QLabel("Integration Time:"), 0, 0)
        self.integration_spin = QudiSpinBox(0.001, 60.0, 3, "s")
        self.integration_spin.setValue(1.0)
        acq_layout.addWidget(self.integration_spin, 0, 1)

        # Number of averages
        acq_layout.addWidget(QLabel("Averages:"), 1, 0)
        self.averages_spin = QSpinBox()
        self.averages_spin.setRange(1, 1000)
        self.averages_spin.setValue(1)
        self.averages_spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {QudiStyle.BG_INPUT};
                border: 1px solid {QudiStyle.BORDER_LIGHT};
                border-radius: 3px;
                padding: 4px;
                color: {QudiStyle.TEXT_PRIMARY};
            }}
        """)
        acq_layout.addWidget(self.averages_spin, 1, 1)

        # ===== Acquisition Control =====
        control_frame = QudiControlFrame("Acquisition Control")
        control_layout = QVBoxLayout(control_frame)

        # Single acquisition
        self.single_btn = QudiButton("Single Acquisition", "primary")
        self.continuous_btn = QudiButton("Continuous", "start")
        self.stop_btn = QudiButton("Stop", "stop")
        self.stop_btn.setEnabled(False)

        control_layout.addWidget(self.single_btn)
        control_layout.addWidget(self.continuous_btn)
        control_layout.addWidget(self.stop_btn)

        # Connect signals
        self.single_btn.clicked.connect(self.single_acquisition)
        self.continuous_btn.clicked.connect(self.start_continuous)
        self.stop_btn.clicked.connect(self.stop_acquisition)

        # ===== Spectrum Analysis =====
        analysis_frame = QudiControlFrame("Spectrum Analysis")
        analysis_layout = QGridLayout(analysis_frame)

        analysis_layout.addWidget(QLabel("Peak Wavelength:"), 0, 0)
        self.peak_label = QLabel("-- nm")
        self.peak_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        analysis_layout.addWidget(self.peak_label, 0, 1)

        analysis_layout.addWidget(QLabel("Peak Intensity:"), 1, 0)
        self.intensity_label = QLabel("-- counts")
        self.intensity_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        analysis_layout.addWidget(self.intensity_label, 1, 1)

        analysis_layout.addWidget(QLabel("FWHM:"), 2, 0)
        self.fwhm_label = QLabel("-- nm")
        self.fwhm_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        analysis_layout.addWidget(self.fwhm_label, 2, 1)

        # Add frames to panel
        layout.addWidget(acq_frame)
        layout.addWidget(control_frame)
        layout.addWidget(analysis_frame)
        layout.addStretch()

        return panel

    def create_spectrum_plot(self) -> QWidget:
        """Create spectrum plot area"""
        plot_widget = QudiPlotWidget(
            title="Optical Spectrum",
            xlabel="Wavelength (nm)",
            ylabel="Intensity (counts)"
        )

        # Add spectrum curve
        self.spectrum_curve = plot_widget.plot(
            pen=pg.mkPen(QudiStyle.ACCENT_ORANGE, width=2),
            name="Spectrum"
        )

        # Set initial data
        self.spectrum_curve.setData(self.wavelengths, self.spectrum)

        self.plot_widget = plot_widget
        return plot_widget

    def setup_simulation(self):
        """Setup spectrometer simulation"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spectrum)

    def single_acquisition(self):
        """Perform single spectrum acquisition"""
        self.update_spectrum()
        self.status_bar.showMessage("Single acquisition completed")

    def start_continuous(self):
        """Start continuous acquisition"""
        self.is_acquiring = True
        self.single_btn.setEnabled(False)
        self.continuous_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        interval_ms = int(self.integration_spin.value() * 1000)
        self.timer.start(interval_ms)

        self.status_bar.showMessage("Continuous acquisition running...")

    def stop_acquisition(self):
        """Stop continuous acquisition"""
        self.is_acquiring = False
        self.single_btn.setEnabled(True)
        self.continuous_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        self.timer.stop()
        self.status_bar.showMessage("Acquisition stopped")

    def update_spectrum(self):
        """Update spectrum data (simulated)"""
        # Simulate realistic spectrum with multiple peaks
        self.spectrum = np.zeros_like(self.wavelengths)

        # Add several Gaussian peaks
        peaks = [(532, 1000, 5), (589, 600, 8), (656, 800, 6)]  # (wavelength, intensity, width)

        for wl, intensity, width in peaks:
            peak = intensity * np.exp(-0.5 * ((self.wavelengths - wl) / width) ** 2)
            self.spectrum += peak

        # Add noise
        noise_level = 50
        noise = np.random.normal(0, noise_level, len(self.spectrum))
        self.spectrum += noise
        self.spectrum = np.maximum(self.spectrum, 0)  # No negative values

        # Update plot
        self.spectrum_curve.setData(self.wavelengths, self.spectrum)

        # Analyze spectrum
        self.analyze_spectrum()

    def analyze_spectrum(self):
        """Analyze current spectrum"""
        if len(self.spectrum) == 0:
            return

        # Find peak
        peak_idx = np.argmax(self.spectrum)
        peak_wavelength = self.wavelengths[peak_idx]
        peak_intensity = self.spectrum[peak_idx]

        # Calculate FWHM (simplified)
        half_max = peak_intensity / 2
        indices = np.where(self.spectrum >= half_max)[0]
        if len(indices) > 1:
            fwhm = self.wavelengths[indices[-1]] - self.wavelengths[indices[0]]
        else:
            fwhm = 0

        # Update labels
        self.peak_label.setText(f"{peak_wavelength:.1f} nm")
        self.intensity_label.setText(f"{peak_intensity:.0f} counts")
        self.fwhm_label.setText(f"{fwhm:.1f} nm")

    def apply_qudi_theme(self):
        """Apply qudi theme"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {QudiStyle.BG_MAIN};
                color: {QudiStyle.TEXT_PRIMARY};
            }}
        """)

class QudiDetector2DWindow(QMainWindow):
    """2D Detector - Camera Interface (Qudi Style)"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.is_acquiring = False

        # Camera parameters
        self.image_data = np.zeros((512, 512))
        self.exposure_time = 0.1  # seconds

        self.setup_ui()
        self.setup_simulation()
        self.apply_qudi_theme()

        self.setWindowTitle(f"{instrument.name} - 2D Camera")
        self.setMinimumSize(1200, 800)

    def setup_ui(self):
        """Setup qudi-style camera UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        central_widget.setLayout(QVBoxLayout())
        central_widget.layout().addWidget(splitter)

        # Control panel
        control_panel = self.create_camera_controls()
        control_panel.setMaximumWidth(300)

        # Image display
        image_area = self.create_image_display()

        splitter.addWidget(control_panel)
        splitter.addWidget(image_area)
        splitter.setSizes([300, 900])

        # Status bar
        self.status_bar = QudiStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Camera ready")

    def create_camera_controls(self) -> QWidget:
        """Create camera control panel"""
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {QudiStyle.BG_WIDGET};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ===== Camera Settings =====
        camera_frame = QudiControlFrame("Camera Settings")
        camera_layout = QGridLayout(camera_frame)

        # Exposure time
        camera_layout.addWidget(QLabel("Exposure Time:"), 0, 0)
        self.exposure_spin = QudiSpinBox(0.001, 10.0, 3, "s")
        self.exposure_spin.setValue(0.1)
        camera_layout.addWidget(self.exposure_spin, 0, 1)

        # Gain
        camera_layout.addWidget(QLabel("Gain:"), 1, 0)
        self.gain_spin = QudiSpinBox(1.0, 10.0, 1, "x")
        self.gain_spin.setValue(1.0)
        camera_layout.addWidget(self.gain_spin, 1, 1)

        # ===== Acquisition Control =====
        acq_frame = QudiControlFrame("Acquisition")
        acq_layout = QVBoxLayout(acq_frame)

        self.snap_btn = QudiButton("Snap Image", "primary")
        self.live_btn = QudiButton("Live View", "start")
        self.stop_btn = QudiButton("Stop", "stop")
        self.stop_btn.setEnabled(False)

        acq_layout.addWidget(self.snap_btn)
        acq_layout.addWidget(self.live_btn)
        acq_layout.addWidget(self.stop_btn)

        # Connect signals
        self.snap_btn.clicked.connect(self.snap_image)
        self.live_btn.clicked.connect(self.start_live)
        self.stop_btn.clicked.connect(self.stop_acquisition)

        # ===== Image Analysis =====
        analysis_frame = QudiControlFrame("Image Statistics")
        analysis_layout = QGridLayout(analysis_frame)

        analysis_layout.addWidget(QLabel("Max Intensity:"), 0, 0)
        self.max_label = QLabel("0")
        analysis_layout.addWidget(self.max_label, 0, 1)

        analysis_layout.addWidget(QLabel("Mean:"), 1, 0)
        self.mean_label = QLabel("0")
        analysis_layout.addWidget(self.mean_label, 1, 1)

        analysis_layout.addWidget(QLabel("Std Dev:"), 2, 0)
        self.std_label = QLabel("0")
        analysis_layout.addWidget(self.std_label, 2, 1)

        # Add frames
        layout.addWidget(camera_frame)
        layout.addWidget(acq_frame)
        layout.addWidget(analysis_frame)
        layout.addStretch()

        return panel

    def create_image_display(self) -> QWidget:
        """Create image display area"""
        self.image_view = QudiImageView()

        # Set initial image
        self.image_view.setImage(self.image_data)

        return self.image_view

    def setup_simulation(self):
        """Setup camera simulation"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_image)

    def snap_image(self):
        """Take single image"""
        self.update_image()
        self.status_bar.showMessage("Image captured")

    def start_live(self):
        """Start live view"""
        self.is_acquiring = True
        self.snap_btn.setEnabled(False)
        self.live_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        interval_ms = max(50, int(self.exposure_spin.value() * 1000))
        self.timer.start(interval_ms)

        self.status_bar.showMessage("Live view active")

    def stop_acquisition(self):
        """Stop live view"""
        self.is_acquiring = False
        self.snap_btn.setEnabled(True)
        self.live_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        self.timer.stop()
        self.status_bar.showMessage("Live view stopped")

    def update_image(self):
        """Update image data (simulated)"""
        # Generate realistic camera image with features
        x, y = np.meshgrid(np.linspace(0, 512, 512), np.linspace(0, 512, 512))

        # Create some features (spots, gradients)
        image = np.zeros_like(x)

        # Add circular features
        centers = [(200, 200), (350, 300), (100, 400)]
        for cx, cy in centers:
            r = np.sqrt((x - cx)**2 + (y - cy)**2)
            spot = 1000 * np.exp(-r**2 / (30**2))
            image += spot

        # Add gradient background
        image += 100 + 0.2 * x + 0.1 * y

        # Add noise
        noise = np.random.poisson(image + 50) - 50
        image = np.maximum(image + noise, 0)

        # Apply exposure and gain
        image *= self.exposure_spin.value() * self.gain_spin.value()

        self.image_data = image.astype(np.uint16)

        # Update display
        self.image_view.setImage(self.image_data, autoRange=False, autoLevels=False)

        # Update statistics
        self.analyze_image()

    def analyze_image(self):
        """Analyze current image"""
        max_val = np.max(self.image_data)
        mean_val = np.mean(self.image_data)
        std_val = np.std(self.image_data)

        self.max_label.setText(f"{max_val:.0f}")
        self.mean_label.setText(f"{mean_val:.1f}")
        self.std_label.setText(f"{std_val:.1f}")

    def apply_qudi_theme(self):
        """Apply qudi theme"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {QudiStyle.BG_MAIN};
                color: {QudiStyle.TEXT_PRIMARY};
            }}
        """)

# ===== MOTOR/ACTUATOR UIs =====

class QudiMotor1DWindow(QMainWindow):
    """1D Motor - Single Axis Positioner (Qudi Style)"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.is_moving = False

        # Motor parameters
        self.current_position = 0.0
        self.target_position = 0.0
        self.velocity = 1.0  # mm/s

        self.setup_ui()
        self.setup_simulation()
        self.apply_qudi_theme()

        self.setWindowTitle(f"{instrument.name} - 1D Motor Control")
        self.setMinimumSize(800, 600)

    def setup_ui(self):
        """Setup qudi-style motor UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ===== Position Display =====
        position_frame = QudiControlFrame("Current Position")
        position_layout = QHBoxLayout(position_frame)

        self.position_display = QLabel("0.000")
        self.position_display.setFont(QFont("Consolas", 24, QFont.Weight.Bold))
        self.position_display.setStyleSheet(f"""
            color: {QudiStyle.ACCENT_BLUE};
            background-color: {QudiStyle.BG_MAIN};
            border: 2px solid {QudiStyle.BORDER_LIGHT};
            padding: 16px;
            border-radius: 6px;
        """)
        self.position_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        units_label = QLabel("mm")
        units_label.setFont(QFont("", 14))
        units_label.setStyleSheet(f"color: {QudiStyle.TEXT_SECONDARY};")

        position_layout.addWidget(self.position_display)
        position_layout.addWidget(units_label)

        # ===== Movement Controls =====
        control_frame = QudiControlFrame("Movement Control")
        control_layout = QGridLayout(control_frame)

        # Target position
        control_layout.addWidget(QLabel("Target Position:"), 0, 0)
        self.target_spin = QudiSpinBox(-100.0, 100.0, 3, "mm")
        self.target_spin.setValue(0.0)
        control_layout.addWidget(self.target_spin, 0, 1)

        # Velocity
        control_layout.addWidget(QLabel("Velocity:"), 1, 0)
        self.velocity_spin = QudiSpinBox(0.1, 10.0, 2, "mm/s")
        self.velocity_spin.setValue(1.0)
        control_layout.addWidget(self.velocity_spin, 1, 1)

        # Movement buttons
        self.move_abs_btn = QudiButton("Move Absolute", "primary")
        self.move_rel_btn = QudiButton("Move Relative", "normal")
        self.stop_btn = QudiButton("Emergency Stop", "stop")

        control_layout.addWidget(self.move_abs_btn, 2, 0)
        control_layout.addWidget(self.move_rel_btn, 2, 1)
        control_layout.addWidget(self.stop_btn, 3, 0, 1, 2)

        # Connect signals
        self.move_abs_btn.clicked.connect(self.move_absolute)
        self.move_rel_btn.clicked.connect(self.move_relative)
        self.stop_btn.clicked.connect(self.stop_movement)

        # ===== Jog Controls =====
        jog_frame = QudiControlFrame("Jog Control")
        jog_layout = QHBoxLayout(jog_frame)

        # Step size
        jog_layout.addWidget(QLabel("Step Size:"))
        self.step_spin = QudiSpinBox(0.001, 10.0, 3, "mm")
        self.step_spin.setValue(0.1)
        jog_layout.addWidget(self.step_spin)

        # Jog buttons
        self.jog_neg_btn = QudiButton("<<<", "normal")
        self.jog_pos_btn = QudiButton(">>>", "normal")

        self.jog_neg_btn.clicked.connect(lambda: self.jog_step(-1))
        self.jog_pos_btn.clicked.connect(lambda: self.jog_step(1))

        jog_layout.addWidget(self.jog_neg_btn)
        jog_layout.addWidget(self.jog_pos_btn)

        # Add all frames
        layout.addWidget(position_frame)
        layout.addWidget(control_frame)
        layout.addWidget(jog_frame)
        layout.addStretch()

        # Status bar
        self.status_bar = QudiStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Motor initialized")

    def setup_simulation(self):
        """Setup motor simulation"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_position)

    def move_absolute(self):
        """Move to absolute position"""
        self.target_position = self.target_spin.value()
        self.start_movement(f"Moving to {self.target_position} mm")

    def move_relative(self):
        """Move relative to current position"""
        self.target_position = self.current_position + self.target_spin.value()
        self.start_movement(f"Moving {self.target_spin.value()} mm relative")

    def jog_step(self, direction):
        """Jog motor by step size"""
        step = direction * self.step_spin.value()
        self.target_position = self.current_position + step
        self.start_movement(f"Jogging {step} mm")

    def start_movement(self, message):
        """Start motor movement"""
        self.is_moving = True
        self.move_abs_btn.setEnabled(False)
        self.move_rel_btn.setEnabled(False)

        # Start simulation timer
        self.timer.start(50)  # 50ms updates

        self.status_bar.showMessage(message)

    def stop_movement(self):
        """Emergency stop"""
        self.is_moving = False
        self.timer.stop()

        self.move_abs_btn.setEnabled(True)
        self.move_rel_btn.setEnabled(True)

        self.status_bar.showMessage("Movement stopped")

    def update_position(self):
        """Update motor position (simulated)"""
        if not self.is_moving:
            return

        # Calculate movement step
        dt = 0.05  # 50ms
        max_step = self.velocity_spin.value() * dt

        # Move towards target
        distance = self.target_position - self.current_position

        if abs(distance) < max_step:
            # Arrived at target
            self.current_position = self.target_position
            self.is_moving = False
            self.timer.stop()

            self.move_abs_btn.setEnabled(True)
            self.move_rel_btn.setEnabled(True)

            self.status_bar.showMessage("Movement completed")
        else:
            # Continue moving
            direction = np.sign(distance)
            self.current_position += direction * max_step

        # Update display
        self.position_display.setText(f"{self.current_position:.3f}")

    def apply_qudi_theme(self):
        """Apply qudi theme"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {QudiStyle.BG_MAIN};
                color: {QudiStyle.TEXT_PRIMARY};
            }}
        """)

# ===== FACTORY FUNCTION =====

def create_instrument_window(instrument: DashboardInstrument) -> QMainWindow:
    """Factory function to create appropriate qudi-style instrument window"""

    window_map = {
        ('detector', '0D'): QudiDetector0DWindow,
        ('detector', '1D'): QudiDetector1DWindow,
        ('detector', '2D'): QudiDetector2DWindow,
        ('motor', '1D'): QudiMotor1DWindow,
    }

    # Get window class
    window_class = window_map.get((instrument.kind, instrument.dimensionality))

    if window_class is None:
        # Fallback to 1D detector for unknown types
        window_class = QudiDetector1DWindow

    return window_class(instrument)