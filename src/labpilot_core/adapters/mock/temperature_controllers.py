"""Mock Temperature Controller Adapters for LabPilot testing and development."""

from typing import Any
import numpy as np
from labpilot_core.adapters._base import AdapterBase, adapter_registry
from labpilot_core.device.schema import DeviceSchema


class MockTemperatureController(AdapterBase):
    """Basic temperature controller mock (Lakeshore 331 simulation)."""

    def __init__(self, name: str = "mock_temperature_controller") -> None:
        super().__init__()
        self._name = name
        self.setpoint = 300.0
        self.temperature = 300.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"temperature": "float64", "setpoint": "float64"},
            settable={"setpoint": "float64"},
            units={"temperature": "K", "setpoint": "K"},
            limits={"setpoint": (4.0, 300.0)},
            tags=["Mock", "TemperatureController", "Lakeshore"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate exponential approach to setpoint."""
        tau = 10.0  # Time constant in seconds
        # Simulate slow temperature change
        delta = (self.setpoint - self.temperature) * (1 - np.exp(-1 / tau))
        self.temperature += delta * 0.1  # Small update
        noise = np.random.normal(0, 0.1)
        return {
            "temperature": float(self.temperature + noise),
            "setpoint": float(self.setpoint),
        }


class MockCryostat(AdapterBase):
    """Cryostat mock (LHe cooling)."""

    def __init__(self, name: str = "mock_cryostat") -> None:
        super().__init__()
        self._name = name
        self.temperature_range = (4.0, 300.0)
        self.temperature = 77.0  # LN2 temperature
        self.setpoint = 77.0
        self.helium_level = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={
                "temperature": "float64",
                "setpoint": "float64",
                "helium_level": "float64",
            },
            settable={"setpoint": "float64"},
            units={"temperature": "K", "setpoint": "K", "helium_level": "%"},
            limits={"setpoint": self.temperature_range},
            tags=["Mock", "Cryostat", "Helium"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        # Simulate He boil-off
        self.helium_level = max(0, self.helium_level - 0.1)
        tau = 100.0
        delta = (self.setpoint - self.temperature) * (1 - np.exp(-1 / tau))
        self.temperature += delta * 0.01
        self.temperature = np.clip(self.temperature, 4.0, 300.0)
        return {
            "temperature": float(self.temperature + np.random.normal(0, 0.05)),
            "setpoint": float(self.setpoint),
            "helium_level": float(self.helium_level),
        }


class MockThermoElectricCooler(AdapterBase):
    """Thermoelectric cooler (TEC) mock."""

    def __init__(self, name: str = "mock_tec") -> None:
        super().__init__()
        self._name = name
        self.temperature_range = (-40.0, 80.0)
        self.temperature = 25.0
        self.setpoint = 25.0
        self.power = 0.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"temperature": "float64", "power": "float64"},
            settable={"setpoint": "float64"},
            units={"temperature": "°C", "power": "W"},
            limits={"setpoint": self.temperature_range},
            tags=["Mock", "TEC", "ThermoelectricCooler"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        # TEC power proportional to temperature difference
        self.power = abs(self.setpoint - self.temperature) * 10  # W
        tau = 5.0
        delta = (self.setpoint - self.temperature) * (1 - np.exp(-1 / tau))
        self.temperature += delta * 0.2
        self.temperature = np.clip(self.temperature, *self.temperature_range)
        return {
            "temperature": float(self.temperature + np.random.normal(0, 0.1)),
            "power": float(self.power),
        }


class MockHeater(AdapterBase):
    """Resistance heater mock."""

    def __init__(self, name: str = "mock_heater") -> None:
        super().__init__()
        self._name = name
        self.max_temperature = 500.0
        self.temperature = 25.0
        self.setpoint = 25.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"temperature": "float64"},
            settable={"setpoint": "float64"},
            units={"temperature": "°C"},
            limits={"setpoint": (0.0, self.max_temperature)},
            tags=["Mock", "Heater"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        tau = 20.0
        delta = (self.setpoint - self.temperature) * (1 - np.exp(-1 / tau))
        self.temperature += delta * 0.15
        self.temperature = np.clip(self.temperature, 0, self.max_temperature)
        return {
            "temperature": float(self.temperature + np.random.normal(0, 0.2))
        }


# Register all temperature controller adapters
adapter_registry.register("mock_temperature_controller", MockTemperatureController)
adapter_registry.register("mock_cryostat", MockCryostat)
adapter_registry.register("mock_tec", MockThermoElectricCooler)
adapter_registry.register("mock_heater", MockHeater)
