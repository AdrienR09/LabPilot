"""LabPilot Core GUI - Optional graphical interface for experiment management.

This module provides a PyQt6-based GUI for managing instruments and running scans.
It integrates with labpilot_core's async Session and event system.

Usage:
    >>> from labpilot_core.gui import LabPilotGUI
    >>> import sys
    >>> from PyQt6.QtWidgets import QApplication
    >>>
    >>> app = QApplication(sys.argv)
    >>> gui = LabPilotGUI(config_path="lab_config.toml")
    >>> gui.show()
    >>> sys.exit(app.exec())
"""

from __future__ import annotations

__all__ = ["LabPilotGUI"]

try:
    from labpilot_core.gui.main_window import LabPilotGUI
except ImportError as e:
    raise ImportError(
        "GUI dependencies not installed. Install with: pip install labpilot-core[gui]"
    ) from e
