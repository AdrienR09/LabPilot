"""
Simple Instrument Management Dialogs

Provides basic instrument selection and configuration without external dependencies.
"""

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QGroupBox,
    QDialogButtonBox, QMessageBox
)


class InstrumentCatalog:
    """Simple instrument catalog for testing and development."""

    CATEGORIES = {
        "Cameras": {
            "description": "Imaging devices and cameras",
            "icon": "📷",
            "instruments": {
                "Thorlabs DCU224C": {
                    "adapter": "ThorlabsDCU224C",
                    "type": "Camera",
                    "manufacturer": "Thorlabs",
                    "module": "test.camera"
                },
                "Test Camera": {
                    "adapter": "TestCamera",
                    "type": "Camera",
                    "manufacturer": "Virtual",
                    "module": "test.camera"
                },
            }
        },
        "Spectrometers": {
            "description": "Optical spectrometers",
            "icon": "🌈",
            "instruments": {
                "Ocean Optics USB2000": {
                    "adapter": "OceanOpticsUSB2000",
                    "type": "Spectrometer",
                    "manufacturer": "Ocean Optics",
                    "module": "test.spectrometer"
                },
                "Test Spectrometer": {
                    "adapter": "TestSpectrometer",
                    "type": "Spectrometer",
                    "manufacturer": "Virtual",
                    "module": "test.spectrometer"
                },
            }
        },
        "Lasers": {
            "description": "Laser sources",
            "icon": "🔴",
            "instruments": {
                "Thorlabs CLD1015": {
                    "adapter": "ThorlabsCLD1015",
                    "type": "Laser",
                    "manufacturer": "Thorlabs",
                    "module": "test.laser"
                },
                "Test Tunable Laser": {
                    "adapter": "TestTunableLaser",
                    "type": "Laser",
                    "manufacturer": "Virtual",
                    "module": "test.laser"
                },
            }
        },
        "Motion Stages": {
            "description": "Motorized translation and rotation stages",
            "icon": "🎯",
            "instruments": {
                "Thorlabs K10CR1": {
                    "adapter": "ThorlabsK10CR1",
                    "type": "Motor",
                    "manufacturer": "Thorlabs",
                    "module": "test.motor"
                },
                "Test XY Scanner": {
                    "adapter": "TestXYScanner",
                    "type": "Motor",
                    "manufacturer": "Virtual",
                    "module": "test.motor"
                },
            }
        },
        "Power Meters": {
            "description": "Optical and electrical power meters",
            "icon": "⚡",
            "instruments": {
                "Thorlabs PM100D": {
                    "adapter": "ThorlabsPM100D",
                    "type": "PowerMeter",
                    "manufacturer": "Thorlabs",
                    "module": "test.powermeter"
                },
                "Test Power Meter": {
                    "adapter": "TestPowerMeter",
                    "type": "PowerMeter",
                    "manufacturer": "Virtual",
                    "module": "test.powermeter"
                },
            }
        }
    }


class SimpleAddInstrumentDialog(QDialog):
    """Simple dialog for adding instruments without external dependencies."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Instrument")
        self.setModal(True)
        self.setMinimumWidth(500)

        self.selected_config = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("➕ Add Instrument")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #4a9eff; padding: 10px;")
        layout.addWidget(header)

        # Category selection
        cat_group = QGroupBox("1. Select Category")
        cat_layout = QFormLayout(cat_group)

        self.category_combo = QComboBox()
        self.category_combo.addItem("-- Select Category --", None)
        for cat_name, cat_info in InstrumentCatalog.CATEGORIES.items():
            icon = cat_info.get('icon', '🔧')
            desc = cat_info.get('description', '')
            display_text = f"{icon} {cat_name} - {desc}"
            self.category_combo.addItem(display_text, cat_name)
        cat_layout.addRow("Category:", self.category_combo)
        layout.addWidget(cat_group)

        # Instrument selection
        inst_group = QGroupBox("2. Select Instrument")
        inst_layout = QFormLayout(inst_group)

        self.instrument_combo = QComboBox()
        self.instrument_combo.setEnabled(False)
        inst_layout.addRow("Instrument:", self.instrument_combo)
        layout.addWidget(inst_group)

        # Configuration
        config_group = QGroupBox("3. Configuration")
        config_layout = QFormLayout(config_group)

        self.instance_name_edit = QLineEdit()
        self.instance_name_edit.setPlaceholderText("e.g., camera_1, laser_main")
        config_layout.addRow("Instance Name:", self.instance_name_edit)

        self.connection_edit = QLineEdit()
        self.connection_edit.setPlaceholderText("e.g., COM3, USB::0x1234::0x5678, 192.168.1.100")
        config_layout.addRow("Connection:", self.connection_edit)

        layout.addWidget(config_group)

        # Info display
        self.info_display = QTextEdit()
        self.info_display.setMaximumHeight(100)
        self.info_display.setPlaceholderText("Select an instrument to see details...")
        self.info_display.setStyleSheet("""
            QTextEdit {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        layout.addWidget(self.info_display)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Styling
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                padding-top: 15px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QComboBox, QLineEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QComboBox:focus, QLineEdit:focus {
                border-color: #4a9eff;
            }
        """)

    def _connect_signals(self):
        """Connect UI signals."""
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        self.instrument_combo.currentTextChanged.connect(self._on_instrument_changed)

    def _on_category_changed(self):
        """Handle category selection change."""
        category_data = self.category_combo.currentData()

        self.instrument_combo.clear()
        self.instrument_combo.setEnabled(False)
        self.info_display.clear()

        if category_data:
            category_info = InstrumentCatalog.CATEGORIES[category_data]
            instruments = category_info.get('instruments', {})

            self.instrument_combo.addItem("-- Select Instrument --", None)
            for inst_name, inst_info in instruments.items():
                manufacturer = inst_info.get('manufacturer', 'Unknown')
                inst_type = inst_info.get('type', 'Device')
                display_text = f"{inst_name} ({manufacturer} {inst_type})"
                self.instrument_combo.addItem(display_text, (inst_name, inst_info))

            self.instrument_combo.setEnabled(True)

    def _on_instrument_changed(self):
        """Handle instrument selection change."""
        instrument_data = self.instrument_combo.currentData()

        if instrument_data:
            inst_name, inst_info = instrument_data

            # Auto-fill instance name
            safe_name = inst_name.lower().replace(' ', '_').replace('-', '_')
            count = 1
            base_name = safe_name
            # Simple counter for unique names (in a real implementation, check existing instruments)
            self.instance_name_edit.setText(f"{base_name}_{count}")

            # Show instrument info
            info_text = f"Instrument: {inst_name}\n"
            info_text += f"Manufacturer: {inst_info.get('manufacturer', 'Unknown')}\n"
            info_text += f"Type: {inst_info.get('type', 'Device')}\n"
            info_text += f"Adapter: {inst_info.get('adapter', 'Unknown')}\n"
            info_text += f"Module: {inst_info.get('module', 'Unknown')}"

            self.info_display.setPlainText(info_text)

    def accept(self):
        """Handle dialog acceptance."""
        # Validate inputs
        if not self.category_combo.currentData():
            QMessageBox.warning(self, "Validation Error", "Please select a category.")
            return

        if not self.instrument_combo.currentData():
            QMessageBox.warning(self, "Validation Error", "Please select an instrument.")
            return

        instance_name = self.instance_name_edit.text().strip()
        if not instance_name:
            QMessageBox.warning(self, "Validation Error", "Please enter an instance name.")
            return

        # Build configuration
        _, inst_info = self.instrument_combo.currentData()

        self.selected_config = {
            'instance_name': instance_name,
            'device_data': {
                'module_path': inst_info.get('module', 'test.device'),
                'wrapper_name': inst_info.get('adapter', 'TestDevice'),
                'category': self.category_combo.currentData(),
                'manufacturer': inst_info.get('manufacturer', 'Unknown'),
                'name': inst_info.get('adapter', 'TestDevice')
            },
            'settings': {
                'connection': self.connection_edit.text().strip()
            }
        }

        super().accept()

    def get_instrument_config(self) -> dict[str, Any] | None:
        """Get the configured instrument settings."""
        return self.selected_config


# Stub for interface dialog (not implemented yet)
class SimpleAddInterfaceDialog(QDialog):
    """Stub for interface dialog."""

    def __init__(self, instruments, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Interface")

        layout = QVBoxLayout(self)

        label = QLabel("Interface management is not yet implemented.\nThis feature will be available in a future update.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #666; font-size: 12px; padding: 20px;")
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.reject)  # Just close without adding
        layout.addWidget(buttons)

    def get_interface_config(self):
        return None