#!/usr/bin/env python3
"""
LabPilot Qt Material Manager - Main Entry Point
Launches the complete Qt Material Design manager interface
"""

import sys
import argparse
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QFont, QPainter, QColor
import qdarkstyle

# Import the main manager window and API client
from .qt_material_manager import LabPilotMaterialManager, PageType, SessionState
from .api_client import create_api_client

class LabPilotSplashScreen(QSplashScreen):
    """Custom splash screen for LabPilot"""

    def __init__(self):
        # Create a simple splash screen pixmap
        pixmap = QPixmap(400, 300)
        pixmap.fill(QColor("#1976d2"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw title
        font = QFont("Arial", 24, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "LabPilot\nManager")

        # Draw version
        font = QFont("Arial", 12)
        painter.setFont(font)
        painter.setPen(QColor("#bbdefb"))
        painter.drawText(20, 270, "Version 2.0.0 - Qt Material Design")

        painter.end()

        super().__init__(pixmap)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)

    def showMessage(self, message: str):
        """Show loading message"""
        super().showMessage(
            message,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            QColor("white")
        )
        QApplication.processEvents()

def check_dependencies():
    """Check if all required dependencies are available"""
    missing_deps = []

    try:
        import PyQt6
    except ImportError:
        missing_deps.append("PyQt6")

    try:
        import qt_material
    except ImportError:
        missing_deps.append("qt-material")

    try:
        import pyqtgraph
    except ImportError:
        missing_deps.append("pyqtgraph")

    try:
        import requests
    except ImportError:
        missing_deps.append("requests")

    return missing_deps

def setup_application() -> QApplication:
    """Setup Qt application with proper configuration"""
    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot Manager")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("Laboratory Automation")
    app.setOrganizationDomain("labpilot.org")

    # Note: High DPI scaling is now handled automatically in PyQt6

    return app

def show_dependency_error(missing_deps: list):
    """Show error dialog for missing dependencies"""
    app = QApplication(sys.argv)
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("Missing Dependencies")
    msg.setText("Some required dependencies are missing:")
    msg.setDetailedText(f"Missing packages:\n" + "\n".join(f"- {dep}" for dep in missing_deps))
    msg.setInformativeText("Please install the missing packages and try again.")
    msg.exec()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="LabPilot Qt Material Manager - Complete laboratory automation interface"
    )

    parser.add_argument(
        "--light-mode",
        action="store_true",
        help="Use light mode instead of dark mode"
    )

    parser.add_argument(
        "--backend-url",
        type=str,
        default="http://localhost:8000",
        help="Backend server URL"
    )

    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Skip splash screen"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    parser.add_argument(
        "--page",
        type=str,
        choices=["dashboard", "devices", "workflows", "flow", "ai", "data", "settings"],
        help="Start on specific page"
    )

    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_arguments()

    # Check dependencies first
    missing_deps = check_dependencies()
    if missing_deps:
        show_dependency_error(missing_deps)
        return 1

    # Setup application
    app = setup_application()

    # Show splash screen
    splash = None
    if not args.no_splash:
        splash = LabPilotSplashScreen()
        splash.show()
        splash.showMessage("Initializing LabPilot Manager...")

    try:
        # Create API client
        if splash:
            splash.showMessage("Connecting to backend...")

        api_client = create_api_client(args.backend_url)

        # Create main window
        if splash:
            splash.showMessage("Setting up user interface...")

        manager = LabPilotMaterialManager()

        # Set API client
        manager.api_client = api_client
        for page in manager.pages.values():
            if hasattr(page, 'set_api_client'):
                page.set_api_client(api_client)

        # Apply theme
        if splash:
            splash.showMessage("Applying dark theme...")

        # Set theme preference (dark mode by default, light if specified)
        manager.preferences.dark_mode = not args.light_mode
        manager.apply_dark_theme()

        # Connect API signals
        api_client.connection_status_changed.connect(
            lambda connected: manager.sidebar.update_session_info(
                SessionState(
                    connected=connected,
                    session_id=manager.session.session_id,
                    device_count=manager.session.device_count,
                    ai_available=manager.session.ai_available,
                    backend_url=manager.session.backend_url
                )
            )
        )

        api_client.session_status_updated.connect(
            lambda data: manager.sidebar.update_session_info(
                SessionState(
                    connected=data.get("connected", False),
                    session_id=data.get("session_id", ""),
                    device_count=data.get("device_count", 0),
                    ai_available=data.get("ai_available", False),
                    backend_url=manager.session.backend_url
                )
            )
        )

        api_client.error_occurred.connect(
            lambda error: QMessageBox.warning(manager, "API Error", error)
        )

        # Start on specific page if requested
        if args.page:
            try:
                page_type = PageType(args.page)
                manager.switch_page(page_type.value)
            except ValueError:
                print(f"Warning: Unknown page '{args.page}', starting on dashboard")

        # Hide splash and show main window
        if splash:
            splash.showMessage("Ready!")
            QTimer.singleShot(1000, splash.close)

        QTimer.singleShot(1500 if splash else 0, manager.show)

        # Debug information
        if args.debug:
            print(f"LabPilot Manager started")
            print(f"Dark mode: {manager.preferences.dark_mode}")
            print(f"Backend URL: {args.backend_url}")
            print(f"Using QDarkStyleSheet theme")

        return app.exec()

    except Exception as e:
        if splash:
            splash.close()

        # Show error dialog
        error_msg = QMessageBox()
        error_msg.setIcon(QMessageBox.Icon.Critical)
        error_msg.setWindowTitle("Startup Error")
        error_msg.setText("Failed to start LabPilot Manager")
        error_msg.setDetailedText(str(e))
        error_msg.exec()

        return 1

def run_manager():
    """Alternative entry point for programmatic use"""
    return main()

if __name__ == "__main__":
    sys.exit(main())