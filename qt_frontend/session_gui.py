"""
LabPilot Qt Session Management GUI
User-friendly interface for managing Qt window sessions
"""

import sys
from typing import Dict, List, Optional
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QGroupBox, QSplitter, QFrame, QMessageBox, QDialog, QDialogButtonBox,
    QCheckBox, QSpinBox, QTabWidget, QScrollArea, QMenuBar, QMenu, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor
from .session_manager import session_manager, SessionData

class SessionInfoWidget(QWidget):
    """Widget to display session information"""

    def __init__(self, session_name: str):
        super().__init__()
        self.session_name = session_name
        self.setup_ui()
        self.load_session_info()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        # Session name header
        name_label = QLabel(self.session_name)
        name_label.setFont(QFont("", 14, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #3B82F6; margin-bottom: 8px;")
        layout.addWidget(name_label)

        # Info grid
        self.info_layout = QGridLayout()
        layout.addLayout(self.info_layout)

        # Description area
        layout.addWidget(QLabel("Description:"))
        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("background: #f5f5f5; padding: 8px; border-radius: 4px; margin-bottom: 8px;")
        layout.addWidget(self.description_label)

        # Instruments list
        layout.addWidget(QLabel("Instruments:"))
        self.instruments_list = QListWidget()
        self.instruments_list.setMaximumHeight(120)
        layout.addWidget(self.instruments_list)

        layout.addStretch()

    def load_session_info(self):
        """Load and display session information"""
        info = session_manager.get_session_info(self.session_name)
        if not info:
            return

        # Display basic info
        row = 0
        info_items = [
            ("Created:", datetime.fromisoformat(info['created_at']).strftime("%Y-%m-%d %H:%M")),
            ("Modified:", datetime.fromisoformat(info['modified_at']).strftime("%Y-%m-%d %H:%M")),
            ("Windows:", str(info['window_count']))
        ]

        for label, value in info_items:
            self.info_layout.addWidget(QLabel(label), row, 0)
            value_label = QLabel(value)
            value_label.setStyleSheet("font-weight: bold;")
            self.info_layout.addWidget(value_label, row, 1)
            row += 1

        # Description
        self.description_label.setText(info['description'] or "No description")

        # Instruments
        for instrument_id in info['instruments']:
            self.instruments_list.addItem(instrument_id)

class NewSessionDialog(QDialog):
    """Dialog for creating a new session"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Session")
        self.setModal(True)
        self.setMinimumSize(400, 200)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Session name
        layout.addWidget(QLabel("Session Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter session name...")
        layout.addWidget(self.name_edit)

        # Description
        layout.addWidget(QLabel("Description (optional):"))
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("Enter session description...")
        layout.addWidget(self.description_edit)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_session_data(self):
        """Get session name and description"""
        return {
            'name': self.name_edit.text().strip(),
            'description': self.description_edit.toPlainText().strip()
        }

class QtSessionManagerWindow(QMainWindow):
    """
    Main session management window
    User-friendly interface for managing Qt sessions
    """

    session_action_requested = pyqtSignal(str, str)  # action, session_name

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LabPilot Session Manager")
        self.setMinimumSize(800, 600)
        self.setWindowFlags(Qt.WindowType.Window)

        # Session data
        self.current_session = session_manager.settings.value("last_session", "")
        self.sessions_info: Dict[str, Dict] = {}

        self.setup_ui()
        self.setup_connections()
        self.refresh_sessions()

        # Apply session manager theme
        self.apply_session_theme()

        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_sessions)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds

    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create splitter for resizable panes
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane - Session list and controls
        left_panel = self.create_left_panel()
        left_panel.setMinimumWidth(300)
        left_panel.setMaximumWidth(400)

        # Right pane - Session details and settings
        right_panel = self.create_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 450])

        layout.addWidget(splitter)

    def create_left_panel(self) -> QWidget:
        """Create left panel with session list and controls"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Sessions")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        header_layout.addWidget(title)

        # Session count
        self.session_count_label = QLabel("0 sessions")
        self.session_count_label.setStyleSheet("color: #666; font-size: 12px;")
        header_layout.addStretch()
        header_layout.addWidget(self.session_count_label)

        layout.addLayout(header_layout)

        # Current session indicator
        current_group = QGroupBox("Current Session")
        current_layout = QVBoxLayout(current_group)

        self.current_session_label = QLabel("No session loaded")
        self.current_session_label.setStyleSheet("font-weight: bold; color: #10B981;")
        current_layout.addWidget(self.current_session_label)

        # Active windows count
        self.active_windows_label = QLabel("0 active windows")
        self.active_windows_label.setStyleSheet("color: #666; font-size: 11px;")
        current_layout.addWidget(self.active_windows_label)

        layout.addWidget(current_group)

        # Actions buttons
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QGridLayout(actions_group)

        self.save_btn = QPushButton("💾 Save Session")
        self.save_btn.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 8px;")
        self.save_btn.clicked.connect(self.save_current_session)

        self.load_btn = QPushButton("📂 Load Session")
        self.load_btn.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 8px;")
        self.load_btn.clicked.connect(self.load_selected_session)

        self.close_all_btn = QPushButton("❌ Close All")
        self.close_all_btn.setStyleSheet("background-color: #EF4444; color: white; font-weight: bold; padding: 8px;")
        self.close_all_btn.clicked.connect(self.close_all_windows)

        actions_layout.addWidget(self.save_btn, 0, 0)
        actions_layout.addWidget(self.load_btn, 0, 1)
        actions_layout.addWidget(self.close_all_btn, 1, 0, 1, 2)

        layout.addWidget(actions_group)

        # Sessions list
        list_group = QGroupBox("Saved Sessions")
        list_layout = QVBoxLayout(list_group)

        self.sessions_list = QListWidget()
        self.sessions_list.setAlternatingRowColors(True)
        self.sessions_list.itemSelectionChanged.connect(self.on_session_selected)
        self.sessions_list.itemDoubleClicked.connect(self.load_selected_session)
        list_layout.addWidget(self.sessions_list)

        # Session list controls
        list_controls = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_sessions)

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setStyleSheet("color: #EF4444;")
        self.delete_btn.clicked.connect(self.delete_selected_session)
        self.delete_btn.setEnabled(False)

        list_controls.addWidget(self.refresh_btn)
        list_controls.addWidget(self.delete_btn)

        list_layout.addLayout(list_controls)

        layout.addWidget(list_group)

        return panel

    def create_right_panel(self) -> QWidget:
        """Create right panel with session details and settings"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)

        # Tab widget for organized content
        self.tab_widget = QTabWidget()

        # Session Details Tab
        details_tab = QScrollArea()
        details_tab.setWidgetResizable(True)
        details_tab.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)

        # Placeholder for session info
        self.session_info_widget = None
        self.no_selection_label = QLabel("Select a session to view details")
        self.no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_selection_label.setStyleSheet("color: #666; font-size: 14px; margin: 40px;")
        self.details_layout.addWidget(self.no_selection_label)

        details_tab.setWidget(self.details_widget)
        self.tab_widget.addTab(details_tab, "📄 Session Details")

        # Settings Tab
        settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(settings_tab, "⚙️ Settings")

        # Help Tab
        help_tab = self.create_help_tab()
        self.tab_widget.addTab(help_tab, "❓ Help")

        layout = QVBoxLayout(panel)
        layout.addWidget(self.tab_widget)

        return panel

    def create_settings_tab(self) -> QWidget:
        """Create settings tab"""
        widget = QScrollArea()
        widget.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)

        # Auto-save settings
        autosave_group = QGroupBox("Auto-Save")
        autosave_layout = QGridLayout(autosave_group)

        self.autosave_enabled = QCheckBox("Enable automatic session saving")
        self.autosave_enabled.setChecked(True)
        autosave_layout.addWidget(self.autosave_enabled, 0, 0, 1, 2)

        autosave_layout.addWidget(QLabel("Auto-save interval (minutes):"), 1, 0)
        self.autosave_interval = QSpinBox()
        self.autosave_interval.setRange(1, 60)
        self.autosave_interval.setValue(5)
        autosave_layout.addWidget(self.autosave_interval, 1, 1)

        layout.addWidget(autosave_group)

        # Session settings
        session_group = QGroupBox("Session Behavior")
        session_layout = QGridLayout(session_group)

        self.restore_position = QCheckBox("Restore window positions")
        self.restore_position.setChecked(True)
        session_layout.addWidget(self.restore_position, 0, 0)

        self.restore_size = QCheckBox("Restore window sizes")
        self.restore_size.setChecked(True)
        session_layout.addWidget(self.restore_size, 1, 0)

        self.restore_visibility = QCheckBox("Restore window visibility")
        self.restore_visibility.setChecked(True)
        session_layout.addWidget(self.restore_visibility, 2, 0)

        layout.addWidget(session_group)

        # Apply button
        apply_btn = QPushButton("Apply Settings")
        apply_btn.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 8px;")
        apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(apply_btn)

        layout.addStretch()

        widget.setWidget(content)
        return widget

    def create_help_tab(self) -> QWidget:
        """Create help tab"""
        widget = QScrollArea()
        widget.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)

        help_text = """
        <h3>LabPilot Session Manager Help</h3>

        <h4>🎯 What are Sessions?</h4>
        <p>Sessions save the complete state of your LabPilot Qt workspace, including:</p>
        <ul>
            <li>Which instrument windows are open</li>
            <li>Window positions and sizes</li>
            <li>Window settings and configurations</li>
            <li>Dock widget arrangements</li>
        </ul>

        <h4>💾 Saving Sessions</h4>
        <p>Click <b>"Save Session"</b> to save your current workspace. You'll be prompted for:</p>
        <ul>
            <li>Session name (required)</li>
            <li>Description (optional)</li>
        </ul>

        <h4>📂 Loading Sessions</h4>
        <p>To load a session:</p>
        <ol>
            <li>Select a session from the list</li>
            <li>Click <b>"Load Session"</b> or double-click the session</li>
            <li>All current windows will be closed</li>
            <li>Session windows will be restored</li>
        </ol>

        <h4>⚙️ Auto-Save</h4>
        <p>Enable auto-save to automatically backup your workspace every few minutes. Auto-saved sessions are named with timestamps.</p>

        <h4>🗂️ Session Files</h4>
        <p>Sessions are stored as JSON files in:</p>
        <p><code>~/.labpilot/sessions/</code></p>

        <h4>🎨 Tips</h4>
        <ul>
            <li>Create different sessions for different experiments</li>
            <li>Use descriptive names: "Spectroscopy_Setup", "Camera_Alignment"</li>
            <li>Save sessions before major changes</li>
            <li>Auto-save provides backup protection</li>
        </ul>
        """

        help_label = QLabel(help_text)
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)
        help_label.setOpenExternalLinks(True)

        layout.addWidget(help_label)
        layout.addStretch()

        widget.setWidget(content)
        return widget

    def setup_connections(self):
        """Setup signal connections"""
        session_manager.session_saved.connect(self.on_session_saved)
        session_manager.session_loaded.connect(self.on_session_loaded)

    def apply_session_theme(self):
        """Apply consistent theming"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #495057;
            }
            QListWidget {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background-color: white;
                selection-background-color: #3B82F6;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f1f3f4;
            }
            QPushButton {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 6px 12px;
                background-color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #f8f9fa;
                border-color: #adb5bd;
            }
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background-color: white;
            }
        """)

    @pyqtSlot()
    def refresh_sessions(self):
        """Refresh the sessions list"""
        # Clear current list
        self.sessions_list.clear()
        self.sessions_info.clear()

        # Get available sessions
        session_names = session_manager.get_available_sessions()

        for session_name in session_names:
            info = session_manager.get_session_info(session_name)
            if info:
                self.sessions_info[session_name] = info

                # Create list item
                item = QListWidgetItem()
                item.setText(session_name)
                item.setData(Qt.ItemDataRole.UserRole, session_name)

                # Add tooltip with info
                tooltip = f"Created: {datetime.fromisoformat(info['created_at']).strftime('%Y-%m-%d %H:%M')}\n"
                tooltip += f"Windows: {info['window_count']}\n"
                if info['description']:
                    tooltip += f"Description: {info['description']}"
                item.setToolTip(tooltip)

                self.sessions_list.addItem(item)

        # Update count
        self.session_count_label.setText(f"{len(session_names)} sessions")

        # Update current session display
        if self.current_session and self.current_session in session_names:
            self.current_session_label.setText(self.current_session)
        else:
            self.current_session_label.setText("No session loaded")

        # Update active windows count
        active_count = len(session_manager.active_windows)
        self.active_windows_label.setText(f"{active_count} active windows")

    @pyqtSlot()
    def on_session_selected(self):
        """Handle session selection"""
        current_item = self.sessions_list.currentItem()
        if current_item:
            session_name = current_item.data(Qt.ItemDataRole.UserRole)
            self.show_session_details(session_name)
            self.delete_btn.setEnabled(True)
            self.load_btn.setEnabled(True)
        else:
            self.show_no_selection()
            self.delete_btn.setEnabled(False)
            self.load_btn.setEnabled(False)

    def show_session_details(self, session_name: str):
        """Show details for selected session"""
        # Clear current content
        if self.session_info_widget:
            self.details_layout.removeWidget(self.session_info_widget)
            self.session_info_widget.deleteLater()

        if self.no_selection_label.parent():
            self.details_layout.removeWidget(self.no_selection_label)

        # Create and add session info widget
        self.session_info_widget = SessionInfoWidget(session_name)
        self.details_layout.addWidget(self.session_info_widget)

    def show_no_selection(self):
        """Show no selection placeholder"""
        if self.session_info_widget:
            self.details_layout.removeWidget(self.session_info_widget)
            self.session_info_widget.deleteLater()
            self.session_info_widget = None

        self.details_layout.addWidget(self.no_selection_label)

    @pyqtSlot()
    def save_current_session(self):
        """Save current session"""
        dialog = NewSessionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_session_data()
            if data['name']:
                success = session_manager.save_session(data['name'], data['description'])
                if success:
                    self.current_session = data['name']
                    self.refresh_sessions()

    @pyqtSlot()
    def load_selected_session(self):
        """Load selected session"""
        current_item = self.sessions_list.currentItem()
        if current_item:
            session_name = current_item.data(Qt.ItemDataRole.UserRole)

            # Confirm if there are active windows
            if len(session_manager.active_windows) > 0:
                reply = QMessageBox.question(
                    self,
                    "Load Session",
                    f"Loading '{session_name}' will close all current windows.\nContinue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # Load session (async operation)
            success = session_manager.load_session(session_name)
            if success:
                self.current_session = session_name
                self.refresh_sessions()

    @pyqtSlot()
    def delete_selected_session(self):
        """Delete selected session"""
        current_item = self.sessions_list.currentItem()
        if current_item:
            session_name = current_item.data(Qt.ItemDataRole.UserRole)

            reply = QMessageBox.question(
                self,
                "Delete Session",
                f"Are you sure you want to delete '{session_name}'?\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                success = session_manager.delete_session(session_name)
                if success:
                    if self.current_session == session_name:
                        self.current_session = ""
                    self.refresh_sessions()

    @pyqtSlot()
    def close_all_windows(self):
        """Close all active windows"""
        if len(session_manager.active_windows) > 0:
            reply = QMessageBox.question(
                self,
                "Close All Windows",
                f"Close all {len(session_manager.active_windows)} active windows?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                session_manager.close_all_windows()
                self.refresh_sessions()

    @pyqtSlot()
    def apply_settings(self):
        """Apply session settings"""
        # Start/stop auto-save based on settings
        if self.autosave_enabled.isChecked():
            interval = self.autosave_interval.value() * 60  # Convert to seconds
            session_manager.start_auto_save(interval)
        else:
            session_manager.stop_auto_save()

        # Show confirmation
        QMessageBox.information(self, "Settings Applied", "Session settings have been applied successfully.")

    @pyqtSlot(str)
    def on_session_saved(self, session_name: str):
        """Handle session saved signal"""
        self.refresh_sessions()

    @pyqtSlot(str)
    def on_session_loaded(self, session_name: str):
        """Handle session loaded signal"""
        self.current_session = session_name
        self.refresh_sessions()

def main():
    """Test the session manager window"""
    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot Session Manager")

    window = QtSessionManagerWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()