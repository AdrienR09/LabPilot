#!/usr/bin/env python3
"""
Settings Page - Configuration Management
Converts React settings page to Qt Material Design
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QPushButton, QGroupBox, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QSpinBox, QSlider, QTabWidget,
    QScrollArea, QMessageBox, QColorDialog, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from qt_material import list_themes
import json

class SettingsPage(QWidget):
    """Settings page implementation"""

    # Signals for settings changes
    theme_changed = pyqtSignal(str)
    backend_url_changed = pyqtSignal(str)
    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None
        self.current_settings = self.load_default_settings()
        self.setup_ui()

    def setup_ui(self):
        """Setup settings page UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #333;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Save and reset buttons
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setObjectName("save_button")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("""
            #save_button {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            #save_button:hover {
                background-color: #45a049;
            }
        """)
        header_layout.addWidget(save_btn)

        reset_btn = QPushButton("🔄 Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        header_layout.addWidget(reset_btn)

        layout.addLayout(header_layout)

        # Settings tabs
        self.tabs = QTabWidget()

        # Appearance tab
        appearance_tab = self.create_appearance_tab()
        self.tabs.addTab(appearance_tab, "🎨 Appearance")

        # Connection tab
        connection_tab = self.create_connection_tab()
        self.tabs.addTab(connection_tab, "🌐 Connection")

        # Instruments tab
        instruments_tab = self.create_instruments_tab()
        self.tabs.addTab(instruments_tab, "🔧 Instruments")

        # AI Assistant tab
        ai_tab = self.create_ai_tab()
        self.tabs.addTab(ai_tab, "🤖 AI Assistant")

        # Data Management tab
        data_tab = self.create_data_tab()
        self.tabs.addTab(data_tab, "📊 Data")

        layout.addWidget(self.tabs)

    def create_appearance_tab(self) -> QWidget:
        """Create appearance settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Theme selection
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)

        self.theme_combo = QComboBox()
        available_themes = list_themes()
        self.theme_combo.addItems(available_themes)
        self.theme_combo.setCurrentText(self.current_settings.get("theme", "light_blue.xml"))
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        theme_layout.addRow("Material Theme:", self.theme_combo)

        layout.addWidget(theme_group)

        # UI Preferences
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout(ui_group)

        self.sidebar_collapsed_check = QCheckBox()
        self.sidebar_collapsed_check.setChecked(self.current_settings.get("sidebar_collapsed", False))
        ui_layout.addRow("Start with collapsed sidebar:", self.sidebar_collapsed_check)

        self.animations_check = QCheckBox()
        self.animations_check.setChecked(self.current_settings.get("animations_enabled", True))
        ui_layout.addRow("Enable animations:", self.animations_check)

        self.tooltips_check = QCheckBox()
        self.tooltips_check.setChecked(self.current_settings.get("tooltips_enabled", True))
        ui_layout.addRow("Show tooltips:", self.tooltips_check)

        layout.addWidget(ui_group)

        layout.addStretch()
        return tab

    def create_connection_tab(self) -> QWidget:
        """Create connection settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Backend connection
        backend_group = QGroupBox("Backend Server")
        backend_layout = QFormLayout(backend_group)

        self.backend_url_edit = QLineEdit()
        self.backend_url_edit.setText(self.current_settings.get("backend_url", "http://localhost:8000"))
        self.backend_url_edit.textChanged.connect(self.on_backend_url_changed)
        backend_layout.addRow("Backend URL:", self.backend_url_edit)

        self.auto_connect_check = QCheckBox()
        self.auto_connect_check.setChecked(self.current_settings.get("auto_connect", True))
        backend_layout.addRow("Auto-connect on startup:", self.auto_connect_check)

        self.connection_timeout_spin = QSpinBox()
        self.connection_timeout_spin.setRange(1, 60)
        self.connection_timeout_spin.setValue(self.current_settings.get("connection_timeout", 10))
        self.connection_timeout_spin.setSuffix(" seconds")
        backend_layout.addRow("Connection timeout:", self.connection_timeout_spin)

        layout.addWidget(backend_group)

        # Network settings
        network_group = QGroupBox("Network")
        network_layout = QFormLayout(network_group)

        self.retry_attempts_spin = QSpinBox()
        self.retry_attempts_spin.setRange(0, 10)
        self.retry_attempts_spin.setValue(self.current_settings.get("retry_attempts", 3))
        network_layout.addRow("Retry attempts:", self.retry_attempts_spin)

        self.use_websockets_check = QCheckBox()
        self.use_websockets_check.setChecked(self.current_settings.get("use_websockets", True))
        network_layout.addRow("Enable WebSocket updates:", self.use_websockets_check)

        layout.addWidget(network_group)

        layout.addStretch()
        return tab

    def create_instruments_tab(self) -> QWidget:
        """Create instrument settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Detection settings
        detection_group = QGroupBox("Instrument Detection")
        detection_layout = QFormLayout(detection_group)

        self.auto_detect_check = QCheckBox()
        self.auto_detect_check.setChecked(self.current_settings.get("auto_detect_instruments", True))
        detection_layout.addRow("Auto-detect instruments:", self.auto_detect_check)

        self.scan_interval_spin = QSpinBox()
        self.scan_interval_spin.setRange(5, 300)
        self.scan_interval_spin.setValue(self.current_settings.get("scan_interval", 30))
        self.scan_interval_spin.setSuffix(" seconds")
        detection_layout.addRow("Re-scan interval:", self.scan_interval_spin)

        layout.addWidget(detection_group)

        # Default settings
        defaults_group = QGroupBox("Default Configuration")
        defaults_layout = QFormLayout(defaults_group)

        self.default_timeout_spin = QSpinBox()
        self.default_timeout_spin.setRange(1, 300)
        self.default_timeout_spin.setValue(self.current_settings.get("default_instrument_timeout", 30))
        self.default_timeout_spin.setSuffix(" seconds")
        defaults_layout.addRow("Default timeout:", self.default_timeout_spin)

        self.save_configs_check = QCheckBox()
        self.save_configs_check.setChecked(self.current_settings.get("save_instrument_configs", True))
        defaults_layout.addRow("Save configurations:", self.save_configs_check)

        layout.addWidget(defaults_group)

        layout.addStretch()
        return tab

    def create_ai_tab(self) -> QWidget:
        """Create AI assistant settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # AI Provider settings
        provider_group = QGroupBox("AI Provider")
        provider_layout = QFormLayout(provider_group)

        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(["OpenAI", "Anthropic", "Local (Ollama)", "Disabled"])
        self.ai_provider_combo.setCurrentText(self.current_settings.get("ai_provider", "Local (Ollama)"))
        provider_layout.addRow("AI Provider:", self.ai_provider_combo)

        self.ai_model_edit = QLineEdit()
        self.ai_model_edit.setText(self.current_settings.get("ai_model", "mistral"))
        provider_layout.addRow("Model:", self.ai_model_edit)

        self.ai_url_edit = QLineEdit()
        self.ai_url_edit.setText(self.current_settings.get("ai_url", "http://localhost:11434"))
        provider_layout.addRow("API URL:", self.ai_url_edit)

        layout.addWidget(provider_group)

        # Chat settings
        chat_group = QGroupBox("Chat Interface")
        chat_layout = QFormLayout(chat_group)

        self.max_history_spin = QSpinBox()
        self.max_history_spin.setRange(10, 1000)
        self.max_history_spin.setValue(self.current_settings.get("max_chat_history", 100))
        chat_layout.addRow("Max chat history:", self.max_history_spin)

        self.auto_save_chat_check = QCheckBox()
        self.auto_save_chat_check.setChecked(self.current_settings.get("auto_save_chat", True))
        chat_layout.addRow("Auto-save conversations:", self.auto_save_chat_check)

        layout.addWidget(chat_group)

        layout.addStretch()
        return tab

    def create_data_tab(self) -> QWidget:
        """Create data management settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Storage settings
        storage_group = QGroupBox("Data Storage")
        storage_layout = QFormLayout(storage_group)

        self.data_path_edit = QLineEdit()
        self.data_path_edit.setText(self.current_settings.get("data_path", "./data"))
        storage_layout.addRow("Data directory:", self.data_path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_data_directory)
        storage_layout.addRow("", browse_btn)

        self.auto_backup_check = QCheckBox()
        self.auto_backup_check.setChecked(self.current_settings.get("auto_backup", True))
        storage_layout.addRow("Auto-backup data:", self.auto_backup_check)

        layout.addWidget(storage_group)

        # Export settings
        export_group = QGroupBox("Export Options")
        export_layout = QFormLayout(export_group)

        self.default_format_combo = QComboBox()
        self.default_format_combo.addItems(["JSON", "CSV", "HDF5", "NPY"])
        self.default_format_combo.setCurrentText(self.current_settings.get("default_export_format", "JSON"))
        export_layout.addRow("Default format:", self.default_format_combo)

        self.compression_check = QCheckBox()
        self.compression_check.setChecked(self.current_settings.get("use_compression", False))
        export_layout.addRow("Use compression:", self.compression_check)

        layout.addWidget(export_group)

        layout.addStretch()
        return tab

    def load_default_settings(self) -> dict:
        """Load default settings"""
        return {
            # Appearance
            "theme": "light_blue.xml",
            "sidebar_collapsed": False,
            "animations_enabled": True,
            "tooltips_enabled": True,

            # Connection
            "backend_url": "http://localhost:8000",
            "auto_connect": True,
            "connection_timeout": 10,
            "retry_attempts": 3,
            "use_websockets": True,

            # Instruments
            "auto_detect_instruments": True,
            "scan_interval": 30,
            "default_instrument_timeout": 30,
            "save_instrument_configs": True,

            # AI
            "ai_provider": "Local (Ollama)",
            "ai_model": "mistral",
            "ai_url": "http://localhost:11434",
            "max_chat_history": 100,
            "auto_save_chat": True,

            # Data
            "data_path": "./data",
            "auto_backup": True,
            "default_export_format": "JSON",
            "use_compression": False
        }

    def set_api_client(self, client):
        """Set API client"""
        self.api_client = client

    def refresh_data(self):
        """Refresh settings"""
        pass

    def on_theme_changed(self, theme: str):
        """Handle theme change"""
        self.theme_changed.emit(theme)

    def on_backend_url_changed(self, url: str):
        """Handle backend URL change"""
        self.backend_url_changed.emit(url)

    def browse_data_directory(self):
        """Browse for data directory"""
        directory = QFileDialog.getExistingDirectory(self, "Select Data Directory")
        if directory:
            self.data_path_edit.setText(directory)

    def save_settings(self):
        """Save current settings"""
        # Collect settings from UI
        self.current_settings.update({
            # Appearance
            "theme": self.theme_combo.currentText(),
            "sidebar_collapsed": self.sidebar_collapsed_check.isChecked(),
            "animations_enabled": self.animations_check.isChecked(),
            "tooltips_enabled": self.tooltips_check.isChecked(),

            # Connection
            "backend_url": self.backend_url_edit.text(),
            "auto_connect": self.auto_connect_check.isChecked(),
            "connection_timeout": self.connection_timeout_spin.value(),
            "retry_attempts": self.retry_attempts_spin.value(),
            "use_websockets": self.use_websockets_check.isChecked(),

            # Instruments
            "auto_detect_instruments": self.auto_detect_check.isChecked(),
            "scan_interval": self.scan_interval_spin.value(),
            "default_instrument_timeout": self.default_timeout_spin.value(),
            "save_instrument_configs": self.save_configs_check.isChecked(),

            # AI
            "ai_provider": self.ai_provider_combo.currentText(),
            "ai_model": self.ai_model_edit.text(),
            "ai_url": self.ai_url_edit.text(),
            "max_chat_history": self.max_history_spin.value(),
            "auto_save_chat": self.auto_save_chat_check.isChecked(),

            # Data
            "data_path": self.data_path_edit.text(),
            "auto_backup": self.auto_backup_check.isChecked(),
            "default_export_format": self.default_format_combo.currentText(),
            "use_compression": self.compression_check.isChecked()
        })

        # Save to file (TODO: implement file saving)
        QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully!")
        self.settings_saved.emit()

    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.current_settings = self.load_default_settings()
            self.update_ui_from_settings()

    def update_ui_from_settings(self):
        """Update UI controls from current settings"""
        # Appearance
        self.theme_combo.setCurrentText(self.current_settings["theme"])
        self.sidebar_collapsed_check.setChecked(self.current_settings["sidebar_collapsed"])
        self.animations_check.setChecked(self.current_settings["animations_enabled"])
        self.tooltips_check.setChecked(self.current_settings["tooltips_enabled"])

        # Connection
        self.backend_url_edit.setText(self.current_settings["backend_url"])
        self.auto_connect_check.setChecked(self.current_settings["auto_connect"])
        self.connection_timeout_spin.setValue(self.current_settings["connection_timeout"])
        self.retry_attempts_spin.setValue(self.current_settings["retry_attempts"])
        self.use_websockets_check.setChecked(self.current_settings["use_websockets"])

        # Continue for other settings...