"""Mock Power Meter Adapters for LabPilot testing and development."""

from typing import Any
import numpy as np
from labpilot_core.adapters._base import AdapterBase, adapter_registry
from labpilot_core.device.schema import DeviceSchema


class MockPowerMeter(AdapterBase):
    """Basic power meter mock."""

    def __init__(self, name: str = "mock_power_meter") -> None:
        super().__init__()
        self._name = name
        self.power = 1.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"power": "float64"},
            settable={},
            units={"power": "mW"},
            trigger_modes=["software"],
            tags=["Mock", "PowerMeter"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        # Simulate fluctuating power with noise
        noise = np.random.normal(0, 0.05, 1)[0]
        power = self.power + noise
        return {"power": float(np.clip(power, 0, 1000))}


class MockUVPowerMeter(AdapterBase):
    """UV-optimized power meter mock."""

    def __init__(self, name: str = "mock_uv_power_meter") -> None:
        super().__init__()
        self._name = name
        self.wavelength_range = (200.0, 400.0)
        self.power = 0.5

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"power": "float64", "wavelength": "float64"},
            settable={"wavelength": "float64"},
            units={"power": "mW", "wavelength": "nm"},
            limits={"wavelength": self.wavelength_range},
            tags=["Mock", "PowerMeter", "UV"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        noise = np.random.normal(0, 0.02, 1)[0]
        power = self.power + noise
        wavelength = np.random.uniform(*self.wavelength_range)
        return {"power": float(np.clip(power, 0, 100)), "wavelength": float(wavelength)}


class MockIRPowerMeter(AdapterBase):
    """IR-optimized power meter mock."""

    def __init__(self, name: str = "mock_ir_power_meter") -> None:
        super().__init__()
        self._name = name
        self.wavelength_range = (700.0, 10000.0)
        self.power = 2.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"power": "float64", "wavelength": "float64"},
            settable={"wavelength": "float64"},
            units={"power": "mW", "wavelength": "nm"},
            limits={"wavelength": self.wavelength_range},
            tags=["Mock", "PowerMeter", "IR"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        noise = np.random.normal(0, 0.1, 1)[0]
        power = self.power + noise
        wavelength = np.random.uniform(*self.wavelength_range)
        return {"power": float(np.clip(power, 0, 500)), "wavelength": float(wavelength)}


class MockArrayPowerMeter(AdapterBase):
    """Array power meter mock (16-channel)."""

    def __init__(self, name: str = "mock_array_power_meter") -> None:
        super().__init__()
        self._name = name
        self.channels = 16

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"powers": "ndarray1d"},
            settable={},
            units={"powers": "mW"},
            tags=["Mock", "PowerMeter", "Array"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated 16-channel power data."""
        powers = []
        for _ in range(self.channels):
            base_power = np.random.uniform(0.1, 5.0)
            noise = np.random.normal(0, 0.05)
            power = np.clip(base_power + noise, 0, 1000)
            powers.append(float(power))
        return {"powers": powers}


# Register all power meter adapters
adapter_registry.register("mock_power_meter", MockPowerMeter)
adapter_registry.register("mock_uv_power_meter", MockUVPowerMeter)
adapter_registry.register("mock_ir_power_meter", MockIRPowerMeter)
adapter_registry.register("mock_array_power_meter", MockArrayPowerMeter)
