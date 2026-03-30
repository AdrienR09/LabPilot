"""Instruments tab for device management.

Enhanced to load and display all devices from labpilot_instruments package.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from PyQt6.QtCore import QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from labpilot_core import Session

# Device catalog organized by category
CATEGORY_MAP = {
    'camera': ['AlliedVision', 'Andor', 'Basler', 'BitFlow', 'DCAM', 'IMAQ',
               'IMAQdx', 'Mightex', 'Photometrics', 'PhotonFocus',
               'PrincetonInstruments', 'SiliconSoftware', 'uc480'],
    'motion': ['Arcus', 'Attocube', 'Newport', 'PhysikInstrumente', 'SmarAct',
               'Standa', 'Thorlabs', 'Trinamic'],
    'laser': ['Hubner', 'LaserQuantum', 'LighthousePhotonics', 'M2', 'Sirah',
              'Toptica'],
    'test_equipment': ['AWG', 'Agilent', 'Keithley', 'Rigol', 'Tektronix'],
    'vacuum': ['Cryomagnetics', 'KJL', 'Leybold', 'Pfeiffer'],
    'temperature': ['Cryocon', 'Lakeshore'],
    'optical': ['HighFinesse', 'NKT', 'OZOptics', 'Ophir'],
    'power': ['Conrad', 'ElektroAutomatik', 'Omron', 'Voltcraft'],
    'controller': ['Arduino', 'Lumel', 'Modbus', 'NI'],
}

CATEGORY_ICONS = {
    'camera': '🎥',
    'motion': '🔧',
    'laser': '🔬',
    'test_equipment': '📊',
    'optical': '🔌',
    'vacuum': '🌀',
    'temperature': '🌡️',
    'power': '⚡',
    'controller': '🎛️',
}


class AsyncRunner(QRunnable):
    """Helper to run async code in Qt thread pool."""

    def __init__(self, coro, callback=None):
        super().__init__()
        self.coro = coro
        self.callback = callback

    def run(self):
        """Execute async coroutine."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self.coro)
            if self.callback:
                self.callback(result)
        finally:
            loop.close()


class InstrumentsTab(QWidget):
    """Tab for viewing and managing instruments.

    Enhanced to show all 99 devices from labpilot_instruments package
    organized by category and manufacturer.
    """

    # Signals
    device_loaded = pyqtSignal(str)  # Device name
    device_connected = pyqtSignal(str)  # Device name
    device_disconnected = pyqtSignal(str)  # Device name
    error_occurred = pyqtSignal(str)  # Error message
    log_message = pyqtSignal(str)  # Log message

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.session: Session | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self.loaded_devices: dict[str, Any] = {}  # device_id -> device instance
        self.current_device = None
        self.current_device_id = None

        self._setup_ui()
        self._connect_signals()
        self._load_device_catalog()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QHBoxLayout(self)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left panel: Device tree
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel: Device controls and info
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes
        splitter.setSizes([400, 800])

    def _create_left_panel(self) -> QWidget:
        """Create left panel with device tree."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Title
        title = QLabel("📁 Available Instruments")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; padding: 5px;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("99 devices | 50 manufacturers | 9 categories")
        subtitle.setStyleSheet("color: #888888; padding: 0 5px 5px 5px; font-size: 10px;")
        layout.addWidget(subtitle)

        # Device tree
        self.device_tree = QTreeWidget()
        self.device_tree.setHeaderLabel("Category > Manufacturer > Device")
        self.device_tree.itemClicked.connect(self._on_device_selected)
        self.device_tree.setStyleSheet(
            """
            QTreeWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                font-size: 11pt;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #4a9eff;
            }
            """
        )
        layout.addWidget(self.device_tree)

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create right panel with controls and info."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Device info group
        info_group = QGroupBox("Device Information")
        info_layout = QVBoxLayout(info_group)

        self.device_name_label = QLabel("Select a device from the tree")
        self.device_name_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.device_name_label.setStyleSheet("color: #ffffff;")
        info_layout.addWidget(self.device_name_label)

        self.device_path_label = QLabel("")
        self.device_path_label.setStyleSheet("color: #888888;")
        info_layout.addWidget(self.device_path_label)

        self.device_doc = QTextEdit()
        self.device_doc.setReadOnly(True)
        self.device_doc.setMaximumHeight(150)
        self.device_doc.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e1e;
                color: #b0b0b0;
                border: 1px solid #3c3c3c;
                font-size: 10pt;
            }
            """
        )
        info_layout.addWidget(self.device_doc)

        layout.addWidget(info_group)

        # Connection controls group
        control_group = QGroupBox("Connection Controls")
        control_layout = QVBoxLayout(control_group)

        # Connection string input
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Connection:"))
        self.connection_input = QLineEdit()
        self.connection_input.setPlaceholderText("e.g., COM3, /dev/ttyUSB0, USB0::0x1234::0x5678::INSTR")
        self.connection_input.setStyleSheet(
            """
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                padding: 5px;
            }
            """
        )
        conn_layout.addWidget(self.connection_input)
        control_layout.addLayout(conn_layout)

        # Control buttons
        button_layout = QHBoxLayout()

        self.btn_load = QPushButton("📥 Load Device")
        self.btn_load.clicked.connect(self._on_load_clicked)
        self.btn_load.setEnabled(False)
        button_layout.addWidget(self.btn_load)

        self.btn_connect = QPushButton("🔌 Connect")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_connect.setEnabled(False)
        button_layout.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("🔌 Disconnect")
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_disconnect.setEnabled(False)
        button_layout.addWidget(self.btn_disconnect)

        self.btn_info = QPushButton("ℹ️ Get Info")
        self.btn_info.clicked.connect(self._on_info_clicked)
        self.btn_info.setEnabled(False)
        button_layout.addWidget(self.btn_info)

        for btn in [self.btn_load, self.btn_connect, self.btn_disconnect, self.btn_info]:
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: none;
                    padding: 8px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #4a9eff;
                }
                QPushButton:disabled {
                    background-color: #2b2b2b;
                    color: #666666;
                }
                """
            )

        control_layout.addLayout(button_layout)
        layout.addWidget(control_group)

        # Console output
        console_group = QGroupBox("Console Output")
        console_layout = QVBoxLayout(console_group)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e1e;
                color: #b0b0b0;
                border: 1px solid #3c3c3c;
                font-family: 'Courier New';
                font-size: 10pt;
            }
            """
        )
        console_layout.addWidget(self.console)

        clear_btn = QPushButton("🗑️ Clear Console")
        clear_btn.clicked.connect(self.console.clear)
        clear_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #3c3c3c;
                color: #ffffff;
                border: none;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4a9eff;
            }
            """
        )
        console_layout.addWidget(clear_btn)

        layout.addWidget(console_group)

        # Group box styling
        for group in [info_group, control_group, console_group]:
            group.setStyleSheet(
                """
                QGroupBox {
                    color: #ffffff;
                    border: 1px solid #3c3c3c;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 10px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QLabel {
                    color: #ffffff;
                }
                """
            )

        return panel

    def _connect_signals(self):
        """Connect widget signals."""
        self.log_message.connect(self._log)

    def _load_device_catalog(self):
        """Load all devices from labpilot_instruments into the tree."""
        self.device_tree.clear()
        self._log("Loading device catalog from labpilot_instruments...")

        total_devices = 0

        for category, manufacturers in sorted(CATEGORY_MAP.items()):
            # Category item
            icon = CATEGORY_ICONS.get(category, '📦')
            cat_item = QTreeWidgetItem([f"{icon} {category.replace('_', ' ').title()}"])
            cat_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'category', 'name': category})
            self.device_tree.addTopLevelItem(cat_item)

            for mfr in sorted(manufacturers):
                # Try to import manufacturer module
                try:
                    mfr_lower = mfr.lower()
                    mod = importlib.import_module(f'labpilot_instruments.{category}.{mfr_lower}')

                    # Get all device classes
                    devices = [name for name in dir(mod)
                              if not name.startswith('_')
                              and name.endswith('Wrapper')]

                    if devices:
                        # Manufacturer item
                        mfr_item = QTreeWidgetItem([f"📦 {mfr} ({len(devices)} devices)"])
                        mfr_item.setData(0, Qt.ItemDataRole.UserRole, {
                            'type': 'manufacturer',
                            'name': mfr,
                            'category': category
                        })
                        cat_item.addChild(mfr_item)

                        # Device items
                        for device in sorted(devices):
                            device_name = device.replace('Wrapper', '')
                            dev_item = QTreeWidgetItem([f"🔌 {device_name}"])
                            dev_item.setData(0, Qt.ItemDataRole.UserRole, {
                                'type': 'device',
                                'name': device_name,
                                'wrapper_name': device,
                                'manufacturer': mfr,
                                'category': category,
                                'module_path': f'labpilot_instruments.{category}.{mfr_lower}'
                            })
                            mfr_item.addChild(dev_item)
                            total_devices += 1

                except Exception as e:
                    self._log(f"Warning: Could not load {category}.{mfr}: {e}")

        self.device_tree.expandAll()
        self._log(f"✓ Loaded {total_devices} devices from labpilot_instruments")

    @pyqtSlot(QTreeWidgetItem, int)
    def _on_device_selected(self, item: QTreeWidgetItem, column: int):
        """Handle device selection in tree."""
        data = item.data(0, Qt.ItemDataRole.UserRole)

        if data and data.get('type') == 'device':
            self.current_device_data = data

            # Update labels
            device_name = data['name']
            category = data['category']
            manufacturer = data['manufacturer']
            module_path = data['module_path']

            self.device_name_label.setText(f"{device_name}")
            self.device_path_label.setText(f"{category}.{manufacturer.lower()}.{device_name}")

            # Try to get docstring
            try:
                mod = importlib.import_module(module_path)
                wrapper_class = getattr(mod, data['wrapper_name'])
                doc = wrapper_class.__doc__ or "No documentation available."
                self.device_doc.setPlainText(doc)
            except Exception as e:
                self.device_doc.setPlainText(f"Could not load documentation: {e}")

            self.btn_load.setEnabled(True)
            self._log(f"Selected: {category}.{manufacturer}.{device_name}")

    @pyqtSlot()
    def _on_load_clicked(self):
        """Load the selected device."""
        if not hasattr(self, 'current_device_data'):
            return

        data = self.current_device_data
        device_name = data['name']
        device_id = f"{data['category']}.{data['manufacturer'].lower()}.{device_name}"

        try:
            # Import and instantiate device
            mod = importlib.import_module(data['module_path'])
            device_class = getattr(mod, data['wrapper_name'])

            device_instance = device_class()
            self.loaded_devices[device_id] = device_instance

            self.current_device = device_instance
            self.current_device_id = device_id

            self._log(f"✓ Loaded {device_name}")
            self._log(f"  Device ID: {device_id}")
            self._log(f"  Wrapper: {device_class.__name__}")
            self._log(f"  PyLabLib class: {device_instance.device_class.__name__}")

            self.btn_connect.setEnabled(True)
            self.btn_info.setEnabled(True)

        except Exception as e:
            self._log(f"✗ Failed to load {device_name}: {e}")
            QMessageBox.warning(self, "Load Error", f"Failed to load device:\n{e}")

    @pyqtSlot()
    def _on_connect_clicked(self):
        """Connect to the loaded device."""
        if not self.current_device:
            return

        connection_str = self.connection_input.text()

        try:
            self._log(f"Connecting{' with: ' + connection_str if connection_str else ''}...")

            if connection_str:
                success = self.current_device.connect(connection_str)
            else:
                success = self.current_device.connect()

            if success:
                self._log("✓ Connected successfully!")
                self._log(f"  Status: {self.current_device.is_connected}")
                self.btn_connect.setEnabled(False)
                self.btn_disconnect.setEnabled(True)
                self.device_connected.emit(self.current_device_id)
            else:
                self._log("✗ Connection failed")
                QMessageBox.warning(self, "Connection Error", "Failed to connect to device")

        except Exception as e:
            self._log(f"✗ Connection error: {e}")
            QMessageBox.critical(self, "Connection Error", f"Error connecting:\n{e}")

    @pyqtSlot()
    def _on_disconnect_clicked(self):
        """Disconnect from the device."""
        if not self.current_device:
            return

        try:
            self._log("Disconnecting...")
            success = self.current_device.disconnect()

            if success:
                self._log("✓ Disconnected successfully")
                self.btn_connect.setEnabled(True)
                self.btn_disconnect.setEnabled(False)
                self.device_disconnected.emit(self.current_device_id)
            else:
                self._log("✗ Disconnection failed")

        except Exception as e:
            self._log(f"✗ Disconnection error: {e}")
            QMessageBox.critical(self, "Disconnection Error", f"Error disconnecting:\n{e}")

    @pyqtSlot()
    def _on_info_clicked(self):
        """Get information about the device."""
        if not self.current_device:
            return

        try:
            self._log("Getting device info...")
            info = self.current_device.get_info()

            self._log("Device Information:")
            for key, value in info.items():
                self._log(f"  {key}: {value}")

        except Exception as e:
            self._log(f"✗ Error getting info: {e}")
            QMessageBox.warning(self, "Info Error", f"Error getting device info:\n{e}")

    def _log(self, message: str):
        """Log message to console."""
        self.console.append(message)

    def set_session(self, session: Session):
        """Set the session (kept for compatibility).

        Args:
            session: LabPilot Session
        """
        self.session = session
        self._log(f"Session set with {len(session.devices)} devices")
