"""Mock Spectrometer Adapters"""
import numpy as np
from src.labpilot_core.adapters._base import InstrumentAdapter

class MockSpectrometer(InstrumentAdapter):
    """Basic mock spectrometer (Ocean Insights)"""

    def __init__(self, name="Mock Spectrometer"):
        super().__init__(name)
        self.wavelengths = np.linspace(200, 1000, 2048)
        self.integration_time = 1.0

    def get_spectrum(self):
        """Return simulated spectrum"""
        noise = np.random.normal(0, 0.01, len(self.wavelengths))
        peak = 50 * np.exp(-((self.wavelengths - 600)**2) / 5000) + noise
        return self.wavelengths, peak

    def set_integration_time(self, ms):
        self.integration_time = ms

class MockHighResSpectrometer(InstrumentAdapter):
    """High resolution mock spectrometer (Princeton Instruments)"""

    def __init__(self, name="Mock HR Spectrometer"):
        super().__init__(name)
        self.wavelengths = np.linspace(300, 900, 4096)
        self.grating = "blazed_600"

class MockUVVISSpectrometer(InstrumentAdapter):
    """UV-VIS mock spectrometer (Agilent)"""

    def __init__(self, name="Mock UV-VIS Spectrometer"):
        super().__init__(name)
        self.wavelengths = np.linspace(190, 1100, 2048)

class MockIRSpectrometer(InstrumentAdapter):
    """IR mock spectrometer (JASCO)"""

    def __init__(self, name="Mock IR Spectrometer"):
        super().__init__(name)
        self.wavenumbers = np.linspace(400, 4000, 1800)

class MockRamanSpectrometer(InstrumentAdapter):
    """Raman mock spectrometer"""

    def __init__(self, name="Mock Raman Spectrometer"):
        super().__init__(name)
        self.wavelengths = np.linspace(400, 1000, 2048)
        self.laser_wavelength = 532  # nm

class MockFluorescenceSpectrometer(InstrumentAdapter):
    """Fluorescence mock spectrometer"""

    def __init__(self, name="Mock Fluorescence Spectrometer"):
        super().__init__(name)
        self.wavelengths = np.linspace(350, 800, 2048)
        self.excitation_wl = 405
