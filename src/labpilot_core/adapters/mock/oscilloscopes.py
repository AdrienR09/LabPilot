"""Mock Oscilloscope Adapters"""
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockOscilloscope(InstrumentAdapter):
    def __init__(self, name="Mock Oscilloscope"):
        super().__init__(name)
        self.channels = 4
        self.bandwidth = 1e9

class MockUSBOscilloscope(InstrumentAdapter):
    def __init__(self, name="Mock USB Oscilloscope"):
        super().__init__(name)
        self.channels = 2
        self.bandwidth = 100e6

class MockHighSpeedOscilloscope(InstrumentAdapter):
    def __init__(self, name="Mock HS Oscilloscope"):
        super().__init__(name)
        self.channels = 8
        self.bandwidth = 10e9
        self.sample_rate = 50e9
