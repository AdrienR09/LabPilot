"""
Mock Adapters - Simulated instruments for development and testing
Organized by category to match real instrument manufacturers
"""

# Import all mock adapters to register them
from .spectrometers import *
from .cameras import *
from .motors import *
from .power_meters import *
from .lock_in_amplifiers import *
from .source_meters import *
from .temperature_controllers import *
from .oscilloscopes import *

__all__ = [
    # Spectrometers (6)
    'MockSpectrometer',
    'MockHighResSpectrometer',
    'MockUVVISSpectrometer',
    'MockIRSpectrometer',
    'MockRamanSpectrometer',
    'MockFluorescenceSpectrometer',
    # Cameras (6)
    'MockCCDCamera',
    'MockEMCCDCamera',
    'MockScientificCamera',
    'MockHighSpeedCamera',
    'MockThermalCamera',
    'MockLineScanCamera',
    # Motors (6)
    'MockMotor',
    'MockXYStage',
    'MockXYZStage',
    'MockRotationalStage',
    'MockPiezoStage',
    'MockFocusMotor',
    # Power Meters (4)
    'MockPowerMeter',
    'MockUVPowerMeter',
    'MockIRPowerMeter',
    'MockArrayPowerMeter',
    # Lock-in Amplifiers (3)
    'MockLockInAmplifier',
    'MockDualChannelLockin',
    'MockMultiPhaseLocking',
    # Source Meters (4)
    'MockSourceMeter',
    'MockHighVoltageSource',
    'MockCurrentSource',
    'MockDualSourceMeter',
    # Temperature Controllers (4)
    'MockTemperatureController',
    'MockHeater',
    'MockCryostat',
    'MockThermoElectricCooler',
    # Oscilloscopes (3)
    'MockOscilloscope',
    'MockUSBOscilloscope',
    'MockHighSpeedOscilloscope',
]
