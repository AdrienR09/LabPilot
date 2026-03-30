"""Mock Motor Adapters"""
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockMotor(InstrumentAdapter):
    def __init__(self, name="Mock Motor"):
        super().__init__(name)
        self.position = 0.0
        self.velocity = 1.0

class MockXYStage(InstrumentAdapter):
    def __init__(self, name="Mock XY Stage"):
        super().__init__(name)
        self.x_position = 0.0
        self.y_position = 0.0

class MockXYZStage(InstrumentAdapter):
    def __init__(self, name="Mock XYZ Stage"):
        super().__init__(name)
        self.x, self.y, self.z = 0.0, 0.0, 0.0

class MockRotationalStage(InstrumentAdapter):
    def __init__(self, name="Mock Rotational Stage"):
        super().__init__(name)
        self.angle = 0.0

class MockPiezosStage(InstrumentAdapter):
    def __init__(self, name="Mock Piezo Stage"):
        super().__init__(name)
        self.x, self.y, self.z = 0.0, 0.0, 0.0
        self.voltage_range = (0, 150)

class MockFocusMotor(InstrumentAdapter):
    def __init__(self, name="Mock Focus Motor"):
        super().__init__(name)
        self.z_position = 0.0
