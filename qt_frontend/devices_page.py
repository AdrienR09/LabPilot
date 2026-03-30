#!/usr/bin/env python3
"""
Devices Page - Instrument Management Interface
Converts React devices page to Qt Material Design with card-based layout
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QScrollArea, QPushButton, QComboBox, QLineEdit,
    QGroupBox, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QMenu, QToolButton, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QIcon, QAction, QPixmap, QPainter, QColor
from typing import Dict, List, Optional
from dataclasses import dataclass
import json

# Import existing structures
from main import DashboardInstrument, InstrumentKind

class DeviceCard(QFrame):
    """Material Design device card with connection controls"""

    # Signals
    connect_requested = pyqtSignal(str)  # device_id
    disconnect_requested = pyqtSignal(str)  # device_id
    configure_requested = pyqtSignal(str)  # device_id
    launch_qt_requested = pyqtSignal(str)  # device_id
    remove_requested = pyqtSignal(str)  # device_id

    def __init__(self, device: DashboardInstrument):
        super().__init__()
        self.device = device
        self.setup_ui()

    def setup_ui(self):
        """Setup device card UI"""
        self.setObjectName("device_card")
        self.setFrameStyle(QFrame.Shape.Box)
        self.setMinimumHeight(200)
        self.setMaximumHeight(250)
        self.setMinimumWidth(300)

        # Set card styling based on connection status
        self.update_card_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with device info
        header_layout = QHBoxLayout()

        # Device icon and type
        icon_label = QLabel(self.get_device_icon())
        icon_label.setStyleSheet("font-size: 32px;")
        header_layout.addWidget(icon_label)

        # Device name and type
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        self.name_label = QLabel(self.device.name)
        self.name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        info_layout.addWidget(self.name_label)

        type_text = f"{self.device.adapter_type} • {self.device.dimensionality}"
        self.type_label = QLabel(type_text)
        self.type_label.setStyleSheet("font-size: 12px; color: #666;")
        info_layout.addWidget(self.type_label)

        header_layout.addLayout(info_layout)
        header_layout.addStretch()

        # Status indicator
        self.status_label = QLabel(self.device.status)
        self.status_label.setStyleSheet(self.get_status_style())
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # Device tags (if any)
        if self.device.tags:
            tags_layout = QHBoxLayout()
            tags_layout.setSpacing(4)

            for tag in self.device.tags[:3]:  # Show max 3 tags
                tag_label = QLabel(tag)
                tag_label.setStyleSheet("""
                    background-color: #e3f2fd;
                    color: #1976d2;
                    border-radius: 8px;
                    padding: 2px 8px;
                    font-size: 10px;
                    font-weight: bold;
                """)
                tags_layout.addWidget(tag_label)

            if len(self.device.tags) > 3:
                more_label = QLabel(f"+{len(self.device.tags) - 3}")
                more_label.setStyleSheet("font-size: 10px; color: #666;")
                tags_layout.addWidget(more_label)

            tags_layout.addStretch()
            layout.addLayout(tags_layout)

        # Connection status bar
        connection_layout = QHBoxLayout()

        self.connection_indicator = QLabel("●")
        self.connection_indicator.setStyleSheet(
            f"color: {'#4CAF50' if self.device.connected else '#f44336'}; font-size: 16px;"
        )
        connection_layout.addWidget(self.connection_indicator)

        connection_text = "Connected" if self.device.connected else "Disconnected"
        self.connection_label = QLabel(connection_text)
        self.connection_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        connection_layout.addWidget(self.connection_label)

        connection_layout.addStretch()
        layout.addLayout(connection_layout)

        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        # Connect/Disconnect button
        if self.device.connected:
            self.connect_btn = QPushButton("Disconnect")
            self.connect_btn.setObjectName("disconnect_button")
            self.connect_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.device.id))
        else:
            self.connect_btn = QPushButton("Connect")
            self.connect_btn.setObjectName("connect_button")
            self.connect_btn.clicked.connect(lambda: self.connect_requested.emit(self.device.id))

        buttons_layout.addWidget(self.connect_btn)

        # Qt Interface button (only when connected)
        if self.device.connected:
            qt_btn = QPushButton("Qt Interface")
            qt_btn.setObjectName("qt_interface_button")
            qt_btn.clicked.connect(lambda: self.launch_qt_requested.emit(self.device.id))
            buttons_layout.addWidget(qt_btn)

        # Menu button for additional actions
        menu_btn = QToolButton()
        menu_btn.setText("⋯")
        menu_btn.setStyleSheet("font-size: 16px; border: none; padding: 4px;")
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu = QMenu()
        configure_action = QAction("⚙️ Configure", self)
        configure_action.triggered.connect(lambda: self.configure_requested.emit(self.device.id))
        menu.addAction(configure_action)

        menu.addSeparator()

        remove_action = QAction("🗑️ Remove", self)
        remove_action.triggered.connect(lambda: self.remove_requested.emit(self.device.id))
        menu.addAction(remove_action)

        menu_btn.setMenu(menu)
        buttons_layout.addWidget(menu_btn)

        layout.addLayout(buttons_layout)

        layout.addStretch()

    def get_device_icon(self) -> str:
        """Get appropriate icon for device type"""
        if self.device.kind == InstrumentKind.DETECTOR.value:
            if self.device.dimensionality == "0D":
                return "📡"  # Point detector
            elif self.device.dimensionality == "1D":
                return "📊"  # Line detector
            elif self.device.dimensionality == "2D":
                return "📷"  # Camera
            else:
                return "🔬"  # General detector
        elif self.device.kind == InstrumentKind.MOTOR.value:
            return "🔧"  # Motor/actuator
        else:
            return "⚙️"  # Generic instrument

    def get_status_style(self) -> str:
        """Get status label styling"""
        status_colors = {
            "Ready": "#4CAF50",
            "Busy": "#FF9800",
            "Error": "#f44336",
            "Unknown": "#9E9E9E"
        }
        color = status_colors.get(self.device.status, "#9E9E9E")
        return f"""
            background-color: {color};
            color: white;
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 10px;
            font-weight: bold;
        """

    def update_card_style(self):
        """Update card styling based on connection status"""
        if self.device.connected:
            border_color = "#4CAF50"
            bg_color = "#ffffff"
        else:
            border_color = "#e0e0e0"
            bg_color = "#fafafa"

        self.setStyleSheet(f"""
            #device_card {{
                border: 2px solid {border_color};
                border-radius: 12px;
                background-color: {bg_color};
            }}
            #device_card:hover {{
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
            #connect_button {{
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            #connect_button:hover {{
                background-color: #45a049;
            }}
            #disconnect_button {{
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            #disconnect_button:hover {{
                background-color: #da190b;
            }}
            #qt_interface_button {{
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            #qt_interface_button:hover {{
                background-color: #1976D2;
            }}
        """)

    def update_device(self, device: DashboardInstrument):
        """Update card with new device data"""
        self.device = device
        self.name_label.setText(device.name)
        self.type_label.setText(f"{device.adapter_type} • {device.dimensionality}")
        self.status_label.setText(device.status)
        self.status_label.setStyleSheet(self.get_status_style())

        # Update connection indicator
        self.connection_indicator.setStyleSheet(
            f"color: {'#4CAF50' if device.connected else '#f44336'}; font-size: 16px;"
        )
        self.connection_label.setText("Connected" if device.connected else "Disconnected")

        # Update connect button
        if device.connected:
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setObjectName("disconnect_button")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(lambda: self.disconnect_requested.emit(self.device.id))
        else:
            self.connect_btn.setText("Connect")
            self.connect_btn.setObjectName("connect_button")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(lambda: self.connect_requested.emit(self.device.id))

        self.update_card_style()

class AddDeviceDialog(QDialog):
    """Dialog for adding new devices"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Device")
        self.setModal(True)
        self.resize(400, 300)
        self.setup_ui()

    def setup_ui(self):
        """Setup add device dialog UI"""
        layout = QVBoxLayout(self)

        # Form layout
        form_layout = QFormLayout()

        # Device name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter device name...")
        form_layout.addRow("Name:", self.name_edit)

        # Device type
        self.type_combo = QComboBox()
        self.type_combo.addItems(["detector", "motor"])
        form_layout.addRow("Type:", self.type_combo)

        # Dimensionality (for detectors)
        self.dim_combo = QComboBox()
        self.dim_combo.addItems(["0D", "1D", "2D", "3D"])
        form_layout.addRow("Dimensionality:", self.dim_combo)

        # Adapter type
        self.adapter_edit = QLineEdit()
        self.adapter_edit.setPlaceholderText("e.g., MockDetector, SerialMotor...")
        form_layout.addRow("Adapter:", self.adapter_edit)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_device_data(self) -> dict:
        """Get device data from form"""
        return {
            "name": self.name_edit.text(),
            "adapter_type": self.adapter_edit.text(),
            "kind": self.type_combo.currentText(),
            "dimensionality": self.dim_combo.currentText(),
            "connected": False,
            "status": "Ready",
            "tags": [],
            "data": None
        }

class DevicesPage(QWidget):
    """Devices page implementation with card-based instrument management"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None
        self.devices: List[DashboardInstrument] = []
        self.device_cards: Dict[str, DeviceCard] = {}
        self.dark_mode = False
        self.setup_ui()
        self.load_mock_devices()

    def setup_ui(self):
        """Setup devices page UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("Devices")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #333;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Filter dropdown
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Devices", "Detectors", "Motors", "Connected", "Disconnected"])
        self.filter_combo.currentTextChanged.connect(self.filter_devices)
        header_layout.addWidget(self.filter_combo)

        # Add device button
        add_btn = QPushButton("+ Add Device")
        add_btn.setObjectName("add_device_button")
        add_btn.clicked.connect(self.show_add_device_dialog)
        add_btn.setStyleSheet("""
            #add_device_button {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            #add_device_button:hover {
                background-color: #45a049;
            }
        """)
        header_layout.addWidget(add_btn)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Devices grid (scrollable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.devices_widget = QWidget()
        self.devices_layout = QGridLayout(self.devices_widget)
        self.devices_layout.setSpacing(20)

        scroll_area.setWidget(self.devices_widget)
        layout.addWidget(scroll_area)

        # Load initial data
        self.load_mock_devices()

    def set_api_client(self, client):
        """Set API client for backend communication"""
        self.api_client = client

    def load_mock_devices(self):
        """Load mock devices for development"""
        mock_devices = [
            DashboardInstrument(
                id="mock_detector_1",
                name="Main Spectrometer",
                adapter_type="MockSpectrometer",
                kind="detector",
                dimensionality="1D",
                connected=True,
                status="Ready",
                tags=["Spectroscopy", "UV-Vis"]
            ),
            DashboardInstrument(
                id="mock_camera_1",
                name="CCD Camera",
                adapter_type="MockCamera",
                kind="detector",
                dimensionality="2D",
                connected=False,
                status="Disconnected",
                tags=["Imaging", "CCD"]
            ),
            DashboardInstrument(
                id="mock_motor_1",
                name="Sample X-Stage",
                adapter_type="MockMotor",
                kind="motor",
                dimensionality="1D",
                connected=True,
                status="Ready",
                tags=["Positioning", "Linear"]
            ),
            DashboardInstrument(
                id="mock_photodiode",
                name="Reference Photodiode",
                adapter_type="MockPhotodiode",
                kind="detector",
                dimensionality="0D",
                connected=True,
                status="Ready",
                tags=["Point-Detector", "Reference"]
            )
        ]

        self.devices = mock_devices
        self.update_device_cards()

    def update_device_cards(self):
        """Update device cards display"""
        # Clear existing cards
        for card_id, card in self.device_cards.items():
            self.devices_layout.removeWidget(card)
            card.deleteLater()
        self.device_cards.clear()

        # Create new cards
        for i, device in enumerate(self.devices):
            card = DeviceCard(device)

            # Connect signals
            card.connect_requested.connect(self.connect_device)
            card.disconnect_requested.connect(self.disconnect_device)
            card.configure_requested.connect(self.configure_device)
            card.launch_qt_requested.connect(self.launch_qt_interface)
            card.remove_requested.connect(self.remove_device)

            # Add to grid (3 columns)
            row = i // 3
            col = i % 3
            self.devices_layout.addWidget(card, row, col)

            self.device_cards[device.id] = card

        # Add spacer items to fill remaining grid spaces
        total_rows = (len(self.devices) + 2) // 3
        for col in range(3):
            spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
            self.devices_layout.addItem(spacer, total_rows, col)

    def filter_devices(self, filter_text: str):
        """Filter devices based on selected criteria"""
        for device_id, card in self.device_cards.items():
            show_card = True

            if filter_text == "Detectors" and card.device.kind != "detector":
                show_card = False
            elif filter_text == "Motors" and card.device.kind != "motor":
                show_card = False
            elif filter_text == "Connected" and not card.device.connected:
                show_card = False
            elif filter_text == "Disconnected" and card.device.connected:
                show_card = False

            card.setVisible(show_card)

    def show_add_device_dialog(self):
        """Show add device dialog"""
        dialog = AddDeviceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            device_data = dialog.get_device_data()
            if device_data["name"] and device_data["adapter_type"]:
                self.add_device(device_data)

    def add_device(self, device_data: dict):
        """Add new device"""
        # Generate unique ID
        device_id = f"device_{len(self.devices) + 1}"
        device_data["id"] = device_id

        new_device = DashboardInstrument(**device_data)
        self.devices.append(new_device)
        self.update_device_cards()

    def refresh_data(self):
        """Refresh device data from backend"""
        if self.api_client:
            # TODO: Implement API call to refresh devices
            pass
        else:
            self.load_mock_devices()

    def set_theme(self, dark_mode: bool):
        """Update theme for devices page"""
        self.dark_mode = dark_mode
        # Re-apply styling if needed

    # Device action handlers
    def connect_device(self, device_id: str):
        """Connect device"""
        device = next((d for d in self.devices if d.id == device_id), None)
        if device:
            device.connected = True
            device.status = "Ready"
            self.device_cards[device_id].update_device(device)

    def disconnect_device(self, device_id: str):
        """Disconnect device"""
        device = next((d for d in self.devices if d.id == device_id), None)
        if device:
            device.connected = False
            device.status = "Disconnected"
            self.device_cards[device_id].update_device(device)

    def configure_device(self, device_id: str):
        """Configure device settings"""
        QMessageBox.information(self, "Configure Device", f"Configure device {device_id}")

    def launch_qt_interface(self, device_id: str):
        """Launch Qt interface for device"""
        device = next((d for d in self.devices if d.id == device_id), None)
        if device and device.connected:
            try:
                from .instrument_windows import create_instrument_window
                window = create_instrument_window(device)
                window.show()
                print(f"Launched UI for: {device.name}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not launch UI: {str(e)}")
        else:
            QMessageBox.warning(self, "Not Connected", f"Device is not connected")

    def remove_device(self, device_id: str):
        """Remove device after confirmation"""
        reply = QMessageBox.question(
            self, "Remove Device",
            f"Are you sure you want to remove device {device_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.devices = [d for d in self.devices if d.id != device_id]
            self.update_device_cards()