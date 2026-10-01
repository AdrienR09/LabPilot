"""
Mock Adapters - Simulated instruments for development and testing
Organized by category to match real instrument manufacturers
"""

# Import all mock adapters to register them
from .cameras import *
from .hardware_scan import *
from .lasers import *
from .lock_in_amplifiers import *
from .microwave_sources import *
from .motors import *
from .ni_card import *
from .ocean_optics import *
from .optical_modulators import *
from .oscilloscopes import *
from .power_meters import *
from .pulse_rig import *
from .source_meters import *
from .spectrometers import *
from .temperature_controllers import *

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
    # ODMR/pulsed-sensing instruments (4) — src/labpilot/instruments/mock/{lasers,
    # microwave_sources,optical_modulators,pulse_rig}.py
    'MockLaser',
    'MockMicrowaveSource',
    'MockAOM',
    'MockPulser',
    'MockGatedCounter',
    # Hardware-timed (NI-card-style) scanning — src/labpilot/instruments/mock/hardware_scan.py
    'MockNIScanner',
    # A whole simulated NI card, chosen by model number — mock/ni_card.py
    'MockNICard',
    # A simulated Ocean Optics spectrometer, chosen by model — mock/ocean_optics.py
    'MockOceanOptics',
]
