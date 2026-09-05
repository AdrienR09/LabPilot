"""Mock Source Meter Adapters for LabPilot testing and development."""

from typing import Any

import numpy as np

from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry


class MockSourceMeter(AdapterBase):
    """Basic source meter mock (Keithley 2400 simulation)."""

    def __init__(self, name: str = "mock_source_meter") -> None:
        super().__init__()
        self._name = name
        self.voltage = 0.0
        self.current = 0.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"voltage": "float64", "current": "float64", "resistance": "float64"},
            settable={"voltage": "float64", "current": "float64"},
            units={"voltage": "V", "current": "A", "resistance": "Ω"},
            limits={"voltage": (-210.0, 210.0), "current": (-1.05, 1.05)},
            tags=["Mock", "SourceMeter", "SMU", "Keithley"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate measurement with realistic noise."""
        # Add measurement noise and settling
        v_noise = np.random.normal(0, 0.001)
        i_noise = np.random.normal(0, 1e-9)
        measured_voltage = self.voltage + v_noise
        measured_current = self.current + i_noise
        # Calculate resistance (avoid division by zero)
        resistance = (
            measured_voltage / measured_current
            if abs(measured_current) > 1e-12
            else float("inf")
        )
        return {
            "voltage": float(measured_voltage),
            "current": float(measured_current),
            "resistance": float(resistance) if resistance != float("inf") else 1e12,
        }

    async def set_voltage(self, value: float) -> None:
        self.voltage = float(value)

    async def set_current(self, value: float) -> None:
        self.current = float(value)


class MockHighVoltageSource(AdapterBase):
    """High-voltage source mock."""

    def __init__(self, name: str = "mock_hv_source") -> None:
        super().__init__()
        self._name = name
        self.voltage_range = (0.0, 1000.0)
        self.voltage = 0.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"voltage": "float64", "current": "float64"},
            settable={"voltage": "float64"},
            units={"voltage": "V", "current": "mA"},
            limits={"voltage": self.voltage_range},
            tags=["Mock", "HVSource", "HighVoltage"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        v_noise = np.random.normal(0, 0.1)
        measured_voltage = self.voltage + v_noise
        current = np.random.uniform(0, 10) * 1e-3  # Up to 10mA
        return {
            "voltage": float(np.clip(measured_voltage, *self.voltage_range)),
            "current": float(current),
        }

    async def set_voltage(self, value: float) -> None:
        self.voltage = float(value)


class MockCurrentSource(AdapterBase):
    """Current source mock."""

    def __init__(self, name: str = "mock_current_source") -> None:
        super().__init__()
        self._name = name
        self.current_range = (-1.0, 1.0)
        self.current = 0.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"current": "float64", "voltage": "float64"},
            settable={"current": "float64"},
            units={"current": "A", "voltage": "V"},
            limits={"current": self.current_range},
            tags=["Mock", "CurrentSource"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        i_noise = np.random.normal(0, 1e-9)
        measured_current = self.current + i_noise
        voltage = np.random.uniform(-10, 10)  # Compliance voltage
        return {
            "current": float(np.clip(measured_current, *self.current_range)),
            "voltage": float(voltage),
        }

    async def set_current(self, value: float) -> None:
        self.current = float(value)


class MockDualSourceMeter(AdapterBase):
    """Dual source meter mock (Keithley 2600 simulation)."""

    def __init__(self, name: str = "mock_dual_source_meter") -> None:
        super().__init__()
        self._name = name
        self.channels = 2
        self.voltage = [0.0, 0.0]
        self.current = [0.0, 0.0]

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={
                "voltage_ch1": "float64",
                "current_ch1": "float64",
                "voltage_ch2": "float64",
                "current_ch2": "float64",
            },
            settable={
                "voltage_ch1": "float64",
                "voltage_ch2": "float64",
            },
            units={"voltage_ch1": "V", "current_ch1": "A", "voltage_ch2": "V", "current_ch2": "A"},
            limits={
                "voltage_ch1": (-210.0, 210.0),
                "voltage_ch2": (-210.0, 210.0),
            },
            tags=["Mock", "SourceMeter", "DualChannel", "Keithley2600"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate dual-channel SMU."""
        outputs = {}
        for ch in range(self.channels):
            v_noise = np.random.normal(0, 0.001)
            i_noise = np.random.normal(0, 1e-9)
            outputs[f"voltage_ch{ch+1}"] = float(self.voltage[ch] + v_noise)
            outputs[f"current_ch{ch+1}"] = float(self.current[ch] + i_noise)
        return outputs

    async def set_voltage_ch1(self, value: float) -> None:
        self.voltage[0] = float(value)

    async def set_voltage_ch2(self, value: float) -> None:
        self.voltage[1] = float(value)


# Register all source meter adapters
adapter_registry.register("mock_source_meter", MockSourceMeter)
adapter_registry.register("mock_hv_source", MockHighVoltageSource)
adapter_registry.register("mock_current_source", MockCurrentSource)
adapter_registry.register("mock_dual_source_meter", MockDualSourceMeter)
