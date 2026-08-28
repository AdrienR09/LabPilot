#!/usr/bin/env python3
"""
LabPilot Qt Frontend - Individual Instrument Windows Only
Launches specific instrument Qt windows when called by the backend API
"""

import os
# Must be set before qtpy (pulled in by the viewer toolkit, imported lazily
# from instrument_windows.py) is imported anywhere in the process. This env
# also happens to have a standalone PyQt5 install alongside our PyQt6 —
# qtpy would otherwise auto-pick PyQt5, silently mixing two incompatible
# Qt bindings in one process (crashes). We only ever use PyQt6.
os.environ.setdefault("QT_API", "pyqt6")

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

# Set pyqtgraph configuration for professional scientific appearance.
# antialias=False: antialiasing every curve/image redraw is one of the
# biggest pyqtgraph perf costs for live-updating plots — off here to keep
# the native instrument windows responsive while polling, same as Qudi's
# own real-time traces.
pg.setConfigOptions(antialias=False, useOpenGL=False, enableExperimental=False)

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
    """Dark theme constants matching Qudi's actual qdark.qss palette (see
    styles/qdark.qss) rather than an invented one, so plot backgrounds and
    label colors set directly in code (which a global stylesheet can't
    reach) stay visually consistent with the qdark-styled native widgets."""

    # Accent (qdark's own focus/selection blue)
    PRIMARY = "#3d8ec9"
    # Used sparingly for status text only (qdark itself has no colored
    # button states — Qudi conveys status via text/border, not button fill)
    SUCCESS = "#4CAF50"
    WARNING = "#d9a441"
    DANGER = "#c0392b"

    # Background colors (qdark's actual grays)
    BG_PRIMARY = "#302F2F"
    BG_SECONDARY = "#201F1F"
    BG_TERTIARY = "#3A3939"

    # Text colors (qdark uses "silver" / muted grays)
    TEXT_PRIMARY = "#C0C0C0"   # silver
    TEXT_SECONDARY = "#b1b1b1"
    TEXT_MUTED = "#777777"

    # Border colors
    BORDER = "#3A3939"

    ICONS_DIR = Path(__file__).parent / "styles" / "icons"

    @staticmethod
    def icon(name: str) -> "QIcon":
        """Load a real Oxygen-set icon (see styles/icons/) instead of an
        emoji glyph — falls back to a blank icon if it's missing."""
        from PyQt6.QtGui import QIcon
        path = LabPilotStyle.ICONS_DIR / f"{name}.png"
        return QIcon(str(path)) if path.exists() else QIcon()

    @staticmethod
    def apply_dark_theme(app: QApplication):
        """Apply Qudi's actual qdark.qss theme (MIT-licensed, see
        styles/qdark.qss) to the entire application, instead of a
        hand-rolled approximation."""
        app.setStyle('Fusion')

        qss_path = Path(__file__).parent / "styles" / "qdark.qss"
        assets_dir = Path(__file__).parent / "styles" / "qdark_assets"
        if qss_path.exists():
            qss = qss_path.read_text()
            # The stylesheet's url(...) references are relative to
            # "artwork/styles/application/qdark" in the original Qudi repo
            # layout; point them at our copy instead, as an absolute path
            # (Qt resolves stylesheet urls relative to CWD otherwise, which
            # would break depending on how this app was launched).
            qss = qss.replace(
                "artwork/styles/application/qdark", assets_dir.as_posix()
            )
            app.setStyleSheet(qss)
        else:
            print(f"[LabPilotStyle] qdark.qss not found at {qss_path}, using Fusion defaults")

        # A few additions qdark.qss doesn't define, used by our own widgets
        app.setStyleSheet(app.styleSheet() + f"""
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
    parser.add_argument('--workflow', type=str, help='Launch combined workflow window by ID')
    parser.add_argument('--backend-url', type=str, default='http://localhost:8000',
                         help='URL of the backend API (default: http://localhost:8000)')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("LabPilot")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Laboratory Automation")

    # Apply professional dark theme
    LabPilotStyle.apply_dark_theme(app)

    if args.instrument:
        # Launch specific instrument window, fetching its real status from
        # the same backend the React frontend uses — never a stub/fake entry.
        try:
            from instrument_windows import create_instrument_window
            from backend_client import BackendClient
            from session_manager import session_manager

            client = BackendClient(args.backend_url)
            instrument_data = client.get_instrument(args.instrument)
            if instrument_data is None:
                print(f"Instrument '{args.instrument}' not found on backend {args.backend_url}")
                sys.exit(1)

            instrument = DashboardInstrument(
                id=instrument_data['id'],
                name=instrument_data['name'],
                adapter_type=instrument_data['adapter_type'],
                kind=instrument_data['kind'],
                dimensionality=instrument_data['dimensionality'],
                connected=instrument_data['connected'],
                status=instrument_data.get('status', 'idle'),
                tags=instrument_data.get('tags', []),
            )
            window = create_instrument_window(instrument, client)

            # Register window with session manager
            window_id = f"{instrument.kind}_{instrument.dimensionality}_{args.instrument}"
            session_manager.register_window(window_id, window)

            # Add session menu to window
            add_session_menu_to_window(window)

            window.show()
            window.raise_()
            window.activateWindow()

        except Exception as e:
            print(f"Failed to launch instrument window: {e}")
            sys.exit(1)
    elif args.workflow:
        # Combined native window for every instrument the workflow
        # references — see workflow_window.py.
        try:
            from workflow_window import WorkflowWindow
            from backend_client import BackendClient
            from session_manager import session_manager

            client = BackendClient(args.backend_url)
            window = WorkflowWindow(args.workflow, client)

            window_id = f"workflow_{args.workflow}"
            session_manager.register_window(window_id, window)
            add_session_menu_to_window(window)

            window.show()
            window.raise_()
            window.activateWindow()

        except Exception as e:
            print(f"Failed to launch workflow window: {e}")
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