"""Compatibility shim.

The native instrument windows used to be defined directly in this file
(seven hand-written QMainWindow subclasses). They're now a generic,
component-based, config-driven system — see instrument_window.py (the
InstrumentWindow class + create_instrument_window factory) and the
components/ package. This module just re-exports the factory under its
original name so existing call sites (main.py, session_manager.py) don't
need to change their import.
"""

from labpilot.ui.desktop.instrument_window import create_instrument_window

__all__ = ["create_instrument_window"]
