#!/usr/bin/env python3
"""
LabPilot Qt Frontend - Individual Instrument Windows Only
Launches specific instrument Qt windows when called by the backend API
"""


# Must be set before qtpy (pulled in by the viewer toolkit, imported lazily
# Pin the Qt binding before qtpy is imported by anything — the rule,
# and why it matters, live in labpilot/ui/qt_api.py.
import labpilot.ui.qt_api  # noqa: F401 — imported for its side effect

# isort: split

import argparse
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow

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

    # Every application-level theme from qudi-legacy's own artwork/styles
    # (https://github.com/Ulm-IQO/qudi-legacy/tree/master/artwork/styles/
    # application), imported verbatim rather than re-invented. "qdark" is
    # the default and the only one whose url(...) references point at real
    # local image assets (styles/qdark_assets/, also vendored verbatim) —
    # "dracula" and "qtdark" are qudi-legacy's own alternates, GPL-3.0
    # licensed same as the rest of that repo (qdark.qss/qdark_assets are
    # separately MIT-licensed within it, see styles/qdark_assets/LICENSE.txt).
    # dracula.qss's checkbox/radio/spinner icons reference Qt Creator's own
    # compiled qmldesigner resources (":/qmldesigner/images/...") which
    # aren't available outside Qt Creator itself — those specific icons
    # won't render under this theme, everything color/border-based still
    # applies normally.
    THEMES = {
        "qdark": {
            "label": "Qudi Dark (default)",
            "qss_file": "qdark.qss",
            "asset_token": "artwork/styles/application/qdark",
            "asset_dir": "qdark_assets",
        },
        "dracula": {
            "label": "Dracula",
            "qss_file": "dracula.qss",
            "asset_token": None,
            "asset_dir": None,
        },
        "qtdark": {
            "label": "Qt Dark (minimal)",
            "qss_file": "qtdark.qss",
            "asset_token": None,
            "asset_dir": None,
        },
    }
    DEFAULT_THEME = "qdark"
    _THEME_CONFIG_PATH = Path.home() / ".labpilot" / "config" / "ui_theme.json"

    @staticmethod
    def icon(name: str) -> "QIcon":
        """Load a real Oxygen-set icon (see styles/icons/) instead of an
        emoji glyph — falls back to a blank icon if it's missing."""
        from PyQt6.QtGui import QIcon
        path = LabPilotStyle.ICONS_DIR / f"{name}.png"
        return QIcon(str(path)) if path.exists() else QIcon()

    @staticmethod
    def get_saved_theme() -> str:
        """This machine's last-selected theme (native-desktop-only display
        preference, so a plain local file — no backend round-trip needed,
        unlike core/config/instrument_ui_prefs.py which both the React and
        Qt apps read)."""
        try:
            import json
            data = json.loads(LabPilotStyle._THEME_CONFIG_PATH.read_text())
            name = data.get("theme")
            return name if name in LabPilotStyle.THEMES else LabPilotStyle.DEFAULT_THEME
        except (OSError, ValueError):
            return LabPilotStyle.DEFAULT_THEME

    @staticmethod
    def save_theme(name: str) -> None:
        import json
        path = LabPilotStyle._THEME_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"theme": name}))

    @staticmethod
    def apply_theme(app: QApplication, theme: str = DEFAULT_THEME) -> None:
        """Apply one of qudi-legacy's own application stylesheets
        (THEMES above) to the entire application — live-switchable, not
        just at startup, since this just recomputes and re-sets the app's
        whole stylesheet."""
        if theme not in LabPilotStyle.THEMES:
            theme = LabPilotStyle.DEFAULT_THEME
        spec = LabPilotStyle.THEMES[theme]
        app.setStyle('Fusion')

        qss_path = Path(__file__).parent / "styles" / spec["qss_file"]
        if qss_path.exists():
            qss = qss_path.read_text()
            if spec["asset_token"] and spec["asset_dir"]:
                # The stylesheet's url(...) references are relative to the
                # original Qudi repo layout; point them at our vendored
                # copy instead, as an absolute path (Qt resolves
                # stylesheet urls relative to CWD otherwise, which would
                # break depending on how this app was launched).
                assets_dir = Path(__file__).parent / "styles" / spec["asset_dir"]
                qss = qss.replace(spec["asset_token"], assets_dir.as_posix())
            app.setStyleSheet(qss)
        else:
            print(f"[LabPilotStyle] {spec['qss_file']} not found at {qss_path}, using Fusion defaults")

        # A few additions no qudi theme defines, used by our own widgets —
        # kept theme-color-aware (TEXT_PRIMARY/SECONDARY/MUTED) rather than
        # hardcoded, though these constants themselves currently only track
        # qdark's own palette (see the class docstring).
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
        LabPilotStyle.save_theme(theme)
        LabPilotStyle._sync_pyqtgraph_background()

    @staticmethod
    def _sync_pyqtgraph_background() -> None:
        """Match pyqtgraph's plot background to whatever the just-applied
        theme's own QSS actually renders as a window's background —
        Qudi's own approach (gui/manager/managergui.py's on_activate:
        `pg.setConfigOption('background', bgcolor)` derived from a
        throwaway widget's live palette, not a hardcoded hex value), so
        this stays correct across every theme (qdark/dracula/qtdark)
        without hand-tuning colors per theme, and updates live on a theme
        switch through the same call path. Probed with a QMainWindow
        (what every real window in this app actually is) rather than a
        bare QWidget — dracula.qss deliberately makes plain QWidget
        transparent and only colors QMainWindow/QFrame/etc., so a bare
        QWidget would pick up nothing under that theme specifically."""
        probe = QMainWindow()
        probe.ensurePolished()
        bg_color = probe.palette().color(QPalette.ColorGroup.Normal, probe.backgroundRole())
        pg.setConfigOption('background', bg_color)

    @staticmethod
    def apply_dark_theme(app: QApplication):
        """Back-compat alias — applies the default qdark theme."""
        LabPilotStyle.apply_theme(app, LabPilotStyle.DEFAULT_THEME)

def add_view_menu_to_window(window):
    """Add a View > Theme menu for live-switching between qudi-legacy's
    application stylesheets (LabPilotStyle.THEMES) — applies instantly
    (re-sets QApplication.styleSheet()) and persists the choice for next
    launch, no restart needed."""
    try:
        from PyQt6.QtGui import QAction, QActionGroup
        from PyQt6.QtWidgets import QApplication as _QApp
        from PyQt6.QtWidgets import QMenuBar

        if not window.menuBar():
            window.setMenuBar(QMenuBar(window))
        menu_bar = window.menuBar()

        view_menu = menu_bar.addMenu("View")
        theme_menu = view_menu.addMenu("Theme")
        group = QActionGroup(window)
        group.setExclusive(True)
        current = LabPilotStyle.get_saved_theme()

        for name, spec in LabPilotStyle.THEMES.items():
            action = QAction(spec["label"], window)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.triggered.connect(
                lambda _checked, n=name: LabPilotStyle.apply_theme(_QApp.instance(), n)
            )
            group.addAction(action)
            theme_menu.addAction(action)
    except Exception as e:
        print(f"Warning: Failed to add view menu: {e}")


def add_session_menu_to_window(window):
    """Add session management menu to a window"""
    try:
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu, QMenuBar

        from labpilot.ui.desktop.session_gui import QtSessionManagerWindow
        from labpilot.ui.desktop.session_manager import session_manager

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

def _force_to_front(window: QMainWindow) -> None:
    """window.raise_()/activateWindow() alone often fail to bring a window
    forward on macOS when the process was spawned via subprocess.Popen
    (e.g. from the Qt Manager's "launch workflow" button) rather than
    double-clicked/launched by LaunchServices — the OS leaves whatever app
    was already active in front, so the new window opens silently behind
    it and looks like it "didn't open". QApplication.alert() triggers the
    dock-icon bounce (standard attention request, no extra permissions/
    dependencies needed) so the user notices even when focus doesn't move."""
    app = QApplication.instance()
    if app is not None:
        app.alert(window, 0)

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

    # Apply this machine's last-selected theme (default: qdark)
    LabPilotStyle.apply_theme(app, LabPilotStyle.get_saved_theme())

    if args.instrument:
        # Launch specific instrument window, fetching its real status from
        # the same backend the React frontend uses — never a stub/fake entry.
        try:
            from labpilot.ui.desktop.backend_client import BackendClient
            from labpilot.ui.desktop.instrument_windows import create_instrument_window
            from labpilot.ui.desktop.session_manager import session_manager

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
            add_view_menu_to_window(window)

            window.show()
            window.raise_()
            window.activateWindow()
            _force_to_front(window)

        except Exception as e:
            print(f"Failed to launch instrument window: {e}")
            sys.exit(1)
    elif args.workflow:
        # Combined native window for every instrument the workflow
        # references — see workflow_window.py.
        try:
            from labpilot.ui.desktop.backend_client import BackendClient
            from labpilot.ui.desktop.session_manager import session_manager
            from labpilot.ui.desktop.workflow_window import WorkflowWindow

            client = BackendClient(args.backend_url)
            window = WorkflowWindow(args.workflow, client)

            window_id = f"workflow_{args.workflow}"
            session_manager.register_window(window_id, window)
            add_session_menu_to_window(window)
            add_view_menu_to_window(window)

            window.show()
            window.raise_()
            window.activateWindow()
            _force_to_front(window)

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