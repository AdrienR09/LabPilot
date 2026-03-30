#!/usr/bin/env python3
"""
LabPilot Qt Frontend - Individual Instrument Windows Only
Launches specific instrument Qt windows when called by the backend API
"""

import sys
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
import pyqtgraph as pg

# Set pyqtgraph configuration for professional scientific appearance
pg.setConfigOptions(antialias=True, useOpenGL=True, enableExperimental=False)

@dataclass
class DashboardInstrument:
    """Data class matching the API instrument structure"""
    id: str
    name: str
    adapter_type: str
    kind: str  # 'detector' or 'motor'
    dimensionality: str  # '0D', '1D', '2D', etc.
    connected: bool = False
    status: str = "Ready"
    tags: List[str] = None
    data: Optional[dict] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

class InstrumentKind(Enum):
    DETECTOR = "detector"
    MOTOR = "motor"

class LabPilotStyle:
    """Professional dark theme constants for scientific applications"""

    # Colors matching the web interface
    PRIMARY = "#3B82F6"      # Blue-500
    SUCCESS = "#10B981"      # Emerald-500
    WARNING = "#F59E0B"      # Amber-500
    DANGER = "#EF4444"       # Red-500

    # Background colors
    BG_PRIMARY = "#111827"    # Gray-900
    BG_SECONDARY = "#1F2937"  # Gray-800
    BG_TERTIARY = "#374151"   # Gray-700

    # Text colors
    TEXT_PRIMARY = "#F9FAFB"  # Gray-50
    TEXT_SECONDARY = "#D1D5DB" # Gray-300
    TEXT_MUTED = "#9CA3AF"    # Gray-400

    # Border colors
    BORDER = "#4B5563"        # Gray-600

    @staticmethod
    def apply_dark_theme(app: QApplication):
        """Apply professional dark theme to the entire application"""
        app.setStyle('Fusion')

        palette = QPalette()

        # Window colors
        palette.setColor(QPalette.ColorRole.Window, QColor(LabPilotStyle.BG_PRIMARY))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(LabPilotStyle.TEXT_PRIMARY))

        # Base colors (for input widgets)
        palette.setColor(QPalette.ColorRole.Base, QColor(LabPilotStyle.BG_SECONDARY))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(LabPilotStyle.BG_TERTIARY))

        # Button colors
        palette.setColor(QPalette.ColorRole.Button, QColor(LabPilotStyle.BG_SECONDARY))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(LabPilotStyle.TEXT_PRIMARY))

        # Text colors
        palette.setColor(QPalette.ColorRole.Text, QColor(LabPilotStyle.TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(LabPilotStyle.TEXT_PRIMARY))

        # Highlight colors
        palette.setColor(QPalette.ColorRole.Highlight, QColor(LabPilotStyle.PRIMARY))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(LabPilotStyle.TEXT_PRIMARY))

        # Disabled colors
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(LabPilotStyle.TEXT_MUTED))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(LabPilotStyle.TEXT_MUTED))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(LabPilotStyle.TEXT_MUTED))

        app.setPalette(palette)

        # Set global stylesheet for additional customization
        app.setStyleSheet(f"""
            QMainWindow {{
                background-color: {LabPilotStyle.BG_PRIMARY};
            }}

            QFrame {{
                border: 1px solid {LabPilotStyle.BORDER};
                border-radius: 8px;
                background-color: {LabPilotStyle.BG_SECONDARY};
            }}

            QPushButton {{
                border: 1px solid {LabPilotStyle.BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                background-color: {LabPilotStyle.BG_SECONDARY};
                color: {LabPilotStyle.TEXT_PRIMARY};
                font-weight: bold;
            }}

            QPushButton:hover {{
                background-color: {LabPilotStyle.BG_TERTIARY};
            }}

            QPushButton:pressed {{
                background-color: {LabPilotStyle.BORDER};
            }}

            QPushButton:disabled {{
                background-color: {LabPilotStyle.BG_TERTIARY};
                color: {LabPilotStyle.TEXT_MUTED};
            }}

            QPushButton.primary {{
                background-color: {LabPilotStyle.PRIMARY};
                border-color: {LabPilotStyle.PRIMARY};
            }}

            QPushButton.primary:hover {{
                background-color: #2563EB;
            }}

            QPushButton.success {{
                background-color: {LabPilotStyle.SUCCESS};
                border-color: {LabPilotStyle.SUCCESS};
            }}

            QPushButton.success:hover {{
                background-color: #059669;
            }}

            QPushButton.danger {{
                background-color: {LabPilotStyle.DANGER};
                border-color: {LabPilotStyle.DANGER};
            }}

            QPushButton.danger:hover {{
                background-color: #DC2626;
            }}

            QPushButton.warning {{
                background-color: {LabPilotStyle.WARNING};
                border-color: {LabPilotStyle.WARNING};
                color: #000000;
            }}

            QPushButton.warning:hover {{
                background-color: #D97706;
            }}

            QSpinBox, QDoubleSpinBox {{
                border: 1px solid {LabPilotStyle.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                background-color: {LabPilotStyle.BG_TERTIARY};
                color: {LabPilotStyle.TEXT_PRIMARY};
            }}

            QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {LabPilotStyle.PRIMARY};
            }}

            QSlider::groove:horizontal {{
                border: 1px solid {LabPilotStyle.BORDER};
                height: 8px;
                background: {LabPilotStyle.BG_TERTIARY};
                border-radius: 4px;
            }}

            QSlider::handle:horizontal {{
                background: {LabPilotStyle.PRIMARY};
                border: 2px solid {LabPilotStyle.PRIMARY};
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}

            QSlider::handle:horizontal:hover {{
                background: #2563EB;
                border-color: #2563EB;
            }}

            QLabel {{
                color: {LabPilotStyle.TEXT_PRIMARY};
            }}

            QLabel.title {{
                font-size: 18px;
                font-weight: bold;
                color: {LabPilotStyle.TEXT_PRIMARY};
            }}

            QLabel.subtitle {{
                font-size: 14px;
                color: {LabPilotStyle.TEXT_SECONDARY};
            }}

            QLabel.muted {{
                color: {LabPilotStyle.TEXT_MUTED};
            }}
        """)

def main():
    """Main application entry point - launches individual instrument windows only"""
    parser = argparse.ArgumentParser(description='LabPilot Individual Qt Instrument Windows')
    parser.add_argument('--instrument', type=str, help='Launch specific instrument window by ID')
    parser.add_argument('--type', type=str, choices=['detector', 'motor'], help='Instrument type')
    parser.add_argument('--dimensionality', type=str, help='Instrument dimensionality (0D, 1D, 2D, 3D)')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Laboratory Automation")

    # Apply professional dark theme
    LabPilotStyle.apply_dark_theme(app)

    if args.instrument:
        # Launch specific instrument window
        try:
            from authentic_qudi_windows import create_instrument_window
            from session_manager import session_manager

            # Create mock instrument data for the specific instrument
            instrument_data = {
                'id': args.instrument,
                'name': f"Instrument {args.instrument}",
                'adapter_type': 'unknown',
                'kind': args.type or 'detector',
                'dimensionality': args.dimensionality or '1D',
                'connected': True,
                'status': 'Ready',
                'tags': [],
                'data': None
            }

            instrument = DashboardInstrument(**instrument_data)
            window = create_instrument_window(instrument)

            # Register window with session manager
            window_id = f"{args.type}_{args.dimensionality}_{args.instrument}"
            session_manager.register_window(window_id, window)

            # Add session menu to window
            add_session_menu_to_window(window)

            window.show()
            window.raise_()
            window.activateWindow()

        except Exception as e:
            print(f"Failed to launch instrument window: {e}")
            sys.exit(1)
    else:
        # No main dashboard window - only individual instrument windows are supported
        print("Usage: python main.py --instrument <id> --type <detector|motor> --dimensionality <0D|1D|2D>")
        print("This Qt frontend only launches individual instrument windows.")
        print("Use the React web manager at http://localhost:3000 to manage instruments.")
        sys.exit(0)

def add_session_menu_to_window(window):
    """Add session management menu to a window"""
    try:
        from session_gui import QtSessionManagerWindow
        from session_manager import session_manager
        from PyQt6.QtWidgets import QMenuBar, QMenu
        from PyQt6.QtGui import QAction

        # Create menu bar if it doesn't exist
        if not window.menuBar():
            menu_bar = QMenuBar(window)
            window.setMenuBar(menu_bar)
        else:
            menu_bar = window.menuBar()

        # Add Session menu
        session_menu = menu_bar.addMenu("Session")

        # Save Session action
        save_action = QAction("💾 Save Session...", window)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(lambda: open_session_manager_save())
        session_menu.addAction(save_action)

        # Load Session action
        load_action = QAction("📂 Load Session...", window)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(lambda: open_session_manager_load())
        session_menu.addAction(load_action)

        session_menu.addSeparator()

        # Session Manager action
        manager_action = QAction("⚙️ Session Manager", window)
        manager_action.triggered.connect(lambda: open_session_manager())
        session_menu.addAction(manager_action)

        # Auto-save toggle
        session_menu.addSeparator()
        autosave_action = QAction("🔄 Enable Auto-Save", window)
        autosave_action.setCheckable(True)
        autosave_action.setChecked(True)
        autosave_action.triggered.connect(lambda checked: session_manager.start_auto_save() if checked else session_manager.stop_auto_save())
        session_menu.addAction(autosave_action)

        # Store session manager window reference
        window._session_manager_window = None

        def open_session_manager():
            """Open session manager window"""
            if window._session_manager_window is None:
                window._session_manager_window = QtSessionManagerWindow()
            window._session_manager_window.show()
            window._session_manager_window.raise_()
            window._session_manager_window.activateWindow()

        def open_session_manager_save():
            """Open session manager in save mode"""
            open_session_manager()
            if hasattr(window._session_manager_window, 'save_current_session'):
                window._session_manager_window.save_current_session()

        def open_session_manager_load():
            """Open session manager in load mode"""
            open_session_manager()
            # Focus on sessions list for loading
            if hasattr(window._session_manager_window, 'sessions_list'):
                window._session_manager_window.sessions_list.setFocus()

    except Exception as e:
        print(f"Warning: Failed to add session menu: {e}")

def main():
    """Main application entry point - launches individual instrument windows only"""
    parser = argparse.ArgumentParser(description='LabPilot Individual Qt Instrument Windows')
    parser.add_argument('--instrument', type=str, help='Launch specific instrument window by ID')
    parser.add_argument('--type', type=str, choices=['detector', 'motor'], help='Instrument type')
    parser.add_argument('--dimensionality', type=str, help='Instrument dimensionality (0D, 1D, 2D, 3D)')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Laboratory Automation")

    # Apply professional dark theme
    LabPilotStyle.apply_dark_theme(app)

    if args.instrument:
        # Launch specific instrument window
        try:
            from authentic_qudi_windows import create_instrument_window
            from session_manager import session_manager

            # Create mock instrument data for the specific instrument
            instrument_data = {
                'id': args.instrument,
                'name': f"Instrument {args.instrument}",
                'adapter_type': 'unknown',
                'kind': args.type or 'detector',
                'dimensionality': args.dimensionality or '1D',
                'connected': True,
                'status': 'Ready',
                'tags': [],
                'data': None
            }

            instrument = DashboardInstrument(**instrument_data)
            window = create_instrument_window(instrument)

            # Register window with session manager
            window_id = f"{args.type}_{args.dimensionality}_{args.instrument}"
            session_manager.register_window(window_id, window)

            # Add session menu to window
            add_session_menu_to_window(window)

            window.show()
            window.raise_()
            window.activateWindow()

        except Exception as e:
            print(f"Failed to launch instrument window: {e}")
            sys.exit(1)
    else:
        # No main dashboard window - only individual instrument windows are supported
        print("Usage: python main.py --instrument <id> --type <detector|motor> --dimensionality <0D|1D|2D>")
        print("This Qt frontend only launches individual instrument windows.")
        print("Use the React web manager at http://localhost:3000 to manage instruments.")
        sys.exit(0)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()