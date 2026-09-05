"""Mock Spectrometer Adapters for LabPilot testing and development."""

from typing import Any

import numpy as np

from labpilot.core.device.parameter import INTEGRATION_TIME, Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry


def _spectrum(axis: str, axis_unit: str, value: str, value_unit: str,
              *, axis_description: str = "") -> tuple[Parameter, Parameter]:
    """The axis/value pair a spectrometer reports, declared rather than
    inferred.

    Which of two same-shaped arrays is the x-axis and which is the
    measurement was previously guessed from a hardcoded list of axis-ish
    names — "wavelength", "time", "frequency", "x" — in three places
    (`core/workflow_templates/_common.py`, `ui/.../schema_utils.py`, and
    the omniscan template). Any spectrometer whose axis is called
    something else fell through and had its *axis* plotted as the
    measurement: the IR mock's wavenumbers and the Raman mock's shift both
    did exactly that. Saying it here fixes it for every consumer at once,
    and cannot go stale the way a list of names does.
    """
    return (
        Parameter(axis, shape=(None,), unit=axis_unit, role=ParamRole.AXIS,
                  description=axis_description),
        Parameter(value, shape=(None,), unit=value_unit, axes=(axis,)),
    )


def _integration_time(limits: tuple[float, float] = (1.0, 60000.0)) -> Parameter:
    return Parameter("integration_time_ms", unit="ms", role=ParamRole.SETTING,
                     settable=True, limits=limits,
                     tags=frozenset({INTEGRATION_TIME}),
                     description="Exposure per spectrum.")


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
            parameters=(
                *_spectrum("wavelengths", "nm", "intensities", "counts"),
                _integration_time(),
            ),
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
            parameters=(
                *_spectrum("wavelengths", "nm", "intensities", "counts"),
                _integration_time(),
                Parameter("grating", dtype="str", role=ParamRole.SETTING,
                          settable=True),
            ),
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
            parameters=(
                *_spectrum("wavelengths", "nm", "absorbance", "AU"),
                _integration_time(),
            ),
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
            parameters=(
                *_spectrum("wavenumbers", "cm^-1", "transmittance", "%"),
                _integration_time(),
            ),
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
            parameters=(
                *_spectrum("shift", "cm^-1", "intensity", "counts",
                           axis_description="Raman shift from the laser line."),
                _integration_time(),
                Parameter("laser_wavelength", unit="nm", role=ParamRole.SETTING,
                          settable=True, limits=(200.0, 1100.0)),
            ),
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
            parameters=(
                *_spectrum("wavelengths", "nm", "fluorescence", "counts"),
                _integration_time(),
                Parameter("excitation_wavelength", unit="nm",
                          role=ParamRole.SETTING, settable=True,
                          limits=(200.0, 1100.0)),
            ),
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
