"""LabPilot's user interfaces: the native Qt desktop app, and the web UI.

Importing anything under here pins the Qt binding first — see `qt_api.py`
for why that has to happen before `qtpy` is imported by anything.
"""

from labpilot.ui import qt_api  # imported for its side effect: sets QT_API

__all__ = ["qt_api"]
