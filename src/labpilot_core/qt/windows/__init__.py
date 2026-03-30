"""Qt window implementations for LabPilot.

This package contains specialized Qt window types for different data visualization needs:

- SpectrumWindow: Real-time spectroscopy plotting with peak finding
- ImageWindow: 2D image display with histogram and ROI
- WaveformWindow: Oscilloscope-like time-series display
- VolumeWindow: 3D volume rendering (future implementation)
- CompositeWindow: Multi-widget layouts for complex panels

All windows inherit from LabPilotWindow which provides:
- EventBus integration for live data updates
- Thread-safe communication between asyncio and Qt
- Consistent styling and behavior
- Window lifecycle management
"""

from __future__ import annotations

__all__ = [
    "CompositeWindow",
    "ImageWindow",
    "LabPilotWindow",
    "SpectrumWindow",
    "WaveformWindow",
]

# Import guard for Qt components
try:
    from labpilot_core.qt.windows._base import LabPilotWindow
    from labpilot_core.qt.windows.composite import CompositeWindow
    from labpilot_core.qt.windows.image import ImageWindow
    from labpilot_core.qt.windows.spectrum import SpectrumWindow
    from labpilot_core.qt.windows.waveform import WaveformWindow
except ImportError:
    # Qt not available
    LabPilotWindow = None
    SpectrumWindow = None
    ImageWindow = None
    WaveformWindow = None
    CompositeWindow = None
