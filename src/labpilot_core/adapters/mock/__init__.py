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
    'MockSpectrometer',
    'MockTunableSpectrometer',
    'MockCamera',
    'MockCCDCamera',
    'MockMotor',
    'MockXYStage',
    'MockPowerMeter',
    'MockPowerMeterArray',
    'MockLockInAmplifier',
    'MockSourceMeter',
    'MockTemperatureController',
    'MockOscilloscope',
]
