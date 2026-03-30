"""LabPilot Qt visualization layer.

This package provides the Qt DSL and window system for AI-generated UIs.

Components:
- dsl: The 15-function DSL that AI uses to generate Qt windows
- bridge: Thread-safe Qt application management
- factory: Routes DSL specs to appropriate window types
- windows: Specialized window implementations (spectrum, image, waveform, etc.)
- manager: Window lifecycle and REST endpoint management

Usage (AI-generated code):
    >>> from labpilot_core.qt.dsl import *
    >>> w = window("My Panel", layout="vertical")
    >>> w.add(spectrum_plot(source="spec.intensities", show_peak=True))
    >>> show(w)  # Spawns Qt window

Usage (programmatic):
    >>> from labpilot_core.qt.bridge import QtBridge
    >>> bridge = QtBridge()
    >>> bridge.start()
    >>> bridge.open_window("my_window", window_spec)
"""

from __future__ import annotations

__all__ = ["QtBridge"]

# Import guard to prevent loading Qt in async code
try:
    from labpilot_core.qt.bridge import QtBridge
except ImportError:
    # QtBridge not available (PyQt6 not installed)
    QtBridge = None
