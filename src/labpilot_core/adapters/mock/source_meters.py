"""Mock Source Meter Adapters"""
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockSourceMeter(InstrumentAdapter):
    def __init__(self, name="Mock Source Meter"):
        super().__init__(name)
        self.voltage = 0.0
        self.current = 0.0

class MockHighVoltageSource(InstrumentAdapter):
    def __init__(self, name="Mock HV Source"):
        super().__init__(name)
        self.voltage_range = (0, 1000)

class MockCurrentSource(InstrumentAdapter):
    def __init__(self, name="Mock Current Source"):
        super().__init__(name)
        self.current_range = (-1, 1)

class MockDualSourceMeter(InstrumentAdapter):
    def __init__(self, name="Mock Dual Source"):
        super().__init__(name)
        self.channels = 2
