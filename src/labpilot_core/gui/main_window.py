"""Main GUI window for LabPilot Core.

Provides unified Manager tab with:
- Block diagram for instruments and interfaces
- Real-time data visualization and plotting
- Device management and control
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PyQt6.QtCore import QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labpilot_core import Session
from labpilot_core.gui.tabs.manager_tab import ManagerTab
from labpilot_core.gui.chat_widget import ChatWidget


class AsyncRunner(QRunnable):
    """Helper to run async code in Qt thread pool."""

    def __init__(self, coro):
        super().__init__()
        self.coro = coro
        self.loop = None

    def run(self):
        """Execute async coroutine."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.coro)
        finally:
            self.loop.close()


class LabPilotGUI(QMainWindow):
    """Main GUI window for LabPilot Core.

    Provides interface for managing instruments and running scans using an
    async Session loaded from TOML config.

    Args:
        config_path: Path to lab configuration TOML file
        parent: Parent widget (optional)
    """

    # Signals
    session_loaded = pyqtSignal(object)  # Session object
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(
        self,
        config_path: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.config_path = Path(config_path) if config_path else None
        self.session: Session | None = None
        self.thread_pool = QThreadPool.globalInstance()

        self._setup_ui()
        self._connect_signals()

        # Load session if config provided
        if self.config_path and self.config_path.exists():
            self._load_session()

    def _setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("LabPilot Core - Instrument & Scan Manager")
        self.setGeometry(100, 100, 1200, 800)

        # Central widget with tabs
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self.manager_tab = ManagerTab()
        self.chat_tab = ChatWidget()

        self.tabs.addTab(self.manager_tab, "🎛️ Manager")
        self.tabs.addTab(self.chat_tab, "🤖 AI Assistant")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Styling
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #2b2b2b;
            }
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4a9eff;
            }
            QStatusBar {
                background-color: #1e1e1e;
                color: #b0b0b0;
            }
        """
        )

    def _connect_signals(self):
        """Connect internal signals."""
        self.session_loaded.connect(self._on_session_loaded)
        self.error_occurred.connect(self._on_error)

    def _load_session(self):
        """Load session from config file asynchronously."""
        self.status_bar.showMessage(f"Loading session from {self.config_path}...")

        async def load():
            try:
                session = await Session.load(str(self.config_path))
                self.session_loaded.emit(session)
            except Exception as e:
                self.error_occurred.emit(f"Failed to load session: {e}")

        runner = AsyncRunner(load())
        self.thread_pool.start(runner)

    @pyqtSlot(object)
    def _on_session_loaded(self, session: Session):
        """Handle session loaded."""
        self.session = session
        # Manager tab is standalone and self-contained
        self.status_bar.showMessage(
            f"✓ Session loaded: {len(session.devices)} devices"
        )

    @pyqtSlot(str)
    def _on_error(self, message: str):
        """Handle error."""
        self.status_bar.showMessage(f"✗ Error: {message}")

    def closeEvent(self, event):
        """Clean up on window close."""
        if self.session:
            # Disconnect all devices
            async def cleanup():
                for device in self.session.devices.values():
                    try:
                        await device.disconnect()
                    except Exception:
                        pass

            runner = AsyncRunner(cleanup())
            self.thread_pool.start(runner)

        event.accept()


def main():
    """Launch the LabPilot GUI application."""
    import argparse

    parser = argparse.ArgumentParser(description="LabPilot Core GUI")
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to lab configuration TOML file",
        default=None,
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot Core")
    app.setOrganizationName("LabPilot")

    window = LabPilotGUI(config_path=args.config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
