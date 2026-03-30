#!/usr/bin/env python3
"""
LabPilot Qt Material Manager - Main Management Interface
Converted from React frontend to provide complete manager functionality with Material Design
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame, QScrollArea,
    QGridLayout, QSplitter, QTextEdit, QLineEdit, QComboBox,
    QProgressBar, QGroupBox, QListWidget, QListWidgetItem,
    QTabWidget, QCheckBox, QSpinBox, QSlider, QTreeWidget,
    QTreeWidgetItem, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QFileDialog, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize, QPropertyAnimation,
    QEasingCurve, QRect, QUrl
)
from PyQt6.QtGui import (
    QIcon, QFont, QPixmap, QPainter, QColor, QBrush, QPen,
    QLinearGradient, QDesktopServices
)

import pyqtgraph as pg
import qdarkstyle

# Import existing components
from .main import DashboardInstrument, InstrumentKind

class PageType(Enum):
    """Page types matching the React manager"""
    DASHBOARD = "dashboard"
    DEVICES = "devices"
    WORKFLOWS = "workflows"
    FLOW_CHART = "flow"
    AI_ASSISTANT = "ai"
    DATA = "data"
    SETTINGS = "settings"

@dataclass
class SessionState:
    """Session state matching React store"""
    connected: bool = False
    session_id: str = ""
    device_count: int = 0
    ai_available: bool = False
    backend_url: str = "http://localhost:8000"

@dataclass
class UIPreferences:
    """User preferences matching React store"""
    dark_mode: bool = True  # Use dark theme by default
    sidebar_collapsed: bool = False
    auto_connect: bool = True
    notifications_enabled: bool = True

class MaterialSidebar(QFrame):
    """Material Design sidebar with navigation"""

    # Signal emitted when page is selected
    page_selected = pyqtSignal(str)  # PageType.value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.collapsed = False
        self.setup_ui()

    def setup_ui(self):
        """Setup sidebar UI with Material Design"""
        self.setObjectName("sidebar")
        self.setFixedWidth(80)  # Narrower for icon-only navigation
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header section - compact for icon-only design
        header = QFrame()
        header.setObjectName("sidebar_header")
        header.setFixedHeight(60)
        header_layout = QVBoxLayout(header)

        # Logo/Title - compact
        title_label = QLabel("◎")  # Simple logo icon
        title_label.setObjectName("sidebar_title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setToolTip("LabPilot Manager")
        header_layout.addWidget(title_label)

        layout.addWidget(header)

        # Navigation buttons
        nav_frame = QFrame()
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setSpacing(2)  # Tighter spacing for icons
        nav_layout.setContentsMargins(8, 8, 8, 8)

        # Navigation items with Material UI icons (icon-first design)
        nav_items = [
            (PageType.DASHBOARD, "◎", "Dashboard"),
            (PageType.DEVICES, "○", "Devices"),
            (PageType.WORKFLOWS, "▷", "Workflows"),
            (PageType.FLOW_CHART, "⧉", "Flow"),
            (PageType.AI_ASSISTANT, "◉", "AI"),
            (PageType.DATA, "▦", "Data"),
            (PageType.SETTINGS, "⚙", "Settings")
        ]

        self.nav_buttons = {}
        for page_type, icon, label in nav_items:
            # Create icon-only button for minimalistic design
            btn = QPushButton(icon)
            btn.setObjectName("nav_button")
            btn.setCheckable(True)
            btn.setToolTip(label)  # Show label on hover
            btn.setFixedSize(48, 48)  # Square icon buttons
            btn.clicked.connect(lambda checked, pt=page_type: self.select_page(pt))
            nav_layout.addWidget(btn)
            self.nav_buttons[page_type] = btn

        # Select dashboard by default
        self.nav_buttons[PageType.DASHBOARD].setChecked(True)

        nav_layout.addStretch()
        layout.addWidget(nav_frame)

        # Footer with theme toggle and collapse button
        footer = QFrame()
        footer.setFixedHeight(60)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        footer_layout.setSpacing(8)

        # Theme toggle button
        self.theme_btn = QPushButton("☀")  # Sun icon for light mode
        self.theme_btn.setObjectName("theme_button")
        self.theme_btn.setFixedSize(32, 32)
        self.theme_btn.setToolTip("Toggle Light/Dark Mode")
        footer_layout.addWidget(self.theme_btn)

        footer_layout.addStretch()

        self.collapse_btn = QPushButton("◀")
        self.collapse_btn.setObjectName("collapse_button")
        self.collapse_btn.setFixedSize(32, 32)
        self.collapse_btn.setToolTip("Collapse Sidebar")
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        footer_layout.addWidget(self.collapse_btn)

        layout.addWidget(footer)

    def select_page(self, page_type: PageType):
        """Select a navigation page"""
        # Update button states
        for btn in self.nav_buttons.values():
            btn.setChecked(False)
        self.nav_buttons[page_type].setChecked(True)

        # Emit signal
        self.page_selected.emit(page_type.value)

    def update_session_info(self, session: SessionState):
        """Update session information display - placeholder for icon sidebar"""
        # No session display in icon-only sidebar
        # Could add tooltip or status indicator if needed
        pass

    def toggle_collapse(self):
        """Toggle sidebar collapse state"""
        target_width = 60 if not self.collapsed else 80  # Smaller widths for icon sidebar

        # Animate width change
        self.animation = QPropertyAnimation(self, b"maximumWidth")
        self.animation.setDuration(300)
        self.animation.setStartValue(self.width())
        self.animation.setEndValue(target_width)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.start()

        self.collapsed = not self.collapsed
        self.collapse_btn.setText("▶" if self.collapsed else "◀")

    def set_theme_toggle_handler(self, handler):
        """Connect theme toggle button to handler"""
        self.theme_btn.clicked.connect(handler)

    def update_theme_icon(self, is_dark_mode: bool):
        """Update theme button icon based on current theme"""
        self.theme_btn.setText("☾" if is_dark_mode else "☀")  # Moon for dark, sun for light

class BasePage(QWidget):
    """Base class for all manager pages"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None  # Will be set by main window
        self.setup_ui()

    def setup_ui(self):
        """Override in subclasses"""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Base Page - Override setup_ui()"))

    def refresh_data(self):
        """Override to refresh page data"""
        pass

    def set_api_client(self, client):
        """Set API client for backend communication"""
        self.api_client = client

class LabPilotMaterialManager(QMainWindow):
    """Main Qt Material Manager Window"""

    def __init__(self):
        super().__init__()
        self.session = SessionState()
        self.preferences = UIPreferences()
        self.pages = {}
        self.api_client = None

        self.setup_ui()
        self.apply_dark_theme()
        self.sidebar.update_theme_icon(self.preferences.dark_mode)  # Initialize theme icon
        self.setup_auto_refresh()

    def setup_ui(self):
        """Setup main window UI"""
        self.setWindowTitle("LabPilot Manager")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = MaterialSidebar()
        self.sidebar.page_selected.connect(self.switch_page)
        self.sidebar.set_theme_toggle_handler(self.toggle_theme)
        main_layout.addWidget(self.sidebar)

        # Content area
        content_frame = QFrame()
        content_frame.setObjectName("content_frame")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Page stack
        self.page_stack = QStackedWidget()
        content_layout.addWidget(self.page_stack)

        main_layout.addWidget(content_frame, 1)

        # Initialize pages
        self.init_pages()

        # Apply initial theme to all pages
        self.update_pages_theme()

    def apply_dark_theme(self):
        """Apply minimalistic theme matching React workflows page"""
        try:
            # Apply QDarkStyleSheet base theme only for dark mode
            if self.preferences.dark_mode:
                self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())
            else:
                self.setStyleSheet("")  # Clear dark style for light mode

            # Minimalistic styling matching React design exactly
            minimalistic_style = """
                /* Main window - clean backgrounds */
                QMainWindow {
                    background-color: """ + ("#111827" if self.preferences.dark_mode else "#F9FAFB") + """;
                    font-family: -apple-system, BlinkMacSystemFont, 'Inter', system-ui, sans-serif;
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                }

                /* Sidebar - minimal design like React */
                #sidebar {
                    background-color: """ + ("#1F2937" if self.preferences.dark_mode else "#FFFFFF") + """;
                    border-right: 1px solid """ + ("#374151" if self.preferences.dark_mode else "#E5E7EB") + """;
                    border-radius: 0;
                }

                #sidebar_title {
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                    font-size: 24px;
                    font-weight: 700;
                    padding: 12px;
                    background: transparent;
                    border: none;
                }

                /* Navigation buttons - minimal icon-only design */
                #nav_button {
                    text-align: center;
                    padding: 0;
                    border: none;
                    background: transparent;
                    color: """ + ("#9CA3AF" if self.preferences.dark_mode else "#6B7280") + """;
                    border-radius: 12px;
                    margin: 4px 12px;
                    font-size: 18px;
                    font-weight: 500;
                    min-height: 48px;
                    max-height: 48px;
                    min-width: 48px;
                    max-width: 48px;
                }

                #nav_button:hover {
                    background-color: """ + ("#374151" if self.preferences.dark_mode else "#F3F4F6") + """;
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                }

                #nav_button:checked {
                    background-color: """ + ("#3B82F6" if self.preferences.dark_mode else "#EBF4FF") + """;
                    color: """ + ("#FFFFFF" if self.preferences.dark_mode else "#1D4ED8") + """;
                }

                /* Theme and collapse buttons */
                #theme_button, #collapse_button {
                    text-align: center;
                    padding: 0;
                    border: 1px solid """ + ("#374151" if self.preferences.dark_mode else "#E5E7EB") + """;
                    background: """ + ("#2D3748" if self.preferences.dark_mode else "#FFFFFF") + """;
                    color: """ + ("#D1D5DB" if self.preferences.dark_mode else "#4A5568") + """;
                    border-radius: 8px;
                    font-size: 14px;
                    min-height: 32px;
                    max-height: 32px;
                    min-width: 32px;
                    max-width: 32px;
                }

                #theme_button:hover, #collapse_button:hover {
                    background-color: """ + ("#4A5568" if self.preferences.dark_mode else "#F7FAFC") + """;
                    border-color: """ + ("#6B7280" if self.preferences.dark_mode else "#CBD5E0") + """;
                }

                /* Content frame - clean design */
                #content_frame {
                    background-color: """ + ("#111827" if self.preferences.dark_mode else "#F9FAFB") + """;
                    border: none;
                }

                /* All QWidget defaults */
                QWidget {
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                    background-color: """ + ("#111827" if self.preferences.dark_mode else "#F9FAFB") + """;
                }

                /* Labels - ensure visibility */
                QLabel {
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                    background-color: transparent;
                    border: none;
                }

                /* Buttons - clean React-style */
                QPushButton {
                    padding: 8px 16px;
                    border: 1px solid """ + ("#4B5563" if self.preferences.dark_mode else "#D1D5DB") + """;
                    border-radius: 6px;
                    background-color: """ + ("#374151" if self.preferences.dark_mode else "#FFFFFF") + """;
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#374151") + """;
                    font-size: 14px;
                    font-weight: 500;
                    min-height: 36px;
                }

                QPushButton:hover {
                    background-color: """ + ("#4B5563" if self.preferences.dark_mode else "#F9FAFB") + """;
                    border-color: """ + ("#6B7280" if self.preferences.dark_mode else "#9CA3AF") + """;
                }

                /* Frame styling */
                QFrame {
                    background-color: """ + ("#1F2937" if self.preferences.dark_mode else "#FFFFFF") + """;
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                    border-color: """ + ("#374151" if self.preferences.dark_mode else "#E5E7EB") + """;
                }

                /* Placeholder page text */
                #page_title {
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                    background-color: transparent;
                }

                /* Scroll areas */
                QScrollArea {
                    background-color: """ + ("#111827" if self.preferences.dark_mode else "#F9FAFB") + """;
                    border: none;
                }

                /* Input fields */
                QLineEdit, QTextEdit, QComboBox {
                    background-color: """ + ("#374151" if self.preferences.dark_mode else "#FFFFFF") + """;
                    color: """ + ("#F9FAFB" if self.preferences.dark_mode else "#111827") + """;
                    border: 1px solid """ + ("#4B5563" if self.preferences.dark_mode else "#D1D5DB") + """;
                    border-radius: 6px;
                    padding: 8px 12px;
                }

                QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                    border-color: """ + ("#3B82F6" if self.preferences.dark_mode else "#2563EB") + """;
                }
            """

            # Apply the clean styling (append to existing or replace)
            current_style = self.styleSheet() if self.preferences.dark_mode else ""
            self.setStyleSheet(current_style + minimalistic_style)

        except Exception as e:
            print(f"Warning: Could not apply minimalistic theme: {e}")

    def init_pages(self):
        """Initialize all manager pages"""
        # Import page classes with fallback handling
        page_classes = {}

        try:
            from dashboard_page import DashboardPage
            page_classes[PageType.DASHBOARD] = DashboardPage
        except ImportError as e:
            print(f"Warning: Could not import DashboardPage: {e}")

        try:
            from devices_page import DevicesPage
            page_classes[PageType.DEVICES] = DevicesPage
        except ImportError as e:
            print(f"Warning: Could not import DevicesPage: {e}")

        try:
            from workflows_page import WorkflowsPage
            page_classes[PageType.WORKFLOWS] = WorkflowsPage
        except ImportError as e:
            print(f"Warning: Could not import WorkflowsPage: {e}")

        try:
            from ai_assistant_page import AIAssistantPage
            page_classes[PageType.AI_ASSISTANT] = AIAssistantPage
        except ImportError as e:
            print(f"Warning: Could not import AIAssistantPage: {e}")

        try:
            from data_page import DataPage
            page_classes[PageType.DATA] = DataPage
        except ImportError as e:
            print(f"Warning: Could not import DataPage: {e}")

        try:
            from settings_page import SettingsPage
            page_classes[PageType.SETTINGS] = SettingsPage
        except ImportError as e:
            print(f"Warning: Could not import SettingsPage: {e}")

        # Create pages
        for page_type in PageType:
            if page_type in page_classes:
                try:
                    page = page_classes[page_type]()
                    if self.api_client:
                        page.set_api_client(self.api_client)
                    self.pages[page_type] = page
                    self.page_stack.addWidget(page)
                except Exception as e:
                    print(f"Error creating {page_type.value} page: {e}")
                    # Create placeholder
                    page = self.create_placeholder_page(page_type.value.title())
                    self.pages[page_type] = page
                    self.page_stack.addWidget(page)
            else:
                # Create placeholder for missing page
                page = self.create_placeholder_page(page_type.value.title())
                self.pages[page_type] = page
                self.page_stack.addWidget(page)

        # Show dashboard initially
        self.switch_page(PageType.DASHBOARD.value)

    def create_placeholder_page(self, title: str) -> QWidget:
        """Create placeholder for unimplemented pages"""
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)

        header = QLabel(f"{title} Page")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 40px;")

        message = QLabel(f"The {title} page is under development.")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setStyleSheet("color: #666; font-size: 16px;")

        layout.addStretch()
        layout.addWidget(header)
        layout.addWidget(message)
        layout.addStretch()

        return placeholder

    def switch_page(self, page_name: str):
        """Switch to specified page"""
        try:
            page_type = PageType(page_name)
            if page_type in self.pages:
                page = self.pages[page_type]
                self.page_stack.setCurrentWidget(page)
                # Refresh page data
                if hasattr(page, 'refresh_data'):
                    page.refresh_data()
        except ValueError:
            print(f"Unknown page: {page_name}")

    def toggle_theme(self):
        """Toggle between light and dark theme"""
        self.preferences.dark_mode = not self.preferences.dark_mode
        self.apply_dark_theme()
        self.sidebar.update_theme_icon(self.preferences.dark_mode)

        # Update theme for all pages
        self.update_pages_theme()

    def update_pages_theme(self):
        """Update theme for all pages"""
        for page in self.pages.values():
            if hasattr(page, 'set_theme'):
                page.set_theme(self.preferences.dark_mode)

    def setup_auto_refresh(self):
        """Setup auto-refresh timer for real-time updates"""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_session_data)
        self.refresh_timer.start(5000)  # 5 second refresh

    def refresh_session_data(self):
        """Refresh session and device data"""
        if self.api_client:
            # This will be implemented when API client is added
            pass

        # Update sidebar
        self.sidebar.update_session_info(self.session)

def main():
    """Main entry point for Qt Material Manager"""
    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot Manager")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("Laboratory Automation")

    # Create and show manager
    manager = LabPilotMaterialManager()
    manager.show()

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())