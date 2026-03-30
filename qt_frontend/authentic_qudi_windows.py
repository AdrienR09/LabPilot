"""
LabPilot Qudi-Style Instrument GUIs - Authentic Implementations
Based on actual qudi GUI patterns from Ulm-IQO/qudi and SchlauCohenLab/qudi-sclab
"""

import sys
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from PyQt6.QtWidgets import (
    QMainWindow, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox,
    QButtonGroup, QRadioButton, QGroupBox, QFrame, QSplitter, QTabWidget,
    QStatusBar, QToolBar, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QThread
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QAction
import pyqtgraph as pg
from .main import DashboardInstrument

class QudiStyleConstants:
    """Authentic qudi styling constants based on qudi source"""

    # Qudi color scheme (from qudi source)
    BG_DARK = "#2b2b2b"
    BG_MEDIUM = "#3c3c3c"
    BG_LIGHT = "#4a4a4a"
    FG_PRIMARY = "#ffffff"
    FG_SECONDARY = "#cccccc"
    FG_DISABLED = "#888888"

    # Qudi accent colors
    ACCENT_BLUE = "#4da6ff"
    ACCENT_GREEN = "#66cc66"
    ACCENT_ORANGE = "#ff9933"
    ACCENT_RED = "#ff6666"
    ACCENT_CYAN = "#17becf"

    # Plot colors (qudi palette)
    PLOT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

def apply_qudi_theme(app_or_widget):
    """Apply authentic qudi dark theme"""
    qudi_stylesheet = f"""
        QMainWindow {{
            background-color: {QudiStyleConstants.BG_DARK};
            color: {QudiStyleConstants.FG_PRIMARY};
        }}
        QWidget {{
            background-color: {QudiStyleConstants.BG_DARK};
            color: {QudiStyleConstants.FG_PRIMARY};
        }}
        QDockWidget {{
            background-color: {QudiStyleConstants.BG_MEDIUM};
            border: 1px solid #555555;
            titlebar-close-icon: url(close.png);
        }}
        QDockWidget::title {{
            text-align: center;
            background: {QudiStyleConstants.BG_LIGHT};
            padding: 5px;
        }}
        QGroupBox {{
            font-weight: bold;
            border: 2px solid #555555;
            border-radius: 5px;
            margin-top: 1ex;
            background-color: {QudiStyleConstants.BG_MEDIUM};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }}
        QPushButton {{
            background-color: {QudiStyleConstants.BG_LIGHT};
            border: 1px solid #666666;
            border-radius: 3px;
            padding: 5px;
            min-width: 60px;
        }}
        QPushButton:hover {{
            background-color: #5a5a5a;
        }}
        QPushButton:pressed {{
            background-color: #333333;
        }}
        QDoubleSpinBox, QSpinBox, QComboBox {{
            background-color: {QudiStyleConstants.BG_LIGHT};
            border: 1px solid #666666;
            border-radius: 3px;
            padding: 3px;
        }}
        QLabel {{
            color: {QudiStyleConstants.FG_PRIMARY};
        }}
    """

    try:
        app_or_widget.setStyleSheet(qudi_stylesheet)
    except:
        pass

# ===== 0D DETECTOR - TIME SERIES GUI (Authentic qudi pattern) =====

class QudiTimeSeriesWindow(QMainWindow):
    """0D Detector - Authentic qudi time_series GUI pattern"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument

        # Time series data storage
        self.time_data = []
        self.value_data = []
        self.max_points = 1000

        # Timers (qudi pattern)
        self.data_timer = QTimer()
        self.update_timer = QTimer()

        self.setup_qudi_ui()
        self.setup_qudi_plots()
        self.connect_qudi_signals()

        apply_qudi_theme(self)
        self.setWindowTitle(f"{instrument.name} - Time Series")
        self.setMinimumSize(800, 600)

    # Session Management Methods
    def get_session_settings(self) -> Dict[str, Any]:
        """Get window-specific settings for session saving"""
        return {
            'acquisition_running': hasattr(self, 'data_timer') and self.data_timer.isActive(),
            'update_interval': getattr(self, 'update_interval', 100),
            'plot_settings': {
                'y_range': self.plot_widget.getViewBox().viewRange()[1] if hasattr(self, 'plot_widget') else [0, 1000],
                'x_range': self.plot_widget.getViewBox().viewRange()[0] if hasattr(self, 'plot_widget') else [0, 100],
            },
            'current_value': getattr(self, 'current_value', 0.0),
        }

    def apply_session_settings(self, settings: Dict[str, Any]):
        """Apply window-specific settings from session loading"""
        try:
            # Restore acquisition state
            if settings.get('acquisition_running', False) and hasattr(self, 'start_acquisition'):
                # Don't auto-start acquisition, just set the state for user activation
                pass

            # Restore update interval
            if 'update_interval' in settings:
                self.update_interval = settings['update_interval']
                if hasattr(self, 'update_timer'):
                    self.update_timer.setInterval(self.update_interval)

            # Restore plot ranges
            if 'plot_settings' in settings and hasattr(self, 'plot_widget'):
                plot_settings = settings['plot_settings']
                if 'y_range' in plot_settings and 'x_range' in plot_settings:
                    self.plot_widget.setRange(
                        xRange=plot_settings['x_range'],
                        yRange=plot_settings['y_range'],
                        padding=0
                    )

            # Restore current value
            if 'current_value' in settings:
                self.current_value = settings['current_value']

        except Exception as e:
            print(f"Warning: Failed to apply some session settings: {e}")

    def setup_qudi_ui(self):
        """Setup authentic qudi dock widget architecture"""
        # Enable dock nesting (qudi pattern)
        self.setDockNestingEnabled(True)

        # Hide central widget (qudi pattern)
        central = QWidget()
        self.setCentralWidget(central)
        central.hide()

        # Create dock widgets (qudi pattern)
        self.setup_control_dock()
        self.setup_plot_dock()
        self.setup_status_dock()

    def setup_control_dock(self):
        """Control dock with qudi time_series pattern"""
        control_dock = QDockWidget("Data Acquisition Control", self)
        control_widget = QWidget()
        layout = QVBoxLayout(control_widget)

        # Acquisition settings group
        acq_group = QGroupBox("Acquisition Settings")
        acq_layout = QGridLayout(acq_group)

        # Trace length (qudi parameter)
        acq_layout.addWidget(QLabel("Trace Length:"), 0, 0)
        self.trace_length_spinbox = QDoubleSpinBox()
        self.trace_length_spinbox.setRange(1.0, 3600.0)
        self.trace_length_spinbox.setSuffix(" s")
        self.trace_length_spinbox.setValue(60.0)
        acq_layout.addWidget(self.trace_length_spinbox, 0, 1)

        # Data rate (qudi parameter)
        acq_layout.addWidget(QLabel("Data Rate:"), 1, 0)
        self.data_rate_spinbox = QDoubleSpinBox()
        self.data_rate_spinbox.setRange(0.1, 100.0)
        self.data_rate_spinbox.setSuffix(" Hz")
        self.data_rate_spinbox.setValue(1.0)
        acq_layout.addWidget(self.data_rate_spinbox, 1, 1)

        # Oversampling (qudi parameter)
        acq_layout.addWidget(QLabel("Oversampling:"), 2, 0)
        self.oversampling_spinbox = QSpinBox()
        self.oversampling_spinbox.setRange(1, 100)
        self.oversampling_spinbox.setValue(1)
        acq_layout.addWidget(self.oversampling_spinbox, 2, 1)

        layout.addWidget(acq_group)

        # Moving average (qudi pattern)
        avg_group = QGroupBox("Signal Processing")
        avg_layout = QGridLayout(avg_group)

        avg_layout.addWidget(QLabel("Moving Average:"), 0, 0)
        self.moving_average_spinbox = QSpinBox()
        self.moving_average_spinbox.setRange(1, 100)
        self.moving_average_spinbox.setValue(1)
        avg_layout.addWidget(self.moving_average_spinbox, 0, 1)

        layout.addWidget(avg_group)

        # Control buttons (qudi pattern)
        button_group = QGroupBox("Control")
        button_layout = QVBoxLayout(button_group)

        self.start_trace_btn = QPushButton("Start Trace")
        self.stop_trace_btn = QPushButton("Stop Trace")
        self.stop_trace_btn.setEnabled(False)
        self.record_btn = QPushButton("Start Recording")
        self.snapshot_btn = QPushButton("Snapshot")

        for btn in [self.start_trace_btn, self.stop_trace_btn, self.record_btn, self.snapshot_btn]:
            button_layout.addWidget(btn)

        layout.addWidget(button_group)
        layout.addStretch()

        control_dock.setWidget(control_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, control_dock)

    def setup_plot_dock(self):
        """Plot dock with qudi dual y-axis pattern"""
        plot_dock = QDockWidget("Time Series Plot", self)

        # Create plot widget with qudi styling
        self.plot_widget = pg.PlotWidget(
            background=QudiStyleConstants.BG_DARK,
            labels={'left': 'Signal (counts/s)', 'bottom': 'Time (s)'}
        )
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Configure qudi-style axes
        self.plot_widget.getAxis('left').setPen(QudiStyleConstants.FG_SECONDARY)
        self.plot_widget.getAxis('bottom').setPen(QudiStyleConstants.FG_SECONDARY)
        self.plot_widget.getAxis('left').setTextPen(QudiStyleConstants.FG_PRIMARY)
        self.plot_widget.getAxis('bottom').setTextPen(QudiStyleConstants.FG_PRIMARY)

        # Create second ViewBox for dual y-axis (qudi pattern)
        self.second_vb = pg.ViewBox()
        self.second_vb.setXLink(self.plot_widget.plotItem)
        self.plot_widget.scene().addItem(self.second_vb)

        # Add plot curves with qudi colors
        self.main_curve = self.plot_widget.plot(
            pen=pg.mkPen(QudiStyleConstants.ACCENT_BLUE, width=2),
            clipToView=True,
            autoDownsample=True
        )

        plot_dock.setWidget(self.plot_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, plot_dock)

    def setup_status_dock(self):
        """Status dock with current value display (qudi pattern)"""
        status_dock = QDockWidget("Current Values", self)
        status_widget = QWidget()
        layout = QVBoxLayout(status_widget)

        # Current value group (qudi pattern)
        curr_group = QGroupBox("Current Value")
        curr_layout = QGridLayout(curr_group)

        curr_layout.addWidget(QLabel("Channel:"), 0, 0)
        self.curr_value_combobox = QComboBox()
        self.curr_value_combobox.addItem("Signal")
        curr_layout.addWidget(self.curr_value_combobox, 0, 1)

        # Large value display
        self.current_value_label = QLabel("0.000")
        self.current_value_label.setFont(QFont("Consolas", 24, QFont.Weight.Bold))
        self.current_value_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_BLUE}; background: {QudiStyleConstants.BG_MEDIUM}; padding: 10px; border-radius: 5px;")
        self.current_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        curr_layout.addWidget(self.current_value_label, 1, 0, 1, 2)

        layout.addWidget(curr_group)
        layout.addStretch()

        status_dock.setWidget(status_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, status_dock)

    def setup_qudi_plots(self):
        """Initialize plots with qudi settings"""
        # Configure plot for scientific use
        pg.setConfigOptions(antialias=True, useOpenGL=True)

    def connect_qudi_signals(self):
        """Connect signals using qudi pattern"""
        self.start_trace_btn.clicked.connect(self.start_trace)
        self.stop_trace_btn.clicked.connect(self.stop_trace)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.snapshot_btn.clicked.connect(self.take_snapshot)

        # Setup timers (qudi pattern)
        self.data_timer.timeout.connect(self.update_data)
        self.update_timer.timeout.connect(self.update_plot)

    @pyqtSlot()
    def start_trace(self):
        """Start time series acquisition (qudi pattern)"""
        self.start_trace_btn.setEnabled(False)
        self.stop_trace_btn.setEnabled(True)

        # Clear data
        self.time_data = []
        self.value_data = []

        # Start timers
        data_interval = int(1000 / self.data_rate_spinbox.value())
        self.data_timer.start(data_interval)
        self.update_timer.start(100)  # 10Hz update rate

        self.statusBar().showMessage("Acquiring time series data...")

    @pyqtSlot()
    def stop_trace(self):
        """Stop time series acquisition"""
        self.data_timer.stop()
        self.update_timer.stop()

        self.start_trace_btn.setEnabled(True)
        self.stop_trace_btn.setEnabled(False)

        self.statusBar().showMessage("Time series stopped")

    @pyqtSlot()
    def update_data(self):
        """Update data point (qudi pattern)"""
        # Simulate realistic detector data
        if len(self.time_data) == 0:
            current_time = 0.0
        else:
            current_time = self.time_data[-1] + (1.0 / self.data_rate_spinbox.value())

        # Simulate signal with noise
        base_signal = 1000 + 200 * np.sin(0.1 * current_time)
        noise = np.random.poisson(base_signal)

        self.time_data.append(current_time)
        self.value_data.append(noise)

        # Keep data within trace length
        max_time = self.trace_length_spinbox.value()
        while self.time_data and (current_time - self.time_data[0]) > max_time:
            self.time_data.pop(0)
            self.value_data.pop(0)

        # Update current value display
        if self.value_data:
            self.current_value_label.setText(f"{self.value_data[-1]:.1f}")

    @pyqtSlot()
    def update_plot(self):
        """Update plot display (qudi pattern)"""
        if len(self.time_data) > 1:
            self.main_curve.setData(self.time_data, self.value_data)

    @pyqtSlot()
    def toggle_recording(self):
        """Toggle data recording (qudi pattern)"""
        # Implementation would save data to file
        pass

    @pyqtSlot()
    def take_snapshot(self):
        """Take snapshot of current data (qudi pattern)"""
        # Implementation would capture current state
        pass

# ===== 0D MOTOR - SWITCH GUI (qudi-sclab pattern) =====

class QudiSwitchWindow(QMainWindow):
    """0D Motor - Authentic qudi-sclab switch GUI pattern"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument

        # Switch states
        self.switch_states = ["OFF", "ON"]
        self.current_state = 0

        self.setup_switch_ui()
        self.setup_watchdog_timer()

        apply_qudi_theme(self)
        self.setWindowTitle(f"{instrument.name} - Switch Control")
        self.setMinimumSize(400, 300)

    def setup_switch_ui(self):
        """Setup qudi-sclab switch grid layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Grid layout (qudi-sclab pattern)
        main_layout = QVBoxLayout(central_widget)

        # Switch control group
        switch_group = QGroupBox(f"Switch Control - {self.instrument.name}")
        grid_layout = QGridLayout(switch_group)

        # Create switch buttons (qudi-sclab pattern)
        self.switch_buttons = QButtonGroup()

        for i, state in enumerate(self.switch_states):
            radio_btn = QRadioButton(state)
            radio_btn.setMinimumHeight(50)
            radio_btn.setStyleSheet(f"""
                QRadioButton {{
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px;
                }}
                QRadioButton::indicator {{
                    width: 20px;
                    height: 20px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {QudiStyleConstants.ACCENT_GREEN};
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: {QudiStyleConstants.BG_LIGHT};
                }}
            """)

            self.switch_buttons.addButton(radio_btn, i)
            grid_layout.addWidget(radio_btn, 0, i)

        # Set initial state
        self.switch_buttons.button(0).setChecked(True)

        main_layout.addWidget(switch_group)

        # Status group
        status_group = QGroupBox("Status")
        status_layout = QGridLayout(status_group)

        status_layout.addWidget(QLabel("Current State:"), 0, 0)
        self.state_label = QLabel("OFF")
        self.state_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.state_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_RED}; padding: 5px;")
        status_layout.addWidget(self.state_label, 0, 1)

        status_layout.addWidget(QLabel("Connection:"), 1, 0)
        self.connection_label = QLabel("Connected")
        self.connection_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_GREEN};")
        status_layout.addWidget(self.connection_label, 1, 1)

        main_layout.addWidget(status_group)

        # Control buttons
        control_group = QGroupBox("Control")
        control_layout = QHBoxLayout(control_group)

        self.apply_btn = QPushButton("Apply State")
        self.apply_btn.setMinimumHeight(40)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMinimumHeight(40)

        control_layout.addWidget(self.apply_btn)
        control_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(control_group)
        main_layout.addStretch()

        # Connect signals
        self.switch_buttons.idToggled.connect(self.on_state_changed)
        self.apply_btn.clicked.connect(self.apply_state)
        self.refresh_btn.clicked.connect(self.refresh_state)

    def setup_watchdog_timer(self):
        """Setup periodic state checking (qudi-sclab pattern)"""
        self.watchdog_timer = QTimer()
        self.watchdog_timer.timeout.connect(self.check_state)
        self.watchdog_timer.start(1000)  # 1Hz monitoring

    @pyqtSlot(int, bool)
    def on_state_changed(self, state_id, checked):
        """Handle state change (qudi-sclab pattern)"""
        if checked:
            self.current_state = state_id
            state_name = self.switch_states[state_id]
            self.state_label.setText(state_name)

            # Update color based on state
            if state_name == "ON":
                self.state_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_GREEN}; padding: 5px;")
            else:
                self.state_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_RED}; padding: 5px;")

    @pyqtSlot()
    def apply_state(self):
        """Apply selected state (qudi-sclab pattern)"""
        state_name = self.switch_states[self.current_state]
        self.statusBar().showMessage(f"Applied state: {state_name}")

    @pyqtSlot()
    def refresh_state(self):
        """Refresh current state (qudi-sclab pattern)"""
        self.statusBar().showMessage("State refreshed")

    @pyqtSlot()
    def check_state(self):
        """Periodic state check (qudi-sclab watchdog pattern)"""
        # In real implementation, would query hardware
        pass

    # Session Management Methods
    def get_session_settings(self) -> Dict[str, Any]:
        """Get window-specific settings for session saving"""
        return {
            'switch_states': {f"channel_{i}": radio.isChecked()
                            for i, radio in enumerate([self.channel0_radio, self.channel1_radio, self.channel2_radio, self.channel3_radio])},
            'current_channel': getattr(self, 'current_channel', 0),
        }

    def apply_session_settings(self, settings: Dict[str, Any]):
        """Apply window-specific settings from session loading"""
        try:
            if 'switch_states' in settings:
                switch_states = settings['switch_states']
                radios = [self.channel0_radio, self.channel1_radio, self.channel2_radio, self.channel3_radio]
                for i, radio in enumerate(radios):
                    if f"channel_{i}" in switch_states:
                        radio.setChecked(switch_states[f"channel_{i}"])

            if 'current_channel' in settings:
                self.current_channel = settings['current_channel']

        except Exception as e:
            print(f"Warning: Failed to apply some session settings: {e}")

# ===== 1D MOTOR - ACTUATOR GUI (qudi-sclab pattern) =====

class QudiActuatorWindow(QMainWindow):
    """1D Motor - Authentic qudi-sclab actuator GUI pattern"""

    def __init__(self, instrument: DashboardInstrument, parent=None):
        super().__init__(parent)
        self.instrument = instrument

        # Actuator state
        self.current_position = 0.0
        self.target_position = 0.0
        self.is_moving = False
        self.constraints = {
            'pos_min': -100.0,
            'pos_max': 100.0,
            'unit': 'mm',
            'step_min': 0.001
        }

        self.setup_actuator_ui()
        self.setup_position_timer()

        apply_qudi_theme(self)
        self.setWindowTitle(f"{instrument.name} - Actuator Control")
        self.setMinimumSize(600, 500)

    def setup_actuator_ui(self):
        """Setup qudi-sclab actuator dock layout"""
        # Enable dock nesting (qudi pattern)
        self.setDockNestingEnabled(True)

        # Create dock widget for this axis (qudi-sclab pattern)
        axis_dock = QDockWidget(f"Axis Control - {self.instrument.name}", self)
        axis_widget = QWidget()
        layout = QVBoxLayout(axis_widget)

        # Position display (qudi-sclab pattern)
        pos_group = QGroupBox("Current Position")
        pos_layout = QVBoxLayout(pos_group)

        self.position_label = QLabel(f"{self.current_position:.3f} {self.constraints['unit']}")
        self.position_label.setFont(QFont("Consolas", 20, QFont.Weight.Bold))
        self.position_label.setStyleSheet(f"""
            color: {QudiStyleConstants.ACCENT_BLUE};
            background-color: {QudiStyleConstants.BG_MEDIUM};
            padding: 15px;
            border-radius: 5px;
            border: 2px solid #666666;
        """)
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pos_layout.addWidget(self.position_label)

        layout.addWidget(pos_group)

        # Movement control (qudi-sclab pattern)
        move_group = QGroupBox("Movement Control")
        move_layout = QGridLayout(move_group)

        # Mode selection (qudi-sclab pattern)
        self.abs_radio = QRadioButton("Absolute")
        self.rel_radio = QRadioButton("Relative")
        self.abs_radio.setChecked(True)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.abs_radio)
        mode_layout.addWidget(self.rel_radio)
        move_layout.addLayout(mode_layout, 0, 0, 1, 2)

        # Target position
        move_layout.addWidget(QLabel("Target Position:"), 1, 0)
        self.target_spinbox = QDoubleSpinBox()
        self.target_spinbox.setRange(self.constraints['pos_min'], self.constraints['pos_max'])
        self.target_spinbox.setDecimals(3)
        self.target_spinbox.setSuffix(f" {self.constraints['unit']}")
        self.target_spinbox.setValue(0.0)
        move_layout.addWidget(self.target_spinbox, 1, 1)

        # Move buttons
        self.move_btn = QPushButton("Move")
        self.move_btn.setMinimumHeight(40)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)

        move_layout.addWidget(self.move_btn, 2, 0)
        move_layout.addWidget(self.stop_btn, 2, 1)

        layout.addWidget(move_group)

        # Status display (qudi-sclab pattern)
        status_group = QGroupBox("Status")
        status_layout = QGridLayout(status_group)

        status_layout.addWidget(QLabel("Status:"), 0, 0)
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_GREEN}; font-weight: bold;")
        status_layout.addWidget(self.status_label, 0, 1)

        status_layout.addWidget(QLabel("Target:"), 1, 0)
        self.target_display_label = QLabel("0.000 mm")
        status_layout.addWidget(self.target_display_label, 1, 1)

        layout.addWidget(status_group)
        layout.addStretch()

        axis_dock.setWidget(axis_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, axis_dock)

        # Connect signals
        self.abs_radio.toggled.connect(self.on_mode_changed)
        self.rel_radio.toggled.connect(self.on_mode_changed)
        self.move_btn.clicked.connect(self.start_move)
        self.stop_btn.clicked.connect(self.stop_move)

    def setup_position_timer(self):
        """Setup fast position updates (qudi-sclab 10ms pattern)"""
        # Position update timer (10ms like qudi-sclab)
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.update_position_display)
        self.position_timer.start(10)

        # Status update timer (100ms like qudi-sclab)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(100)

        # Movement simulation timer
        self.movement_timer = QTimer()
        self.movement_timer.timeout.connect(self.simulate_movement)

    @pyqtSlot(bool)
    def on_mode_changed(self, checked):
        """Handle movement mode change (qudi-sclab pattern)"""
        if self.rel_radio.isChecked():
            # Adjust range for relative movement
            max_rel_pos = self.constraints['pos_max'] - self.current_position
            min_rel_pos = self.constraints['pos_min'] - self.current_position
            self.target_spinbox.setRange(min_rel_pos, max_rel_pos)
            self.target_spinbox.setValue(0.0)
        else:
            # Absolute movement - full range
            self.target_spinbox.setRange(self.constraints['pos_min'], self.constraints['pos_max'])
            self.target_spinbox.setValue(self.current_position)

    @pyqtSlot()
    def start_move(self):
        """Start movement (qudi-sclab pattern)"""
        if self.abs_radio.isChecked():
            # Absolute movement
            self.target_position = self.target_spinbox.value()
        else:
            # Relative movement
            self.target_position = self.current_position + self.target_spinbox.value()

        self.is_moving = True
        self.move_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Start movement simulation
        self.movement_timer.start(50)  # 20Hz movement updates

        self.target_display_label.setText(f"{self.target_position:.3f} {self.constraints['unit']}")
        self.status_label.setText("Moving")
        self.status_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_ORANGE}; font-weight: bold;")

    @pyqtSlot()
    def stop_move(self):
        """Stop movement (qudi-sclab pattern)"""
        self.is_moving = False
        self.movement_timer.stop()

        self.move_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        self.status_label.setText("Idle")
        self.status_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_GREEN}; font-weight: bold;")

    @pyqtSlot()
    def simulate_movement(self):
        """Simulate actuator movement"""
        if not self.is_moving:
            return

        # Simple movement simulation
        distance = self.target_position - self.current_position
        if abs(distance) < 0.001:
            # Reached target
            self.current_position = self.target_position
            self.stop_move()
        else:
            # Move towards target
            step = 0.1 if distance > 0 else -0.1
            self.current_position += step

    @pyqtSlot()
    def update_position_display(self):
        """Update position display (qudi-sclab 10ms pattern)"""
        # Format like qudi: ScaledFloat with unit
        self.position_label.setText(f"{self.current_position:.3f} {self.constraints['unit']}")

    @pyqtSlot()
    def update_status(self):
        """Update status (qudi-sclab 100ms pattern)"""
        # In real implementation, would check hardware status
        pass

    # Session Management Methods
    def get_session_settings(self) -> Dict[str, Any]:
        """Get window-specific settings for session saving"""
        return {
            'current_position': self.current_position,
            'target_position': getattr(self, 'target_position', self.current_position),
            'is_moving': getattr(self, 'is_moving', False),
            'movement_mode': 'relative' if hasattr(self, 'rel_radio') and self.rel_radio.isChecked() else 'absolute',
            'constraints': self.constraints,
        }

    def apply_session_settings(self, settings: Dict[str, Any]):
        """Apply window-specific settings from session loading"""
        try:
            if 'current_position' in settings:
                self.current_position = settings['current_position']

            if 'target_position' in settings:
                self.target_position = settings['target_position']

            if 'movement_mode' in settings and hasattr(self, 'abs_radio') and hasattr(self, 'rel_radio'):
                if settings['movement_mode'] == 'relative':
                    self.rel_radio.setChecked(True)
                else:
                    self.abs_radio.setChecked(True)

            if 'constraints' in settings:
                self.constraints.update(settings['constraints'])

            # Update displays
            if hasattr(self, 'update_position_display'):
                self.update_position_display()

        except Exception as e:
            print(f"Warning: Failed to apply some session settings: {e}")


# ===== SPECTROMETER WINDOW (1D DETECTOR) =====

class QudiSpectrometerWindow(QMainWindow):
    """
    Authentic qudi spectrometer GUI (1D detector)
    Based on https://github.com/Ulm-IQO/qudi/tree/master/gui/spectrometer
    """

    def __init__(self, instrument: DashboardInstrument):
        super().__init__()
        self.instrument = instrument
        self.setWindowTitle(f"Spectrometer - {instrument.name}")
        self.setMinimumSize(1000, 600)

        # Spectrometer state
        self.wavelengths = np.linspace(400, 800, 2048)  # nm
        self.spectrum_data = np.zeros(2048)
        self.background_data = None
        self.acquiring = False
        self.integration_time = 100  # ms

        # Setup UI with qudi dock pattern
        self.setup_ui()
        self.setup_acquisition_timer()

        # Apply qudi styling
        apply_qudi_theme(self)

    def setup_ui(self):
        """Setup spectrometer UI with qudi patterns"""
        # Central widget with plot
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create plot widget - qudi uses PlotWidget for spectra
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(QudiStyleConstants.BG_DARK)
        self.plot_widget.setLabel('left', 'Intensity', units='counts')
        self.plot_widget.setLabel('bottom', 'Wavelength', units='nm')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Spectrum curve
        self.spectrum_curve = self.plot_widget.plot(
            pen=pg.mkPen(color=QudiStyleConstants.ACCENT_CYAN, width=2),
            name='Spectrum'
        )

        # Background curve (if loaded)
        self.background_curve = self.plot_widget.plot(
            pen=pg.mkPen(color=QudiStyleConstants.ACCENT_ORANGE, width=1, style=Qt.PenStyle.DashLine),
            name='Background'
        )

        layout.addWidget(self.plot_widget)

        # Setup control docks (qudi pattern)
        self.setup_control_dock()
        self.setup_settings_dock()

    def setup_control_dock(self):
        """Control dock for acquisition (qudi pattern)"""
        control_dock = QDockWidget("Control", self)
        control_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        control_widget = QWidget()
        layout = QVBoxLayout(control_widget)

        # Acquisition control group (qudi pattern)
        acq_group = QGroupBox("Acquisition")
        acq_layout = QGridLayout(acq_group)

        # Start/Stop buttons (qudi pattern)
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet(f"background-color: {QudiStyleConstants.ACCENT_GREEN};")
        self.start_btn.clicked.connect(self.start_acquisition)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(f"background-color: {QudiStyleConstants.ACCENT_RED};")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_acquisition)

        acq_layout.addWidget(self.start_btn, 0, 0)
        acq_layout.addWidget(self.stop_btn, 0, 1)

        # Integration time control
        acq_layout.addWidget(QLabel("Integration Time (ms):"), 1, 0)
        self.integration_spinbox = QSpinBox()
        self.integration_spinbox.setRange(1, 10000)
        self.integration_spinbox.setValue(self.integration_time)
        self.integration_spinbox.valueChanged.connect(self.on_integration_changed)
        acq_layout.addWidget(self.integration_spinbox, 1, 1)

        # Number of averages
        acq_layout.addWidget(QLabel("Averages:"), 2, 0)
        self.averages_spinbox = QSpinBox()
        self.averages_spinbox.setRange(1, 1000)
        self.averages_spinbox.setValue(1)
        acq_layout.addWidget(self.averages_spinbox, 2, 1)

        layout.addWidget(acq_group)

        # Background subtraction group
        bg_group = QGroupBox("Background")
        bg_layout = QVBoxLayout(bg_group)

        self.record_bg_btn = QPushButton("Record Background")
        self.record_bg_btn.clicked.connect(self.record_background)
        bg_layout.addWidget(self.record_bg_btn)

        self.clear_bg_btn = QPushButton("Clear Background")
        self.clear_bg_btn.clicked.connect(self.clear_background)
        bg_layout.addWidget(self.clear_bg_btn)

        self.subtract_bg_checkbox = QCheckBox("Subtract Background")
        bg_layout.addWidget(self.subtract_bg_checkbox)

        layout.addWidget(bg_group)

        # Data info group
        info_group = QGroupBox("Spectrum Info")
        info_layout = QGridLayout(info_group)

        info_layout.addWidget(QLabel("Peak Wavelength:"), 0, 0)
        self.peak_wl_label = QLabel("--- nm")
        self.peak_wl_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_CYAN}; font-weight: bold;")
        info_layout.addWidget(self.peak_wl_label, 0, 1)

        info_layout.addWidget(QLabel("Peak Intensity:"), 1, 0)
        self.peak_int_label = QLabel("--- counts")
        self.peak_int_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_CYAN}; font-weight: bold;")
        info_layout.addWidget(self.peak_int_label, 1, 1)

        info_layout.addWidget(QLabel("Total Intensity:"), 2, 0)
        self.total_int_label = QLabel("--- counts")
        info_layout.addWidget(self.total_int_label, 2, 1)

        layout.addWidget(info_group)
        layout.addStretch()

        control_dock.setWidget(control_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, control_dock)

    def setup_settings_dock(self):
        """Settings dock for wavelength range (qudi pattern)"""
        settings_dock = QDockWidget("Settings", self)
        settings_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                 QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        settings_widget = QWidget()
        layout = QVBoxLayout(settings_widget)

        # Wavelength range group
        wl_group = QGroupBox("Wavelength Range")
        wl_layout = QGridLayout(wl_group)

        wl_layout.addWidget(QLabel("Min (nm):"), 0, 0)
        self.wl_min_spinbox = QDoubleSpinBox()
        self.wl_min_spinbox.setRange(200, 2000)
        self.wl_min_spinbox.setValue(400)
        self.wl_min_spinbox.setDecimals(1)
        wl_layout.addWidget(self.wl_min_spinbox, 0, 1)

        wl_layout.addWidget(QLabel("Max (nm):"), 1, 0)
        self.wl_max_spinbox = QDoubleSpinBox()
        self.wl_max_spinbox.setRange(200, 2000)
        self.wl_max_spinbox.setValue(800)
        self.wl_max_spinbox.setDecimals(1)
        wl_layout.addWidget(self.wl_max_spinbox, 1, 1)

        layout.addWidget(wl_group)
        layout.addStretch()

        settings_dock.setWidget(settings_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, settings_dock)

    def setup_acquisition_timer(self):
        """Setup acquisition timer (qudi pattern)"""
        self.acq_timer = QTimer()
        self.acq_timer.timeout.connect(self.acquire_spectrum)

    @pyqtSlot()
    def start_acquisition(self):
        """Start continuous acquisition (qudi pattern)"""
        self.acquiring = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.acq_timer.start(self.integration_time)

    @pyqtSlot()
    def stop_acquisition(self):
        """Stop acquisition (qudi pattern)"""
        self.acquiring = False
        self.acq_timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    @pyqtSlot(int)
    def on_integration_changed(self, value):
        """Handle integration time change"""
        self.integration_time = value
        if self.acquiring:
            self.acq_timer.setInterval(value)

    @pyqtSlot()
    def acquire_spectrum(self):
        """Acquire and display spectrum (qudi pattern)"""
        # Simulate spectrum (Gaussian peak with noise)
        center_wl = 590 + np.random.randn() * 5
        width = 20
        self.spectrum_data = 1000 * np.exp(-0.5 * ((self.wavelengths - center_wl) / width) ** 2)
        self.spectrum_data += np.random.randn(len(self.wavelengths)) * 50  # Noise
        self.spectrum_data = np.maximum(self.spectrum_data, 0)  # No negative counts

        # Apply background subtraction if enabled
        display_data = self.spectrum_data.copy()
        if self.subtract_bg_checkbox.isChecked() and self.background_data is not None:
            display_data -= self.background_data
            display_data = np.maximum(display_data, 0)

        # Update plot
        self.spectrum_curve.setData(self.wavelengths, display_data)

        # Update info labels
        peak_idx = np.argmax(display_data)
        self.peak_wl_label.setText(f"{self.wavelengths[peak_idx]:.1f} nm")
        self.peak_int_label.setText(f"{display_data[peak_idx]:.0f} counts")
        self.total_int_label.setText(f"{np.sum(display_data):.0f} counts")

    @pyqtSlot()
    def record_background(self):
        """Record current spectrum as background"""
        if len(self.spectrum_data) > 0:
            self.background_data = self.spectrum_data.copy()
            self.background_curve.setData(self.wavelengths, self.background_data)

    @pyqtSlot()
    def clear_background(self):
        """Clear background spectrum"""
        self.background_data = None
        self.background_curve.setData([], [])

    # Session Management Methods
    def get_session_settings(self) -> Dict[str, Any]:
        """Get window-specific settings for session saving"""
        return {
            'integration_time': self.integration_time,
            'acquiring': self.acquiring,
            'averages': self.averages_spinbox.value() if hasattr(self, 'averages_spinbox') else 1,
            'wavelength_range': {
                'min': self.wl_min_spinbox.value() if hasattr(self, 'wl_min_spinbox') else 400,
                'max': self.wl_max_spinbox.value() if hasattr(self, 'wl_max_spinbox') else 800,
            },
            'background_subtraction': self.subtract_bg_checkbox.isChecked() if hasattr(self, 'subtract_bg_checkbox') else False,
        }

    def apply_session_settings(self, settings: Dict[str, Any]):
        """Apply window-specific settings from session loading"""
        try:
            if 'integration_time' in settings:
                self.integration_time = settings['integration_time']
                if hasattr(self, 'integration_spinbox'):
                    self.integration_spinbox.setValue(self.integration_time)

            if 'averages' in settings and hasattr(self, 'averages_spinbox'):
                self.averages_spinbox.setValue(settings['averages'])

            if 'wavelength_range' in settings:
                wl_range = settings['wavelength_range']
                if hasattr(self, 'wl_min_spinbox') and 'min' in wl_range:
                    self.wl_min_spinbox.setValue(wl_range['min'])
                if hasattr(self, 'wl_max_spinbox') and 'max' in wl_range:
                    self.wl_max_spinbox.setValue(wl_range['max'])

            if 'background_subtraction' in settings and hasattr(self, 'subtract_bg_checkbox'):
                self.subtract_bg_checkbox.setChecked(settings['background_subtraction'])

        except Exception as e:
            print(f"Warning: Failed to apply some session settings: {e}")


# ===== CAMERA WINDOW (2D DETECTOR) =====

class QudiCameraWindow(QMainWindow):
    """
    Authentic qudi camera GUI (2D detector)
    Based on https://github.com/Ulm-IQO/qudi/tree/master/gui/camera
    """

    def __init__(self, instrument: DashboardInstrument):
        super().__init__()
        self.instrument = instrument
        self.setWindowTitle(f"Camera - {instrument.name}")
        self.setMinimumSize(1200, 700)

        # Camera state
        self.image_data = None
        self.acquiring = False
        self.exposure_time = 100  # ms
        self.gain = 1.0
        self.frame_count = 0

        # Setup UI with qudi dock pattern
        self.setup_ui()
        self.setup_acquisition_timer()

        # Apply qudi styling
        apply_qudi_theme(self)

    def setup_ui(self):
        """Setup camera UI with qudi patterns"""
        # Central widget with image view
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create image view widget - qudi uses ImageView for cameras
        self.image_view = pg.ImageView()
        self.image_view.ui.roiBtn.hide()  # Hide ROI button like qudi
        self.image_view.ui.menuBtn.hide()  # Hide menu button like qudi

        # Set color map (qudi uses 'viridis' or 'hot')
        self.image_view.setColorMap(pg.colormap.get('viridis'))

        layout.addWidget(self.image_view)

        # Setup control docks (qudi pattern)
        self.setup_control_dock()
        self.setup_roi_dock()

    def setup_control_dock(self):
        """Control dock for camera settings (qudi pattern)"""
        control_dock = QDockWidget("Control", self)
        control_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        control_widget = QWidget()
        layout = QVBoxLayout(control_widget)

        # Acquisition control group (qudi pattern)
        acq_group = QGroupBox("Acquisition")
        acq_layout = QGridLayout(acq_group)

        # Live/Snap buttons (qudi pattern)
        self.live_btn = QPushButton("Live View")
        self.live_btn.setCheckable(True)
        self.live_btn.setStyleSheet(f"background-color: {QudiStyleConstants.ACCENT_GREEN};")
        self.live_btn.clicked.connect(self.toggle_live_view)

        self.snap_btn = QPushButton("Snap")
        self.snap_btn.clicked.connect(self.snap_image)

        acq_layout.addWidget(self.live_btn, 0, 0)
        acq_layout.addWidget(self.snap_btn, 0, 1)

        # Exposure time control
        acq_layout.addWidget(QLabel("Exposure (ms):"), 1, 0)
        self.exposure_spinbox = QDoubleSpinBox()
        self.exposure_spinbox.setRange(0.1, 10000)
        self.exposure_spinbox.setValue(self.exposure_time)
        self.exposure_spinbox.setDecimals(1)
        self.exposure_spinbox.valueChanged.connect(self.on_exposure_changed)
        acq_layout.addWidget(self.exposure_spinbox, 1, 1)

        # Gain control
        acq_layout.addWidget(QLabel("Gain:"), 2, 0)
        self.gain_spinbox = QDoubleSpinBox()
        self.gain_spinbox.setRange(1.0, 16.0)
        self.gain_spinbox.setValue(self.gain)
        self.gain_spinbox.setDecimals(1)
        self.gain_spinbox.valueChanged.connect(self.on_gain_changed)
        acq_layout.addWidget(self.gain_spinbox, 2, 1)

        # Frame counter
        acq_layout.addWidget(QLabel("Frame Count:"), 3, 0)
        self.frame_count_label = QLabel("0")
        self.frame_count_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_CYAN}; font-weight: bold;")
        acq_layout.addWidget(self.frame_count_label, 3, 1)

        layout.addWidget(acq_group)

        # Image info group
        info_group = QGroupBox("Image Info")
        info_layout = QGridLayout(info_group)

        info_layout.addWidget(QLabel("Max Intensity:"), 0, 0)
        self.max_int_label = QLabel("---")
        self.max_int_label.setStyleSheet(f"color: {QudiStyleConstants.ACCENT_CYAN}; font-weight: bold;")
        info_layout.addWidget(self.max_int_label, 0, 1)

        info_layout.addWidget(QLabel("Min Intensity:"), 1, 0)
        self.min_int_label = QLabel("---")
        info_layout.addWidget(self.min_int_label, 1, 1)

        info_layout.addWidget(QLabel("Mean Intensity:"), 2, 0)
        self.mean_int_label = QLabel("---")
        info_layout.addWidget(self.mean_int_label, 2, 1)

        layout.addWidget(info_group)

        # Color map group
        cmap_group = QGroupBox("Display")
        cmap_layout = QVBoxLayout(cmap_group)

        cmap_layout.addWidget(QLabel("Color Map:"))
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(['viridis', 'hot', 'cool', 'gray', 'inferno'])
        self.cmap_combo.currentTextChanged.connect(self.on_colormap_changed)
        cmap_layout.addWidget(self.cmap_combo)

        self.autoscale_checkbox = QCheckBox("Auto Scale")
        self.autoscale_checkbox.setChecked(True)
        cmap_layout.addWidget(self.autoscale_checkbox)

        layout.addWidget(cmap_group)
        layout.addStretch()

        control_dock.setWidget(control_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, control_dock)

    def setup_roi_dock(self):
        """ROI analysis dock (qudi pattern)"""
        roi_dock = QDockWidget("ROI Analysis", self)
        roi_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                            QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        roi_widget = QWidget()
        layout = QVBoxLayout(roi_widget)

        # ROI statistics
        roi_group = QGroupBox("Statistics")
        roi_layout = QGridLayout(roi_group)

        roi_layout.addWidget(QLabel("ROI Sum:"), 0, 0)
        self.roi_sum_label = QLabel("---")
        roi_layout.addWidget(self.roi_sum_label, 0, 1)

        roi_layout.addWidget(QLabel("ROI Mean:"), 1, 0)
        self.roi_mean_label = QLabel("---")
        roi_layout.addWidget(self.roi_mean_label, 1, 1)

        layout.addWidget(roi_group)
        layout.addStretch()

        roi_dock.setWidget(roi_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, roi_dock)

    def setup_acquisition_timer(self):
        """Setup acquisition timer (qudi pattern)"""
        self.acq_timer = QTimer()
        self.acq_timer.timeout.connect(self.acquire_image)

    @pyqtSlot(bool)
    def toggle_live_view(self, checked):
        """Toggle live view (qudi pattern)"""
        if checked:
            self.acquiring = True
            self.acq_timer.start(int(self.exposure_time))
            self.live_btn.setText("Stop Live")
            self.live_btn.setStyleSheet(f"background-color: {QudiStyleConstants.ACCENT_RED};")
        else:
            self.acquiring = False
            self.acq_timer.stop()
            self.live_btn.setText("Live View")
            self.live_btn.setStyleSheet(f"background-color: {QudiStyleConstants.ACCENT_GREEN};")

    @pyqtSlot()
    def snap_image(self):
        """Snap single image (qudi pattern)"""
        self.acquire_image()

    @pyqtSlot(float)
    def on_exposure_changed(self, value):
        """Handle exposure time change"""
        self.exposure_time = value
        if self.acquiring:
            self.acq_timer.setInterval(int(value))

    @pyqtSlot(float)
    def on_gain_changed(self, value):
        """Handle gain change"""
        self.gain = value

    @pyqtSlot(str)
    def on_colormap_changed(self, cmap_name):
        """Change color map"""
        self.image_view.setColorMap(pg.colormap.get(cmap_name))

    @pyqtSlot()
    def acquire_image(self):
        """Acquire and display image (qudi pattern)"""
        # Simulate camera image (2D Gaussian spot with noise)
        size = 512
        x = np.linspace(-size/2, size/2, size)
        y = np.linspace(-size/2, size/2, size)
        X, Y = np.meshgrid(x, y)

        # Random center position
        cx = np.random.randn() * 20
        cy = np.random.randn() * 20

        # Gaussian spot
        sigma = 40
        self.image_data = 1000 * self.gain * np.exp(-((X - cx)**2 + (Y - cy)**2) / (2 * sigma**2))

        # Add noise
        self.image_data += np.random.randn(size, size) * 10 * self.gain
        self.image_data = np.maximum(self.image_data, 0)  # No negative counts

        # Update display
        self.image_view.setImage(self.image_data.T, autoRange=False, autoLevels=self.autoscale_checkbox.isChecked())

        # Update info labels
        self.max_int_label.setText(f"{np.max(self.image_data):.0f}")
        self.min_int_label.setText(f"{np.min(self.image_data):.0f}")
        self.mean_int_label.setText(f"{np.mean(self.image_data):.0f}")

        # Update frame counter
        self.frame_count += 1
        self.frame_count_label.setText(str(self.frame_count))

    # Session Management Methods
    def get_session_settings(self) -> Dict[str, Any]:
        """Get window-specific settings for session saving"""
        return {
            'exposure_time': self.exposure_time,
            'gain': self.gain,
            'acquiring': self.acquiring,
            'frame_count': self.frame_count,
            'colormap': self.cmap_combo.currentText() if hasattr(self, 'cmap_combo') else 'viridis',
            'autoscale': self.autoscale_checkbox.isChecked() if hasattr(self, 'autoscale_checkbox') else True,
        }

    def apply_session_settings(self, settings: Dict[str, Any]):
        """Apply window-specific settings from session loading"""
        try:
            if 'exposure_time' in settings:
                self.exposure_time = settings['exposure_time']
                if hasattr(self, 'exposure_spinbox'):
                    self.exposure_spinbox.setValue(self.exposure_time)

            if 'gain' in settings:
                self.gain = settings['gain']
                if hasattr(self, 'gain_spinbox'):
                    self.gain_spinbox.setValue(self.gain)

            if 'frame_count' in settings:
                self.frame_count = settings['frame_count']
                if hasattr(self, 'frame_count_label'):
                    self.frame_count_label.setText(str(self.frame_count))

            if 'colormap' in settings and hasattr(self, 'cmap_combo'):
                index = self.cmap_combo.findText(settings['colormap'])
                if index >= 0:
                    self.cmap_combo.setCurrentIndex(index)

            if 'autoscale' in settings and hasattr(self, 'autoscale_checkbox'):
                self.autoscale_checkbox.setChecked(settings['autoscale'])

        except Exception as e:
            print(f"Warning: Failed to apply some session settings: {e}")


# ===== FACTORY FUNCTION =====

def create_instrument_window(instrument: DashboardInstrument) -> QMainWindow:
    """Factory function to create authentic qudi-style instrument windows"""

    window_map = {
        ('detector', '0D'): QudiTimeSeriesWindow,
        ('detector', '1D'): QudiSpectrometerWindow,
        ('detector', '2D'): QudiCameraWindow,
        ('motor', '0D'): QudiSwitchWindow,
        ('motor', '1D'): QudiActuatorWindow,
        ('motor', '2D'): QudiActuatorWindow,
        ('motor', '3D'): QudiActuatorWindow,
    }

    # Get window class
    window_class = window_map.get((instrument.kind, instrument.dimensionality))

    if window_class is None:
        # Default fallback
        window_class = QudiTimeSeriesWindow

    return window_class(instrument)