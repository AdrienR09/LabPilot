"""Mock Camera Adapters"""
import numpy as np
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockCCDCamera(InstrumentAdapter):
    """CCD camera mock (Andor)"""
    def __init__(self, name="Mock CCD Camera"):
        super().__init__(name)
        self.resolution = (1024, 1024)
        self.temperature = -70

class MockEMCCDCamera(InstrumentAdapter):
    """Electron-multiplied CCD mock"""
    def __init__(self, name="Mock EM-CCD"):
        super().__init__(name)
        self.resolution = (512, 512)
        self.em_gain = 1

class MockScientificCamera(InstrumentAdapter):
    """Scientific CMOS camera mock (Hamamatsu)"""
    def __init__(self, name="Mock Scientific Camera"):
        super().__init__(name)
        self.resolution = (2048, 2048)
        self.fps = 30

class MockHighSpeedCamera(InstrumentAdapter):
    """High-speed camera mock"""
    def __init__(self, name="Mock HS Camera"):
        super().__init__(name)
        self.resolution = (640, 480)
        self.fps_max = 10000

class MockThermalCamera(InstrumentAdapter):
    """Thermal/IR camera mock"""
    def __init__(self, name="Mock Thermal Camera"):
        super().__init__(name)
        self.resolution = (640, 480)
        self.temperature_range = (-40, 120)

class MockLineScanCamera(InstrumentAdapter):
    """Line scan camera mock"""
    def __init__(self, name="Mock Line Scan"):
        super().__init__(name)
        self.pixels = 4096
        self.scan_rate = 50000
