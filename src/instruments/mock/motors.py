"""Mock Motor Adapters for LabPilot testing and development."""

from typing import Any
from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema


class MockMotor(AdapterBase):
    """Single-axis motor mock."""

    def __init__(self, name: str = "mock_motor") -> None:
        super().__init__()
        self._name = name
        self.position = 0.0
        self.velocity = 1.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"position": "float64", "moving": "bool"},
            settable={"position": "float64", "velocity": "float64"},
            units={"position": "mm", "velocity": "mm/s"},
            limits={"position": (0.0, 100.0), "velocity": (0.1, 10.0)},
            tags=["Mock", "Motor", "1D"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"position": self.position, "moving": False}

    async def set_position(self, value: float) -> None:
        self.position = float(value)

    async def set_velocity(self, value: float) -> None:
        self.velocity = float(value)


class MockXYStage(AdapterBase):
    """XY stage mock (2-axis motor)."""

    def __init__(self, name: str = "mock_xy_stage") -> None:
        super().__init__()
        self._name = name
        self.x_position = 0.0
        self.y_position = 0.0
        self.velocity = 1.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"x": "float64", "y": "float64", "moving": "bool"},
            settable={"x": "float64", "y": "float64", "velocity": "float64"},
            units={"x": "mm", "y": "mm", "velocity": "mm/s"},
            limits={"x": (0.0, 50.0), "y": (0.0, 50.0), "velocity": (0.1, 10.0)},
            tags=["Mock", "Stage", "XY", "2D"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"x": self.x_position, "y": self.y_position, "moving": False}

    async def set_x(self, value: float) -> None:
        self.x_position = float(value)

    async def set_y(self, value: float) -> None:
        self.y_position = float(value)

    async def set_velocity(self, value: float) -> None:
        self.velocity = float(value)


class MockXYZStage(AdapterBase):
    """XYZ stage mock (3-axis motor)."""

    def __init__(self, name: str = "mock_xyz_stage") -> None:
        super().__init__()
        self._name = name
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.velocity = 1.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"x": "float64", "y": "float64", "z": "float64", "moving": "bool"},
            settable={"x": "float64", "y": "float64", "z": "float64", "velocity": "float64"},
            units={"x": "mm", "y": "mm", "z": "mm", "velocity": "mm/s"},
            limits={
                "x": (0.0, 50.0),
                "y": (0.0, 50.0),
                "z": (0.0, 20.0),
                "velocity": (0.1, 10.0),
            },
            tags=["Mock", "Stage", "XYZ", "3D"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z, "moving": False}

    async def set_x(self, value: float) -> None:
        self.x = float(value)

    async def set_y(self, value: float) -> None:
        self.y = float(value)

    async def set_z(self, value: float) -> None:
        self.z = float(value)

    async def set_velocity(self, value: float) -> None:
        self.velocity = float(value)


class MockRotationalStage(AdapterBase):
    """Rotational motor mock."""

    def __init__(self, name: str = "mock_rotational_stage") -> None:
        super().__init__()
        self._name = name
        self.angle = 0.0
        self.velocity = 5.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"angle": "float64", "moving": "bool"},
            settable={"angle": "float64", "velocity": "float64"},
            units={"angle": "degrees", "velocity": "degrees/s"},
            limits={"angle": (0.0, 360.0), "velocity": (0.1, 30.0)},
            tags=["Mock", "Motor", "Rotational"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"angle": self.angle % 360.0, "moving": False}

    async def set_angle(self, value: float) -> None:
        self.angle = float(value)

    async def set_velocity(self, value: float) -> None:
        self.velocity = float(value)


class MockPiezoStage(AdapterBase):
    """Piezo XYZ stage mock (high precision)."""

    def __init__(self, name: str = "mock_piezo_stage") -> None:
        super().__init__()
        self._name = name
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.voltage_range = (0.0, 150.0)

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"x": "float64", "y": "float64", "z": "float64"},
            settable={"x": "float64", "y": "float64", "z": "float64"},
            units={"x": "um", "y": "um", "z": "um"},
            limits={
                "x": (0.0, 100.0),
                "y": (0.0, 100.0),
                "z": (0.0, 20.0),
            },
            tags=["Mock", "Stage", "Piezo", "HighPrecision"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z}

    async def set_x(self, value: float) -> None:
        self.x = float(value)

    async def set_y(self, value: float) -> None:
        self.y = float(value)

    async def set_z(self, value: float) -> None:
        self.z = float(value)


class MockFocusMotor(AdapterBase):
    """Focus (Z-axis) motor mock."""

    def __init__(self, name: str = "mock_focus_motor") -> None:
        super().__init__()
        self._name = name
        self.z_position = 0.0
        self.velocity = 0.5

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"z": "float64", "moving": "bool"},
            settable={"z": "float64", "velocity": "float64"},
            units={"z": "mm", "velocity": "mm/s"},
            limits={"z": (-10.0, 10.0), "velocity": (0.1, 5.0)},
            tags=["Mock", "Motor", "Focus", "Z"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"z": self.z_position, "moving": False}

    async def set_z(self, value: float) -> None:
        self.z_position = float(value)

    async def set_velocity(self, value: float) -> None:
        self.velocity = float(value)


# Register all motor adapters
adapter_registry.register("mock_motor", MockMotor)
adapter_registry.register("mock_xy_stage", MockXYStage)
adapter_registry.register("mock_xyz_stage", MockXYZStage)
adapter_registry.register("mock_rotational_stage", MockRotationalStage)
adapter_registry.register("mock_piezo_stage", MockPiezoStage)
adapter_registry.register("mock_focus_motor", MockFocusMotor)
