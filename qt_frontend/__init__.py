"""
LabPilot Qt Frontend - Professional PyQt6 application for lab automation
"""

__version__ = "2.0.0"
__author__ = "LabPilot Team"

from .main import DashboardInstrument, InstrumentKind, LabPilotStyle

__all__ = [
    "DashboardInstrument",
    "InstrumentKind",
    "LabPilotStyle",
]
