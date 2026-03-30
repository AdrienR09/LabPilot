"""
LabPilot Qt Session Management
Handles saving and loading of Qt window configurations, positions, and settings
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from PyQt6.QtCore import QSettings, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QCloseEvent

@dataclass
class WindowState:
    """State of a single Qt window"""
    instrument_id: str
    instrument_type: str
    dimensionality: str
    window_class: str
    geometry: tuple  # (x, y, width, height)
    is_visible: bool
    is_maximized: bool
    dock_states: Dict[str, Any] = None  # Dock widget states
    settings: Dict[str, Any] = None      # Window-specific settings

@dataclass
class SessionData:
    """Complete session state"""
    session_name: str
    created_at: str
    modified_at: str
    description: str
    windows: List[WindowState]
    global_settings: Dict[str, Any] = None

class QtSessionManager(QObject):
    """
    Qt Session Manager for LabPilot
    Handles saving/loading of window sessions with positions and settings
    """

    session_saved = pyqtSignal(str)  # session_name
    session_loaded = pyqtSignal(str)  # session_name

    def __init__(self):
        super().__init__()
        self.sessions_dir = Path.home() / ".labpilot" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Track active windows
        self.active_windows: Dict[str, Any] = {}  # window_id -> window_object
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save_current_session)

        # Settings
        self.settings = QSettings("LabPilot", "QtSession")

    def register_window(self, window_id: str, window: Any):
        """Register a window for session management"""
        self.active_windows[window_id] = window

        # Connect to window close event to update session
        if hasattr(window, 'closeEvent'):
            # Store original close event
            window._original_close_event = window.closeEvent

            # Override with session-aware close event
            def session_close_event(event: QCloseEvent):
                self.unregister_window(window_id)
                window._original_close_event(event)

            window.closeEvent = session_close_event

    def unregister_window(self, window_id: str):
        """Unregister a window from session management"""
        if window_id in self.active_windows:
            del self.active_windows[window_id]

    def get_window_state(self, window_id: str) -> Optional[WindowState]:
        """Get current state of a window"""
        if window_id not in self.active_windows:
            return None

        window = self.active_windows[window_id]

        # Extract instrument info from window
        instrument_id = getattr(window.instrument, 'id', window_id)
        instrument_type = getattr(window.instrument, 'kind', 'unknown')
        dimensionality = getattr(window.instrument, 'dimensionality', '0D')

        # Get geometry
        geometry = window.geometry()
        geometry_tuple = (geometry.x(), geometry.y(), geometry.width(), geometry.height())

        # Get dock states (for qudi windows)
        dock_states = {}
        for dock in window.findChildren(window.__class__.__bases__[0]):
            if hasattr(dock, 'objectName') and dock.objectName():
                dock_states[dock.objectName()] = {
                    'visible': dock.isVisible(),
                    'floating': dock.isFloating(),
                    'area': int(window.dockWidgetArea(dock)) if not dock.isFloating() else None
                }

        # Get window-specific settings
        settings = {}
        if hasattr(window, 'get_session_settings'):
            settings = window.get_session_settings()

        return WindowState(
            instrument_id=instrument_id,
            instrument_type=instrument_type,
            dimensionality=dimensionality,
            window_class=window.__class__.__name__,
            geometry=geometry_tuple,
            is_visible=window.isVisible(),
            is_maximized=window.isMaximized(),
            dock_states=dock_states,
            settings=settings
        )

    def save_session(self, session_name: str, description: str = "") -> bool:
        """Save current session to file"""
        try:
            # Collect states from all active windows
            window_states = []
            for window_id in self.active_windows:
                state = self.get_window_state(window_id)
                if state:
                    window_states.append(state)

            # Create session data
            now = datetime.now().isoformat()
            session_data = SessionData(
                session_name=session_name,
                created_at=now,
                modified_at=now,
                description=description,
                windows=window_states,
                global_settings=self.get_global_settings()
            )

            # Save to JSON file
            session_file = self.sessions_dir / f"{session_name}.json"
            with open(session_file, 'w') as f:
                # Convert dataclasses to dict
                data_dict = asdict(session_data)
                json.dump(data_dict, f, indent=2)

            # Update settings
            self.settings.setValue("last_session", session_name)

            self.session_saved.emit(session_name)
            print(f"✅ Session '{session_name}' saved successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to save session '{session_name}': {e}")
            return False

    def load_session(self, session_name: str) -> bool:
        """Load session from file"""
        try:
            session_file = self.sessions_dir / f"{session_name}.json"
            if not session_file.exists():
                print(f"❌ Session file not found: {session_file}")
                return False

            # Load session data
            with open(session_file, 'r') as f:
                data_dict = json.load(f)

            # Close existing windows
            self.close_all_windows()

            # Restore windows
            for window_data in data_dict['windows']:
                self.restore_window(window_data)

            # Restore global settings
            if 'global_settings' in data_dict:
                self.apply_global_settings(data_dict['global_settings'])

            # Update modified time
            data_dict['modified_at'] = datetime.now().isoformat()
            with open(session_file, 'w') as f:
                json.dump(data_dict, f, indent=2)

            self.settings.setValue("last_session", session_name)

            self.session_loaded.emit(session_name)
            print(f"✅ Session '{session_name}' loaded successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to load session '{session_name}': {e}")
            return False

    def restore_window(self, window_data: Dict[str, Any]):
        """Restore a single window from saved state"""
        try:
            # Import here to avoid circular imports
            from main import DashboardInstrument
            from .instrument_windows import create_instrument_window

            # Create instrument data
            instrument_data = {
                'id': window_data['instrument_id'],
                'name': f"Instrument {window_data['instrument_id']}",
                'adapter_type': 'restored_session',
                'kind': window_data['instrument_type'],
                'dimensionality': window_data['dimensionality'],
                'connected': True,
                'status': 'Ready',
                'tags': ['SessionRestore'],
                'data': None
            }

            instrument = DashboardInstrument(**instrument_data)
            window = create_instrument_window(instrument)

            # Restore geometry
            x, y, width, height = window_data['geometry']
            window.setGeometry(x, y, width, height)

            if window_data['is_maximized']:
                window.showMaximized()
            elif window_data['is_visible']:
                window.show()

            # Restore dock states
            if window_data.get('dock_states'):
                for dock_name, dock_state in window_data['dock_states'].items():
                    dock = window.findChild(window.__class__.__bases__[0], dock_name)
                    if dock:
                        dock.setVisible(dock_state['visible'])
                        if dock_state['floating']:
                            dock.setFloating(True)
                        elif dock_state['area'] is not None:
                            window.addDockWidget(dock_state['area'], dock)

            # Restore window-specific settings
            if window_data.get('settings') and hasattr(window, 'apply_session_settings'):
                window.apply_session_settings(window_data['settings'])

            # Register for session management
            window_id = f"{window_data['instrument_type']}_{window_data['dimensionality']}_{window_data['instrument_id']}"
            self.register_window(window_id, window)

        except Exception as e:
            print(f"❌ Failed to restore window {window_data['instrument_id']}: {e}")

    def close_all_windows(self):
        """Close all active windows"""
        windows_to_close = list(self.active_windows.values())
        for window in windows_to_close:
            window.close()
        self.active_windows.clear()

    def get_available_sessions(self) -> List[str]:
        """Get list of available session names"""
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            sessions.append(session_file.stem)
        return sorted(sessions)

    def get_session_info(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Get session information without loading it"""
        try:
            session_file = self.sessions_dir / f"{session_name}.json"
            if not session_file.exists():
                return None

            with open(session_file, 'r') as f:
                data = json.load(f)

            return {
                'name': data['session_name'],
                'created_at': data['created_at'],
                'modified_at': data['modified_at'],
                'description': data.get('description', ''),
                'window_count': len(data['windows']),
                'instruments': [w['instrument_id'] for w in data['windows']]
            }
        except Exception as e:
            print(f"❌ Failed to read session info for '{session_name}': {e}")
            return None

    def delete_session(self, session_name: str) -> bool:
        """Delete a saved session"""
        try:
            session_file = self.sessions_dir / f"{session_name}.json"
            if session_file.exists():
                session_file.unlink()
                print(f"✅ Session '{session_name}' deleted")
                return True
            return False
        except Exception as e:
            print(f"❌ Failed to delete session '{session_name}': {e}")
            return False

    def get_global_settings(self) -> Dict[str, Any]:
        """Get global application settings"""
        return {
            'theme': 'dark',
            'auto_save_interval': self.settings.value("auto_save_interval", 300),  # 5 minutes
            'window_animation': self.settings.value("window_animation", True),
        }

    def apply_global_settings(self, settings: Dict[str, Any]):
        """Apply global settings"""
        if 'auto_save_interval' in settings:
            self.settings.setValue("auto_save_interval", settings['auto_save_interval'])
        if 'window_animation' in settings:
            self.settings.setValue("window_animation", settings['window_animation'])

    def start_auto_save(self, interval_seconds: int = 300):
        """Start automatic session saving"""
        self.auto_save_timer.start(interval_seconds * 1000)  # Convert to ms

    def stop_auto_save(self):
        """Stop automatic session saving"""
        self.auto_save_timer.stop()

    def auto_save_current_session(self):
        """Auto-save current session"""
        if len(self.active_windows) > 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_name = f"autosave_{timestamp}"
            self.save_session(session_name, "Automatic save")

# Global session manager instance
session_manager = QtSessionManager()