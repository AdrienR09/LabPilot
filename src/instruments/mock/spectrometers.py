"""Mock Spectrometer Adapters for LabPilot testing and development."""

from typing import Any
import numpy as np
from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema


class MockSpectrometer(AdapterBase):
    """Basic mock spectrometer (Ocean Insights USB2000 simulation)."""

    def __init__(self, name: str = "mock_spectrometer") -> None:
        super().__init__()
        self._name = name
        self.wavelengths = np.linspace(200, 1000, 2048)
        self.integration_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
            settable={"integration_time_ms": "float64"},
            units={"wavelengths": "nm", "intensities": "counts"},
            limits={"integration_time_ms": (1.0, 60000.0)},
            trigger_modes=["software"],
            tags=["Mock", "Spectrometer", "Visible"],
        )

    def _connect_sync(self) -> None:
        """Simulate connection."""
        pass

    def _disconnect_sync(self) -> None:
        """Simulate disconnection."""
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated spectrum with peak."""
        # Generate realistic spectrum with Gaussian peak
        noise = np.random.normal(0, 10, len(self.wavelengths))
        peak = 5000 * np.exp(-((self.wavelengths - 650) ** 2) / 5000) + noise
        peak = np.maximum(peak, 0)  # No negative counts
        return {
            "wavelengths": self.wavelengths.tolist(),
            "intensities": peak.tolist(),
        }

    async def set_integration_time_ms(self, value: float) -> None:
        self.integration_time = float(value)


class MockHighResSpectrometer(AdapterBase):
    """High resolution mock spectrometer (Princeton Instruments simulation)."""

    def __init__(self, name: str = "mock_hi_res_spectrometer") -> None:
        super().__init__()
        self._name = name
        self.wavelengths = np.linspace(300, 900, 4096)
        self.grating = "blazed_600"
        self.integration_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
            settable={"integration_time_ms": "float64", "grating": "str"},
            units={"wavelengths": "nm", "intensities": "counts"},
            limits={"integration_time_ms": (1.0, 60000.0)},
            tags=["Mock", "Spectrometer", "HighResolution", "Princeton"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """High-resolution spectrum with sharp peaks."""
        noise = np.random.normal(0, 5, len(self.wavelengths))
        # Multiple peaks to simulate Rydberg lines
        peak1 = 8000 * np.exp(-((self.wavelengths - 486.1) ** 2) / 100)
        peak2 = 6000 * np.exp(-((self.wavelengths - 656.3) ** 2) / 100)
        intensities = (peak1 + peak2 + noise).tolist()
        return {
            "wavelengths": self.wavelengths.tolist(),
            "intensities": intensities,
        }

    async def set_integration_time_ms(self, value: float) -> None:
        self.integration_time = float(value)

    async def set_grating(self, value: str) -> None:
        self.grating = str(value)


class MockUVVISSpectrometer(AdapterBase):
    """UV-VIS mock spectrometer (Agilent simulation)."""

    def __init__(self, name: str = "mock_uv_vis_spectrometer") -> None:
        super().__init__()
        self._name = name
        self.wavelengths = np.linspace(190, 1100, 2048)
        self.integration_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"wavelengths": "ndarray1d", "absorbance": "ndarray1d"},
            settable={"integration_time_ms": "float64"},
            units={"wavelengths": "nm", "absorbance": "AU"},
            limits={"integration_time_ms": (1.0, 60000.0)},
            tags=["Mock", "Spectrometer", "UV-VIS"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulated UV-VIS absorption spectrum."""
        noise = np.random.normal(0, 0.005, len(self.wavelengths))
        # Absorption peak typical of aromatic compounds
        absorbance = 2.5 * np.exp(-((self.wavelengths - 280) ** 2) / 2000) + noise
        absorbance = np.clip(absorbance, 0, 3)  # Realistic range
        return {
            "wavelengths": self.wavelengths.tolist(),
            "absorbance": absorbance.tolist(),
        }

    async def set_integration_time_ms(self, value: float) -> None:
        self.integration_time = float(value)


class MockIRSpectrometer(AdapterBase):
    """IR mock spectrometer (JASCO simulation)."""

    def __init__(self, name: str = "mock_ir_spectrometer") -> None:
        super().__init__()
        self._name = name
        self.wavenumbers = np.linspace(400, 4000, 1800)
        self.integration_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"wavenumbers": "ndarray1d", "transmittance": "ndarray1d"},
            settable={"integration_time_ms": "float64"},
            units={"wavenumbers": "cm^-1", "transmittance": "%"},
            limits={"integration_time_ms": (1.0, 60000.0)},
            tags=["Mock", "Spectrometer", "IR"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulated IR transmittance spectrum."""
        noise = np.random.normal(0, 1, len(self.wavenumbers))
        # Typical C-H and O-H stretches
        peak_ch = 30 * np.exp(-((self.wavenumbers - 2950) ** 2) / 20000)
        peak_oh = 40 * np.exp(-((self.wavenumbers - 3300) ** 2) / 30000)
        transmittance = 100 - (peak_ch + peak_oh + noise)
        transmittance = np.clip(transmittance, 0, 100)
        return {
            "wavenumbers": self.wavenumbers.tolist(),
            "transmittance": transmittance.tolist(),
        }

    async def set_integration_time_ms(self, value: float) -> None:
        self.integration_time = float(value)


class MockRamanSpectrometer(AdapterBase):
    """Raman mock spectrometer simulation."""

    def __init__(self, name: str = "mock_raman_spectrometer") -> None:
        super().__init__()
        self._name = name
        self.wavelengths = np.linspace(100, 3200, 2048)
        self.laser_wavelength = 532  # nm
        self.integration_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"shift": "ndarray1d", "intensity": "ndarray1d"},
            settable={"integration_time_ms": "float64", "laser_wavelength": "float64"},
            units={"shift": "cm^-1", "intensity": "counts"},
            limits={"integration_time_ms": (1.0, 60000.0)},
            tags=["Mock", "Spectrometer", "Raman"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulated Raman spectrum with D and G bands."""
        noise = np.random.normal(0, 50, len(self.wavelengths))
        # D and G bands (carbon materials)
        d_band = 3000 * np.exp(-((self.wavelengths - 1350) ** 2) / 50000)
        g_band = 5000 * np.exp(-((self.wavelengths - 1600) ** 2) / 50000)
        intensity = (d_band + g_band + noise).tolist()
        return {
            "shift": self.wavelengths.tolist(),
            "intensity": intensity,
        }

    async def set_integration_time_ms(self, value: float) -> None:
        self.integration_time = float(value)

    async def set_laser_wavelength(self, value: float) -> None:
        self.laser_wavelength = float(value)


class MockFluorescenceSpectrometer(AdapterBase):
    """Fluorescence mock spectrometer simulation."""

    def __init__(self, name: str = "mock_fluorescence_spectrometer") -> None:
        super().__init__()
        self._name = name
        self.wavelengths = np.linspace(350, 800, 2048)
        self.excitation_wl = 405  # nm
        self.integration_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"wavelengths": "ndarray1d", "fluorescence": "ndarray1d"},
            settable={
                "integration_time_ms": "float64",
                "excitation_wavelength": "float64",
            },
            units={"wavelengths": "nm", "fluorescence": "counts"},
            limits={"integration_time_ms": (1.0, 60000.0)},
            tags=["Mock", "Spectrometer", "Fluorescence"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulated fluorescence emission spectrum."""
        noise = np.random.normal(0, 100, len(self.wavelengths))
        # Decay from 405nm laser excitation
        baseline = 100
        fluorescence = (
            baseline + 8000 * np.exp(-((self.wavelengths - 460) ** 2) / 3000) + noise
        )
        fluorescence = np.maximum(fluorescence, 0)
        return {
            "wavelengths": self.wavelengths.tolist(),
            "fluorescence": fluorescence.tolist(),
        }

    async def set_integration_time_ms(self, value: float) -> None:
        self.integration_time = float(value)

    async def set_excitation_wavelength(self, value: float) -> None:
        self.excitation_wl = float(value)


# Register all spectrometer adapters
adapter_registry.register("mock_spectrometer", MockSpectrometer)
adapter_registry.register("mock_hi_res_spectrometer", MockHighResSpectrometer)
adapter_registry.register("mock_uv_vis_spectrometer", MockUVVISSpectrometer)
adapter_registry.register("mock_ir_spectrometer", MockIRSpectrometer)
adapter_registry.register("mock_raman_spectrometer", MockRamanSpectrometer)
adapter_registry.register("mock_fluorescence_spectrometer", MockFluorescenceSpectrometer)
