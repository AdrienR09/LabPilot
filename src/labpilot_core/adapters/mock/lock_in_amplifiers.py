"""Mock Lock-in Amplifier Adapters"""
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockLockInAmplifier(InstrumentAdapter):
    def __init__(self, name="Mock Lock-in Amplifier"):
        super().__init__(name)
        self.frequency = 1000
        self.phase = 0
        self.sensitivity = 100e-9

class MockDualChannelLockin(InstrumentAdapter):
    def __init__(self, name="Mock Dual-Channel Lockin"):
        super().__init__(name)
        self.frequency = 1000
        self.channels = 2

class MockMultiPhaseLocking(InstrumentAdapter):
    def __init__(self, name="Mock Multi-Phase Lockin"):
        super().__init__(name)
        self.phases = [0, 90, 180, 270]
