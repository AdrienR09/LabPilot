"""
Instrument Control Windows - Professional Qt/PyQtGraph Implementation
Contains all instrument-specific control interfaces with advanced plotting
"""

import sys
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSpinBox, QDoubleSpinBox, QSlider, QComboBox, QGroupBox, QGridLayout,
    QSizePolicy, QToolBar, QMainWindow, QStatusBar, QCheckBox, QButtonGroup
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QFont, QAction, QIcon
import pyqtgraph as pg
from main import DashboardInstrument, LabPilotStyle

class PyQtGraphWidget(pg.PlotWidget):
    """Enhanced PyQtGraph widget with professional scientific features"""

    def __init__(self, title: str = "", x_label: str = "X", y_label: str = "Y",
                 x_unit: str = "", y_unit: str = "", parent=None):
        super().__init__(parent)

        # Configure plot appearance
        self.setBackground(LabPilotStyle.BG_PRIMARY)
        self.showGrid(x=True, y=True, alpha=0.3)

        # Set labels
        xlabel = f"{x_label}"
        if x_unit:
            xlabel += f" ({x_unit})"

        ylabel = f"{y_label}"
        if y_unit:
            ylabel += f" ({y_unit})"

        self.setLabel('left', ylabel, color=LabPilotStyle.TEXT_PRIMARY)
        self.setLabel('bottom', xlabel, color=LabPilotStyle.TEXT_PRIMARY)

        if title:
            self.setTitle(title, color=LabPilotStyle.TEXT_PRIMARY, size='14pt')

        # Configure axes
        self.getAxis('left').setTextPen(LabPilotStyle.TEXT_PRIMARY)
        self.getAxis('bottom').setTextPen(LabPilotStyle.TEXT_PRIMARY)
        self.getAxis('left').setPen(LabPilotStyle.TEXT_SECONDARY)
        self.getAxis('bottom').setPen(LabPilotStyle.TEXT_SECONDARY)

        # Enable professional features
        self.setMenuEnabled(True)  # Right-click context menu
        self.enableAutoRange()
        self.setMouseEnabled(x=True, y=True)  # Pan and zoom

        # Add crosshair
        self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(LabPilotStyle.TEXT_MUTED, width=1))
        self.crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(LabPilotStyle.TEXT_MUTED, width=1))
        self.addItem(self.crosshair_v, ignoreBounds=True)
        self.addItem(self.crosshair_h, ignoreBounds=True)

        # Mouse tracking for crosshair
        self.scene().sigMouseMoved.connect(self.mouse_moved)

    def mouse_moved(self, pos):
        """Update crosshair position"""
        if self.sceneBoundingRect().contains(pos):
            mouse_point = self.plotItem.vb.mapSceneToView(pos)
            self.crosshair_v.setPos(mouse_point.x())
            self.crosshair_h.setPos(mouse_point.y())

class ImageViewWidget(pg.ImageView):
    """Enhanced ImageView for 2D detector data"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Configure appearance
        self.ui.histogram.gradient.loadPreset('viridis')
        self.ui.roiBtn.hide()  # Hide ROI button initially
        self.ui.normBtn.hide()  # Hide normalize button

        # Set background
        self.setBackground(LabPilotStyle.BG_PRIMARY)

class ProfessionalSpinBox(QDoubleSpinBox):
    """Professional spinbox with scientific notation support"""

    def __init__(self, minimum=0, maximum=9999, decimals=3, suffix="", parent=None):
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setDecimals(decimals)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setStyleSheet(f"""
            QDoubleSpinBox {{
                font-family: 'Consolas', 'Monaco', monospace;
                font-weight: bold;
                padding: 4px 8px;
            }}
        """)

class IconButton(QPushButton):
    """Professional icon button with consistent styling"""

    def __init__(self, text: str, icon_text: str = "", button_class: str = "primary", parent=None):
        super().__init__(f"{icon_text} {text}" if icon_text else text, parent)
        self.setProperty("class", button_class)
        self.setMinimumHeight(36)
        self.setFont(QFont("", 10, QFont.Weight.Bold))

# ===== 0D DETECTOR WINDOW =====
class Detector0DWindow(QMainWindow):
    """0D Detector - Counter with time trace (Qudi style)"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.current_value = 0.0
        self.time_trace_data = {'x': [], 'y': []}
        self.is_live = False
        self.is_recording = False
        self.integration_time = 100  # ms

        self.setup_ui()
        self.setup_simulation()
        self.setWindowTitle(f"{instrument.name} - 0D Detector Control")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top toolbar with counter and controls
        toolbar_widget = QFrame()
        toolbar_widget.setFixedHeight(100)
        toolbar_widget.setStyleSheet(f"background-color: {LabPilotStyle.BG_SECONDARY};")
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)

        # Large counter display
        counter_layout = QVBoxLayout()

        self.counter_label = QLabel("0")
        self.counter_label.setFont(QFont("", 28, QFont.Weight.Bold))
        self.counter_label.setStyleSheet(f"color: {LabPilotStyle.PRIMARY}; font-family: 'Consolas', monospace;")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        units_label = QLabel("counts/s")
        units_label.setProperty("class", "muted")
        units_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        counter_layout.addWidget(self.counter_label)
        counter_layout.addWidget(units_label)
        toolbar_layout.addLayout(counter_layout)

        toolbar_layout.addStretch()

        # Control buttons
        controls_layout = QHBoxLayout()

        self.snapshot_btn = IconButton("Snapshot", "▶", "primary")
        self.snapshot_btn.clicked.connect(self.take_snapshot)

        self.live_btn = IconButton("Start Live", "▶", "success")
        self.live_btn.clicked.connect(self.toggle_live)

        self.record_btn = IconButton("Record", "●", "warning")
        self.record_btn.clicked.connect(self.toggle_recording)

        controls_layout.addWidget(self.snapshot_btn)
        controls_layout.addWidget(self.live_btn)
        controls_layout.addWidget(self.record_btn)

        toolbar_layout.addLayout(controls_layout)

        toolbar_layout.addStretch()

        # Settings
        settings_layout = QHBoxLayout()

        settings_layout.addWidget(QLabel("Integration:"))
        self.integration_spinbox = ProfessionalSpinBox(10, 5000, 0, "ms")
        self.integration_spinbox.setValue(self.integration_time)
        self.integration_spinbox.valueChanged.connect(self.update_integration_time)
        settings_layout.addWidget(self.integration_spinbox)

        toolbar_layout.addLayout(settings_layout)

        layout.addWidget(toolbar_widget)

        # Full-window time trace graph
        self.plot_widget = PyQtGraphWidget(
            title="Time Trace",
            x_label="Time",
            y_label="Intensity",
            x_unit="s",
            y_unit="counts/s"
        )

        # Configure plot for time series
        self.plot_curve = self.plot_widget.plot(
            [], [],
            pen=pg.mkPen(LabPilotStyle.PRIMARY, width=2),
            symbol='o',
            symbolSize=4,
            symbolBrush=LabPilotStyle.PRIMARY
        )

        # Fill under curve
        self.plot_fill = pg.FillBetweenItem(
            self.plot_curve,
            pg.PlotCurveItem([]),
            brush=pg.mkBrush(*pg.colorTuple(pg.mkColor(LabPilotStyle.PRIMARY))[:3] + (50,))
        )
        self.plot_widget.addItem(self.plot_fill)

        layout.addWidget(self.plot_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

        # Set window properties
        self.resize(1200, 800)

    def setup_simulation(self):
        """Setup data simulation timer"""
        self.simulation_timer = QTimer()
        self.simulation_timer.timeout.connect(self.update_simulation)

    def take_snapshot(self):
        """Take single measurement"""
        value = np.random.normal(1000, 100) + np.random.exponential(200)
        self.current_value = max(0, value)
        self.counter_label.setText(f"{self.current_value:.0f}")

        if self.is_recording:
            current_time = len(self.time_trace_data['x']) * 0.1  # Simple time progression
            self.time_trace_data['x'].append(current_time)
            self.time_trace_data['y'].append(self.current_value)
            self.update_plot()

        self.status_bar.showMessage(f"Snapshot: {self.current_value:.0f} counts/s")

    def toggle_live(self):
        """Toggle live acquisition"""
        if not self.is_live:
            self.is_live = True
            self.live_btn.setText("■ Stop Live")
            self.live_btn.setProperty("class", "danger")
            self.live_btn.setStyleSheet("")  # Reset style to apply new class
            self.simulation_timer.start(self.integration_time)
            self.status_bar.showMessage("Live acquisition started")
        else:
            self.is_live = False
            self.live_btn.setText("▶ Start Live")
            self.live_btn.setProperty("class", "success")
            self.live_btn.setStyleSheet("")  # Reset style
            self.simulation_timer.stop()
            self.status_bar.showMessage("Live acquisition stopped")

    def toggle_recording(self):
        """Toggle trace recording"""
        if not self.is_recording:
            self.is_recording = True
            self.record_btn.setText("■ Stop Record")
            self.record_btn.setProperty("class", "danger")
            self.record_btn.setStyleSheet("")
            # Clear existing data
            self.time_trace_data = {'x': [], 'y': []}
            self.status_bar.showMessage("Recording started")
        else:
            self.is_recording = False
            self.record_btn.setText("● Record")
            self.record_btn.setProperty("class", "warning")
            self.record_btn.setStyleSheet("")
            self.status_bar.showMessage(f"Recording stopped. {len(self.time_trace_data['x'])} points captured")

    def update_integration_time(self, value):
        """Update integration time"""
        self.integration_time = int(value)
        if self.is_live:
            self.simulation_timer.setInterval(self.integration_time)

    def update_simulation(self):
        """Update live data"""
        self.take_snapshot()

    def update_plot(self):
        """Update the time trace plot"""
        if len(self.time_trace_data['x']) > 1:
            self.plot_curve.setData(self.time_trace_data['x'], self.time_trace_data['y'])

            # Keep only last 500 points for performance
            if len(self.time_trace_data['x']) > 500:
                self.time_trace_data['x'] = self.time_trace_data['x'][-500:]
                self.time_trace_data['y'] = self.time_trace_data['y'][-500:]

# ===== 1D DETECTOR WINDOW =====
class Detector1DWindow(QMainWindow):
    """1D Detector - Spectrometer (PyMoDAQ style)"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.spectrum_data = {'x': [], 'y': []}
        self.is_live = False
        self.integration_time = 100
        self.pixels = 1024

        self.setup_ui()
        self.setup_simulation()
        self.generate_spectrum()  # Initial spectrum
        self.setWindowTitle(f"{instrument.name} - Spectrometer Control")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(80)
        toolbar.setStyleSheet(f"background-color: {LabPilotStyle.BG_SECONDARY};")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)

        # Acquisition controls
        controls_layout = QHBoxLayout()

        self.snapshot_btn = IconButton("Snapshot", "▶", "primary")
        self.snapshot_btn.clicked.connect(self.take_snapshot)

        self.live_btn = IconButton("Start Live", "▶", "success")
        self.live_btn.clicked.connect(self.toggle_live)

        controls_layout.addWidget(self.snapshot_btn)
        controls_layout.addWidget(self.live_btn)
        toolbar_layout.addLayout(controls_layout)

        toolbar_layout.addStretch()

        # Integration time
        integration_layout = QHBoxLayout()
        integration_layout.addWidget(QLabel("Integration:"))

        self.integration_spinbox = ProfessionalSpinBox(1, 10000, 0, "ms")
        self.integration_spinbox.setValue(self.integration_time)
        integration_layout.addWidget(self.integration_spinbox)

        toolbar_layout.addLayout(integration_layout)

        toolbar_layout.addStretch()

        # Settings button
        self.settings_btn = IconButton("Settings", "⚙", "")
        self.settings_btn.setCheckable(True)
        self.settings_btn.toggled.connect(self.toggle_settings)
        toolbar_layout.addWidget(self.settings_btn)

        # Max intensity display
        self.max_label = QLabel("Max: 0")
        self.max_label.setProperty("class", "muted")
        toolbar_layout.addWidget(self.max_label)

        layout.addWidget(toolbar)

        # Settings panel (hidden by default)
        self.settings_panel = QFrame()
        self.settings_panel.setMaximumHeight(60)
        self.settings_panel.hide()
        settings_layout = QHBoxLayout(self.settings_panel)

        settings_layout.addWidget(QLabel("Pixels:"))
        self.pixels_combo = QComboBox()
        self.pixels_combo.addItems(["256", "512", "1024", "2048"])
        self.pixels_combo.setCurrentText(str(self.pixels))
        self.pixels_combo.currentTextChanged.connect(self.update_pixels)
        settings_layout.addWidget(self.pixels_combo)

        settings_layout.addStretch()
        layout.addWidget(self.settings_panel)

        # Full-screen spectrum plot
        self.plot_widget = PyQtGraphWidget(
            title="Live Spectrum",
            x_label="Wavelength",
            y_label="Intensity",
            x_unit="nm",
            y_unit="counts"
        )

        self.spectrum_curve = self.plot_widget.plot(
            [], [],
            pen=pg.mkPen(LabPilotStyle.PRIMARY, width=1.5)
        )

        # Fill under spectrum
        self.spectrum_fill = pg.FillBetweenItem(
            self.spectrum_curve,
            pg.PlotCurveItem([]),
            brush=pg.mkBrush(*pg.colorTuple(pg.mkColor(LabPilotStyle.PRIMARY))[:3] + (30,))
        )
        self.plot_widget.addItem(self.spectrum_fill)

        layout.addWidget(self.plot_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

        self.resize(1400, 900)

    def setup_simulation(self):
        self.simulation_timer = QTimer()
        self.simulation_timer.timeout.connect(self.generate_spectrum)

    def generate_spectrum(self):
        """Generate realistic spectrum data"""
        wavelengths = np.linspace(400, 800, self.pixels)

        # Base noise
        spectrum = np.random.normal(50, 10, self.pixels)

        # Add realistic peaks
        peak1 = 500 * np.exp(-0.5 * ((wavelengths - 500) / 30) ** 2)
        peak2 = 300 * np.exp(-0.5 * ((wavelengths - 600) / 50) ** 2)
        peak3 = 200 * np.exp(-0.5 * ((wavelengths - 700) / 20) ** 2)

        # Background slope
        background = (wavelengths - 400) * 0.1

        spectrum = np.maximum(0, spectrum + peak1 + peak2 + peak3 + background)

        self.spectrum_data = {'x': wavelengths, 'y': spectrum}
        self.update_spectrum_plot()

        # Update max display
        max_intensity = np.max(spectrum)
        self.max_label.setText(f"Max: {max_intensity:.0f}")

    def take_snapshot(self):
        self.generate_spectrum()
        self.status_bar.showMessage("Spectrum captured")

    def toggle_live(self):
        if not self.is_live:
            self.is_live = True
            self.live_btn.setText("■ Stop Live")
            self.live_btn.setProperty("class", "danger")
            self.live_btn.setStyleSheet("")
            self.simulation_timer.start(self.integration_time)
            self.status_bar.showMessage("Live acquisition started")
        else:
            self.is_live = False
            self.live_btn.setText("▶ Start Live")
            self.live_btn.setProperty("class", "success")
            self.live_btn.setStyleSheet("")
            self.simulation_timer.stop()
            self.status_bar.showMessage("Live acquisition stopped")

    def toggle_settings(self, checked):
        if checked:
            self.settings_panel.show()
        else:
            self.settings_panel.hide()

    def update_pixels(self, text):
        self.pixels = int(text)
        if not self.is_live:  # Only regenerate if not in live mode
            self.generate_spectrum()

    def update_spectrum_plot(self):
        if len(self.spectrum_data['x']) > 0:
            self.spectrum_curve.setData(self.spectrum_data['x'], self.spectrum_data['y'])

# ===== 2D DETECTOR WINDOW =====
class Detector2DWindow(QMainWindow):
    """2D Detector - Camera with full window image"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.image_data = None
        self.is_live = False
        self.exposure_time = 100
        self.resolution = (256, 256)

        self.setup_ui()
        self.setup_simulation()
        self.generate_image()
        self.setWindowTitle(f"{instrument.name} - Camera Control")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(80)
        toolbar.setStyleSheet(f"background-color: {LabPilotStyle.BG_SECONDARY};")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)

        # Acquisition controls
        controls_layout = QHBoxLayout()

        self.snapshot_btn = IconButton("Capture", "▶", "primary")
        self.snapshot_btn.clicked.connect(self.capture_image)

        self.live_btn = IconButton("Start Live", "▶", "success")
        self.live_btn.clicked.connect(self.toggle_live)

        controls_layout.addWidget(self.snapshot_btn)
        controls_layout.addWidget(self.live_btn)
        toolbar_layout.addLayout(controls_layout)

        toolbar_layout.addStretch()

        # Exposure time
        exposure_layout = QHBoxLayout()
        exposure_layout.addWidget(QLabel("Exposure:"))

        self.exposure_spinbox = ProfessionalSpinBox(1, 10000, 0, "ms")
        self.exposure_spinbox.setValue(self.exposure_time)
        exposure_layout.addWidget(self.exposure_spinbox)

        toolbar_layout.addLayout(exposure_layout)

        toolbar_layout.addStretch()

        # Settings
        self.settings_btn = IconButton("Settings", "⚙", "")
        self.settings_btn.setCheckable(True)
        self.settings_btn.toggled.connect(self.toggle_settings)
        toolbar_layout.addWidget(self.settings_btn)

        # Image info
        self.info_label = QLabel("256×256")
        self.info_label.setProperty("class", "muted")
        toolbar_layout.addWidget(self.info_label)

        layout.addWidget(toolbar)

        # Settings panel
        self.settings_panel = QFrame()
        self.settings_panel.setMaximumHeight(60)
        self.settings_panel.hide()
        settings_layout = QHBoxLayout(self.settings_panel)

        settings_layout.addWidget(QLabel("Resolution:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["128×128", "256×256", "512×512", "1024×1024"])
        self.resolution_combo.setCurrentText("256×256")
        self.resolution_combo.currentTextChanged.connect(self.update_resolution)
        settings_layout.addWidget(self.resolution_combo)

        settings_layout.addStretch()
        layout.addWidget(self.settings_panel)

        # Full-screen image display
        self.image_view = ImageViewWidget()
        layout.addWidget(self.image_view)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

        self.resize(1200, 1000)

    def setup_simulation(self):
        self.simulation_timer = QTimer()
        self.simulation_timer.timeout.connect(self.generate_image)

    def generate_image(self):
        """Generate realistic 2D image"""
        width, height = self.resolution
        y_coords, x_coords = np.ogrid[:height, :width]

        center_x, center_y = width // 2, height // 2

        # Base noise
        image = np.random.normal(100, 25, (height, width))

        # Central gaussian feature
        distance = np.sqrt((x_coords - center_x)**2 + (y_coords - center_y)**2)
        central_feature = 500 * np.exp(-distance / 40)

        # Interference pattern
        interference = 100 * np.sin(x_coords / 15) * np.sin(y_coords / 15)

        # Secondary spot
        spot_x, spot_y = int(0.7 * width), int(0.3 * height)
        spot_distance = np.sqrt((x_coords - spot_x)**2 + (y_coords - spot_y)**2)
        secondary_spot = 200 * np.exp(-spot_distance / 20)

        self.image_data = np.maximum(0, image + central_feature + interference + secondary_spot)

        self.update_image_display()

        max_val = np.max(self.image_data)
        self.info_label.setText(f"{width}×{height} • Max: {max_val:.0f}")

    def capture_image(self):
        self.generate_image()
        self.status_bar.showMessage("Image captured")

    def toggle_live(self):
        if not self.is_live:
            self.is_live = True
            self.live_btn.setText("■ Stop Live")
            self.live_btn.setProperty("class", "danger")
            self.live_btn.setStyleSheet("")
            self.simulation_timer.start(self.exposure_time)
            self.status_bar.showMessage("Live preview started")
        else:
            self.is_live = False
            self.live_btn.setText("▶ Start Live")
            self.live_btn.setProperty("class", "success")
            self.live_btn.setStyleSheet("")
            self.simulation_timer.stop()
            self.status_bar.showMessage("Live preview stopped")

    def toggle_settings(self, checked):
        if checked:
            self.settings_panel.show()
        else:
            self.settings_panel.hide()

    def update_resolution(self, text):
        width, height = map(int, text.split('×'))
        self.resolution = (width, height)
        if not self.is_live:
            self.generate_image()

    def update_image_display(self):
        if self.image_data is not None:
            self.image_view.setImage(
                self.image_data.T,  # Transpose for correct orientation
                autoRange=True,
                autoLevels=True,
                autoHistogramRange=True
            )

# ===== 0D MOTOR WINDOW =====
class Motor0DWindow(QMainWindow):
    """0D Motor - State switches and buttons"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.current_state = "OFF"
        self.available_states = ["OFF", "ON", "STANDBY", "LOCKED"]

        self.setup_ui()
        self.setWindowTitle(f"{instrument.name} - Motor Control")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Center the content
        layout = QVBoxLayout(central_widget)
        layout.addStretch()

        # Main control frame
        control_frame = QFrame()
        control_frame.setMaximumSize(400, 500)
        control_frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        frame_layout = QVBoxLayout(control_frame)
        frame_layout.setContentsMargins(32, 32, 32, 32)
        frame_layout.setSpacing(24)

        # Title
        title = QLabel(self.instrument.name)
        title.setFont(QFont("", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(title)

        # Current state display
        state_layout = QVBoxLayout()

        state_label = QLabel("Current State")
        state_label.setProperty("class", "subtitle")
        state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.state_display = QLabel(self.current_state)
        self.state_display.setFont(QFont("", 20, QFont.Weight.Bold))
        self.state_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_state_color()

        state_layout.addWidget(state_label)
        state_layout.addWidget(self.state_display)
        frame_layout.addLayout(state_layout)

        # State buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(12)

        self.state_buttons = []
        for state in self.available_states:
            btn = QPushButton(state)
            btn.setMinimumHeight(50)
            btn.setFont(QFont("", 12, QFont.Weight.Bold))
            btn.clicked.connect(lambda checked, s=state: self.set_state(s))
            self.state_buttons.append(btn)
            buttons_layout.addWidget(btn)

        frame_layout.addLayout(buttons_layout)

        # Center the frame
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(control_frame)
        h_layout.addStretch()

        layout.addLayout(h_layout)
        layout.addStretch()

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage(f"Current state: {self.current_state}")
        self.setStatusBar(self.status_bar)

        self.resize(600, 700)
        self.update_button_states()

    def set_state(self, state: str):
        """Set motor state"""
        self.current_state = state
        self.state_display.setText(state)
        self.update_state_color()
        self.update_button_states()
        self.status_bar.showMessage(f"State changed to: {state}")

    def update_state_color(self):
        """Update state display color"""
        if self.current_state == "ON":
            color = LabPilotStyle.SUCCESS
        elif self.current_state == "STANDBY":
            color = LabPilotStyle.WARNING
        elif self.current_state == "LOCKED":
            color = LabPilotStyle.DANGER
        else:
            color = LabPilotStyle.TEXT_MUTED

        self.state_display.setStyleSheet(f"color: {color};")

    def update_button_states(self):
        """Update button appearance based on current state"""
        for i, state in enumerate(self.available_states):
            if state == self.current_state:
                self.state_buttons[i].setProperty("class", "primary")
            else:
                self.state_buttons[i].setProperty("class", "")
            self.state_buttons[i].setStyleSheet("")  # Reset style to apply class

# ===== 1D MOTOR WINDOW =====
class Motor1DWindow(QMainWindow):
    """1D Motor - Position control with real-time slider"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        self.current_position = 50.0
        self.target_position = 50.0
        self.is_moving = False
        self.is_homing = False
        self.realtime_slider = True

        self.setup_ui()
        self.setWindowTitle(f"{instrument.name} - 1D Motor Control")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Current position display (top)
        position_frame = QFrame()
        position_layout = QVBoxLayout(position_frame)
        position_layout.setContentsMargins(16, 16, 16, 16)

        pos_label = QLabel("Current Position")
        pos_label.setProperty("class", "subtitle")
        pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        position_layout_h = QHBoxLayout()
        position_layout_h.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.position_display = QLabel("50.000")
        self.position_display.setFont(QFont("", 48, QFont.Weight.Bold))
        self.position_display.setStyleSheet(f"color: {LabPilotStyle.PRIMARY}; font-family: 'Consolas', monospace;")

        unit_label = QLabel("mm")
        unit_label.setFont(QFont("", 16))
        unit_label.setProperty("class", "muted")

        position_layout_h.addWidget(self.position_display)
        position_layout_h.addWidget(unit_label)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("", 14))
        self.update_status_display()

        position_layout.addWidget(pos_label)
        position_layout.addLayout(position_layout_h)
        position_layout.addWidget(self.status_label)

        layout.addWidget(position_frame)

        # Control section
        control_frame = QFrame()
        control_layout = QVBoxLayout(control_frame)
        control_layout.setContentsMargins(16, 16, 16, 16)
        control_layout.setSpacing(16)

        # Target position input
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target Position:"))

        self.target_spinbox = ProfessionalSpinBox(0, 100, 3, "mm")
        self.target_spinbox.setValue(self.target_position)
        self.target_spinbox.valueChanged.connect(self.update_target_position)
        target_layout.addWidget(self.target_spinbox)

        control_layout.addLayout(target_layout)

        # Control buttons
        buttons_layout = QHBoxLayout()

        self.home_btn = IconButton("Home", "🏠", "warning")
        self.home_btn.clicked.connect(self.home_motor)

        self.move_btn = IconButton("Move", "→", "primary")
        self.move_btn.clicked.connect(self.move_to_position)

        self.stop_btn = IconButton("Stop", "■", "danger")
        self.stop_btn.clicked.connect(self.stop_motion)
        self.stop_btn.setEnabled(False)

        self.settings_btn = IconButton("Settings", "⚙", "")
        self.settings_btn.setCheckable(True)
        self.settings_btn.toggled.connect(self.toggle_settings)

        buttons_layout.addWidget(self.home_btn)
        buttons_layout.addWidget(self.move_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.settings_btn)

        control_layout.addLayout(buttons_layout)

        # Position slider
        slider_layout = QVBoxLayout()

        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("0 mm"))
        range_layout.addStretch()
        range_layout.addWidget(QLabel("100 mm"))
        slider_layout.addLayout(range_layout)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)  # 0.1 mm resolution
        self.position_slider.setValue(int(self.target_position * 10))
        self.position_slider.valueChanged.connect(self.slider_changed)
        slider_layout.addWidget(self.position_slider)

        self.realtime_label = QLabel("Real-time slider: ON")
        self.realtime_label.setProperty("class", "muted")
        self.realtime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider_layout.addWidget(self.realtime_label)

        control_layout.addLayout(slider_layout)

        # Settings panel
        self.settings_panel = QFrame()
        self.settings_panel.hide()
        settings_layout = QHBoxLayout(self.settings_panel)

        settings_layout.addWidget(QLabel("Real-time Slider Movement:"))
        self.realtime_checkbox = QCheckBox()
        self.realtime_checkbox.setChecked(self.realtime_slider)
        self.realtime_checkbox.toggled.connect(self.toggle_realtime_slider)
        settings_layout.addWidget(self.realtime_checkbox)
        settings_layout.addStretch()

        control_layout.addWidget(self.settings_panel)

        layout.addWidget(control_frame)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        self.setStatusBar(self.status_bar)

        self.resize(800, 600)

        # Motion simulation timer
        self.motion_timer = QTimer()
        self.motion_timer.timeout.connect(self.update_motion)

    def update_target_position(self, value):
        """Update target position from spinbox"""
        self.target_position = value
        self.position_slider.setValue(int(value * 10))

        # Real-time movement
        if self.realtime_slider and not self.is_moving:
            self.current_position = value
            self.position_display.setText(f"{self.current_position:.3f}")

    def slider_changed(self, value):
        """Update target from slider"""
        self.target_position = value / 10.0
        self.target_spinbox.setValue(self.target_position)

    def move_to_position(self):
        """Start motor movement"""
        if self.is_moving:
            return

        self.is_moving = True
        self.start_position = self.current_position
        self.motion_start_time = 0
        self.motion_duration = abs(self.target_position - self.current_position) * 100  # 100ms per mm

        self.move_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.home_btn.setEnabled(False)

        self.motion_timer.start(50)  # 20Hz update
        self.status_bar.showMessage(f"Moving to {self.target_position:.3f} mm")

    def home_motor(self):
        """Home the motor"""
        self.target_position = 0.0
        self.target_spinbox.setValue(0.0)
        self.is_homing = True
        self.move_to_position()

    def stop_motion(self):
        """Stop motor motion"""
        self.motion_timer.stop()
        self.is_moving = False
        self.is_homing = False

        self.move_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.home_btn.setEnabled(True)

        self.update_status_display()
        self.status_bar.showMessage(f"Stopped at {self.current_position:.3f} mm")

    def update_motion(self):
        """Update motion simulation"""
        self.motion_start_time += 50

        progress = min(self.motion_start_time / self.motion_duration, 1.0)
        self.current_position = self.start_position + (self.target_position - self.start_position) * progress

        self.position_display.setText(f"{self.current_position:.3f}")

        if progress >= 1.0:
            self.motion_timer.stop()
            self.is_moving = False
            homing = self.is_homing
            self.is_homing = False

            self.move_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.home_btn.setEnabled(True)

            if homing:
                self.status_bar.showMessage("Homing completed")
            else:
                self.status_bar.showMessage(f"Move completed at {self.current_position:.3f} mm")

        self.update_status_display()

    def toggle_settings(self, checked):
        """Toggle settings panel"""
        if checked:
            self.settings_panel.show()
        else:
            self.settings_panel.hide()

    def toggle_realtime_slider(self, checked):
        """Toggle real-time slider movement"""
        self.realtime_slider = checked
        self.realtime_label.setText(f"Real-time slider: {'ON' if checked else 'OFF'}")

    def update_status_display(self):
        """Update status display color and text"""
        if self.is_moving:
            self.status_label.setText("⚡ Moving...")
            self.status_label.setStyleSheet(f"color: {LabPilotStyle.PRIMARY};")
        elif self.is_homing:
            self.status_label.setText("🏠 Homing...")
            self.status_label.setStyleSheet(f"color: {LabPilotStyle.WARNING};")
        else:
            self.status_label.setText("✓ Ready")
            self.status_label.setStyleSheet(f"color: {LabPilotStyle.SUCCESS};")

# ===== MULTI-AXIS MOTOR WINDOW =====
class MotorMultiAxisWindow(QMainWindow):
    """Multi-axis Motor - Grid of axis cards"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument
        try:
            self.num_axes = int(instrument.dimensionality[0])
        except (ValueError, IndexError):
            self.num_axes = 2

        self.positions = [50.0] * self.num_axes
        self.target_positions = [50.0] * self.num_axes
        self.is_moving = [False] * self.num_axes
        self.axis_labels = ['X', 'Y', 'Z', 'U', 'V', 'W']

        self.setup_ui()
        self.setWindowTitle(f"{instrument.name} - Multi-Axis Motor Control")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 16, 16, 16)

        # Grid of axis cards
        self.grid_layout = QGridLayout()
        self.axis_cards = []

        cols = min(3, self.num_axes)
        for i in range(self.num_axes):
            card = self.create_axis_card(i)
            self.axis_cards.append(card)

            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(card, row, col)

        layout.addLayout(self.grid_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("All axes ready")
        self.setStatusBar(self.status_bar)

        self.resize(1200, 800)

    def create_axis_card(self, axis_index: int) -> QFrame:
        """Create individual axis control card"""
        card = QFrame()
        card.setMinimumSize(350, 400)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Header
        header_layout = QVBoxLayout()

        title = QLabel(f"{self.axis_labels[axis_index]} Axis")
        title.setFont(QFont("", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        status_label = QLabel("Ready")
        status_label.setProperty("class", "muted")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        setattr(self, f'status_label_{axis_index}', status_label)

        header_layout.addWidget(title)
        header_layout.addWidget(status_label)
        layout.addLayout(header_layout)

        # Position display card
        pos_card = QFrame()
        pos_card.setStyleSheet(f"background-color: {LabPilotStyle.BG_TERTIARY}; border-radius: 8px;")
        pos_layout = QGridLayout(pos_card)

        # Current position
        pos_layout.addWidget(QLabel("Current"), 0, 0)
        current_label = QLabel(f"{self.positions[axis_index]:.2f}")
        current_label.setFont(QFont("", 16, QFont.Weight.Bold))
        current_label.setStyleSheet(f"color: {LabPilotStyle.PRIMARY};")
        pos_layout.addWidget(current_label, 1, 0)
        pos_layout.addWidget(QLabel("mm"), 2, 0)
        setattr(self, f'current_label_{axis_index}', current_label)

        # Target position
        pos_layout.addWidget(QLabel("Target"), 0, 1)
        target_label = QLabel(f"{self.target_positions[axis_index]:.2f}")
        target_label.setFont(QFont("", 16, QFont.Weight.Bold))
        target_label.setStyleSheet(f"color: {LabPilotStyle.WARNING};")
        pos_layout.addWidget(target_label, 1, 1)
        pos_layout.addWidget(QLabel("mm"), 2, 1)
        setattr(self, f'target_label_{axis_index}', target_label)

        layout.addWidget(pos_card)

        # Controls
        controls_layout = QVBoxLayout()

        # Target input
        input_layout = QHBoxLayout()
        target_spinbox = ProfessionalSpinBox(0, 100, 2, "mm")
        target_spinbox.setValue(self.target_positions[axis_index])
        target_spinbox.valueChanged.connect(lambda v, i=axis_index: self.update_target(i, v))
        input_layout.addWidget(target_spinbox)
        setattr(self, f'target_spinbox_{axis_index}', target_spinbox)

        controls_layout.addLayout(input_layout)

        # Buttons
        buttons_layout = QHBoxLayout()

        home_btn = IconButton("", "🏠", "warning")
        home_btn.setFixedSize(40, 40)
        home_btn.clicked.connect(lambda: self.home_axis(axis_index))
        setattr(self, f'home_btn_{axis_index}', home_btn)

        move_btn = IconButton("", "→", "primary")
        move_btn.setFixedSize(40, 40)
        move_btn.clicked.connect(lambda: self.move_axis(axis_index))
        setattr(self, f'move_btn_{axis_index}', move_btn)

        stop_btn = IconButton("", "■", "danger")
        stop_btn.setFixedSize(40, 40)
        stop_btn.setEnabled(False)
        stop_btn.clicked.connect(lambda: self.stop_axis(axis_index))
        setattr(self, f'stop_btn_{axis_index}', stop_btn)

        buttons_layout.addWidget(home_btn)
        buttons_layout.addWidget(move_btn)
        buttons_layout.addWidget(stop_btn)

        controls_layout.addLayout(buttons_layout)

        # Slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 1000)
        slider.setValue(int(self.target_positions[axis_index] * 10))
        slider.valueChanged.connect(lambda v, i=axis_index: self.slider_changed(i, v))
        controls_layout.addWidget(slider)
        setattr(self, f'slider_{axis_index}', slider)

        layout.addLayout(controls_layout)

        return card

    def update_target(self, axis_index: int, value: float):
        """Update target position"""
        self.target_positions[axis_index] = value
        target_label = getattr(self, f'target_label_{axis_index}')
        target_label.setText(f"{value:.2f}")

        slider = getattr(self, f'slider_{axis_index}')
        slider.setValue(int(value * 10))

    def slider_changed(self, axis_index: int, value: int):
        """Update from slider"""
        target_value = value / 10.0
        self.target_positions[axis_index] = target_value

        spinbox = getattr(self, f'target_spinbox_{axis_index}')
        spinbox.setValue(target_value)

    def move_axis(self, axis_index: int):
        """Move specific axis"""
        self.is_moving[axis_index] = True

        # Update UI
        move_btn = getattr(self, f'move_btn_{axis_index}')
        stop_btn = getattr(self, f'stop_btn_{axis_index}')
        home_btn = getattr(self, f'home_btn_{axis_index}')
        status_label = getattr(self, f'status_label_{axis_index}')

        move_btn.setEnabled(False)
        stop_btn.setEnabled(True)
        home_btn.setEnabled(False)
        status_label.setText("⚡ Moving")
        status_label.setStyleSheet(f"color: {LabPilotStyle.PRIMARY};")

        # Simulate movement
        QTimer.singleShot(1500, lambda: self.finish_movement(axis_index))

    def home_axis(self, axis_index: int):
        """Home specific axis"""
        self.target_positions[axis_index] = 0.0
        spinbox = getattr(self, f'target_spinbox_{axis_index}')
        spinbox.setValue(0.0)
        self.move_axis(axis_index)

    def stop_axis(self, axis_index: int):
        """Stop specific axis"""
        self.is_moving[axis_index] = False
        self.finish_movement(axis_index)

    def finish_movement(self, axis_index: int):
        """Finish axis movement"""
        self.positions[axis_index] = self.target_positions[axis_index]
        self.is_moving[axis_index] = False

        # Update UI
        current_label = getattr(self, f'current_label_{axis_index}')
        move_btn = getattr(self, f'move_btn_{axis_index}')
        stop_btn = getattr(self, f'stop_btn_{axis_index}')
        home_btn = getattr(self, f'home_btn_{axis_index}')
        status_label = getattr(self, f'status_label_{axis_index}')

        current_label.setText(f"{self.positions[axis_index]:.2f}")
        move_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        home_btn.setEnabled(True)
        status_label.setText("✓ Ready")
        status_label.setStyleSheet(f"color: {LabPilotStyle.SUCCESS};")

        self.status_bar.showMessage(f"{self.axis_labels[axis_index]} axis: {self.positions[axis_index]:.2f} mm")

# ===== FACTORY FUNCTION =====
def create_instrument_window(instrument: DashboardInstrument) -> QMainWindow:
    """Factory function to create appropriate instrument window"""

    if instrument.kind == "detector":
        if instrument.dimensionality == "0D":
            return Detector0DWindow(instrument)
        elif instrument.dimensionality == "1D":
            return Detector1DWindow(instrument)
        elif instrument.dimensionality == "2D":
            return Detector2DWindow(instrument)

    elif instrument.kind == "motor":
        if instrument.dimensionality == "0D":
            return Motor0DWindow(instrument)
        elif instrument.dimensionality == "1D":
            return Motor1DWindow(instrument)
        else:
            return MotorMultiAxisWindow(instrument)

    raise ValueError(f"Unsupported instrument: {instrument.kind} {instrument.dimensionality}")