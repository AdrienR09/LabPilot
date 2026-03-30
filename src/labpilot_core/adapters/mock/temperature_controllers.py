"""Mock Temperature Controller Adapters"""
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockTemperatureController(InstrumentAdapter):
    def __init__(self, name="Mock Temperature Controller"):
        super().__init__(name)
        self.setpoint = 300
        self.temperature = 300

class MockCryostat(InstrumentAdapter):
    def __init__(self, name="Mock Cryostat"):
        super().__init__(name)
        self.temperature_range = (4, 300)

class MockThermoElectricCooler(InstrumentAdapter):
    def __init__(self, name="Mock TEC"):
        super().__init__(name)
        self.temperature_range = (-40, 80)

class MockHeater(InstrumentAdapter):
    def __init__(self, name="Mock Heater"):
        super().__init__(name)
        self.max_temperature = 500
