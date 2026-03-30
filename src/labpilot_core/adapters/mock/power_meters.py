"""Mock Power Meter Adapters"""
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockPowerMeter(InstrumentAdapter):
    def __init__(self, name="Mock Power Meter"):
        super().__init__(name)
        self.power = 1.0

class MockUVPowerMeter(InstrumentAdapter):
    def __init__(self, name="Mock UV Power Meter"):
        super().__init__(name)
        self.wavelength_range = (200, 400)

class MockIRPowerMeter(InstrumentAdapter):
    def __init__(self, name="Mock IR Power Meter"):
        super().__init__(name)
        self.wavelength_range = (700, 10000)

class MockArrayPowerMeter(InstrumentAdapter):
    def __init__(self, name="Mock Array Power Meter"):
        super().__init__(name)
        self.channels = 16
