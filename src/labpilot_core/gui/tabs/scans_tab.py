"""Scans tab for running experiments."""

from __future__ import annotations

import asyncio

from PyQt6.QtCore import QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from labpilot_core import Session
from labpilot_core.plans.base import ScanPlan
from labpilot_core.plans.scan import scan


class AsyncRunner(QRunnable):
    """Helper to run async code in Qt thread pool."""

    def __init__(self, coro):
        super().__init__()
        self.coro = coro

    def run(self):
        """Execute async coroutine."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.coro)
        finally:
            loop.close()


class ScansTab(QWidget):
    """Tab for configuring and running scans.

    Allows user to:
    - Select motor and detector from session devices
    - Configure scan parameters
    - Run scans and view progress
    """

    # Signals
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    scan_error = pyqtSignal(str)
    scan_data = pyqtSignal(dict)  # Event data

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.session: Session | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self.scan_running = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Configuration panel
        config_group = QGroupBox("📊 Scan Configuration")
        config_layout = QFormLayout()

        # Device selection
        self.motor_combo = QComboBox()
        self.detector_combo = QComboBox()

        config_layout.addRow("Motor:", self.motor_combo)
        config_layout.addRow("Detector:", self.detector_combo)

        # Scan parameters
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(-1000, 1000)
        self.start_spin.setValue(0.0)

        self.stop_spin = QDoubleSpinBox()
        self.stop_spin.setRange(-1000, 1000)
        self.stop_spin.setValue(10.0)

        self.num_spin = QSpinBox()
        self.num_spin.setRange(2, 1000)
        self.num_spin.setValue(11)

        config_layout.addRow("Start:", self.start_spin)
        config_layout.addRow("Stop:", self.stop_spin)
        config_layout.addRow("Num Points:", self.num_spin)

        config_group.setLayout(config_layout)
        config_group.setStyleSheet(
            """
            QGroupBox {
                color: #ffffff;
                border: 1px solid #3c3c3c;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QComboBox, QDoubleSpinBox, QSpinBox {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                padding: 4px;
            }
        """
        )
        layout.addWidget(config_group)

        # Control buttons
        btn_layout = QHBoxLayout()

        self.btn_run = QPushButton("▶️ Run Scan")
        self.btn_stop = QPushButton("⏹️ Stop")

        self.btn_run.setStyleSheet(
            """
            QPushButton {
                background-color: #4a9eff;
                color: #ffffff;
                border: none;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a8eef;
            }
            QPushButton:disabled {
                background-color: #2b2b2b;
                color: #666666;
            }
        """
        )

        self.btn_stop.setStyleSheet(
            """
            QPushButton {
                background-color: #ff4a4a;
                color: #ffffff;
                border: none;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ef3a3a;
            }
            QPushButton:disabled {
                background-color: #2b2b2b;
                color: #666666;
            }
        """
        )

        self.btn_stop.setEnabled(False)

        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_stop)
        layout.addLayout(btn_layout)

        # Output/Log display
        layout.addWidget(QLabel("📝 Scan Log:"))

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e1e;
                color: #b0b0b0;
                border: 1px solid #3c3c3c;
                font-family: 'Courier New';
                font-size: 11px;
            }
        """
        )
        layout.addWidget(self.log_display)

    def _connect_signals(self):
        """Connect widget signals."""
        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)

        self.scan_started.connect(self._on_scan_started)
        self.scan_finished.connect(self._on_scan_finished)
        self.scan_error.connect(self._on_scan_error)
        self.scan_data.connect(self._on_scan_data)

    def set_session(self, session: Session):
        """Set the session and populate device combos.

        Args:
            session: LabPilot Session with loaded devices
        """
        self.session = session
        self._refresh_devices()

    def _refresh_devices(self):
        """Refresh device combo boxes from session."""
        self.motor_combo.clear()
        self.detector_combo.clear()

        if not self.session:
            return

        for name, device in self.session.devices.items():
            # Check if device has appropriate protocols
            if hasattr(device, "set") and hasattr(device, "where"):
                # Movable-like device
                self.motor_combo.addItem(f"🎯 {name}", name)

            if hasattr(device, "read"):
                # Readable device
                self.detector_combo.addItem(f"📊 {name}", name)

    @pyqtSlot()
    def _on_run_clicked(self):
        """Handle run button click."""
        if not self.session:
            self.log("✗ No session loaded")
            return

        motor_name = self.motor_combo.currentData()
        detector_name = self.detector_combo.currentData()

        if not motor_name or not detector_name:
            self.log("✗ Please select motor and detector")
            return

        motor = self.session.devices.get(motor_name)
        detector = self.session.devices.get(detector_name)

        if not motor or not detector:
            self.log("✗ Selected devices not found")
            return

        # Create scan plan
        plan = ScanPlan(
            name="gui_scan",
            motor=motor_name,
            detector=detector_name,
            start=self.start_spin.value(),
            stop=self.stop_spin.value(),
            num=self.num_spin.value(),
        )

        self.log(f"▶️ Starting scan: {motor_name} → {detector_name}")
        self.log(f"   Range: {plan.start} to {plan.stop} ({plan.num} points)")

        async def run_scan():
            self.scan_started.emit()
            try:
                async for event in scan(plan, motor, detector, self.session.bus):
                    self.scan_data.emit(event.data)

                self.scan_finished.emit()
            except Exception as e:
                self.scan_error.emit(str(e))

        runner = AsyncRunner(run_scan())
        self.thread_pool.start(runner)

    @pyqtSlot()
    def _on_stop_clicked(self):
        """Handle stop button click."""
        self.log("⏹️ Stop requested")
        # TODO: Implement scan cancellation
        self.scan_running = False

    @pyqtSlot()
    def _on_scan_started(self):
        """Handle scan started."""
        self.scan_running = True
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)

    @pyqtSlot()
    def _on_scan_finished(self):
        """Handle scan finished."""
        self.scan_running = False
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("✅ Scan completed")

    @pyqtSlot(str)
    def _on_scan_error(self, error: str):
        """Handle scan error."""
        self.scan_running = False
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log(f"✗ Scan error: {error}")

    @pyqtSlot(dict)
    def _on_scan_data(self, data: dict):
        """Handle scan data event."""
        self.log(f"  📊 {data}")

    def log(self, message: str):
        """Append message to log display."""
        self.log_display.append(message)
