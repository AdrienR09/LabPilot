"""Mock Camera Adapters for LabPilot testing and development."""

from typing import Any

import numpy as np

from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry


class MockCCDCamera(AdapterBase):
    """CCD camera mock (Andor simulation)."""

    def __init__(self, name: str = "mock_ccd_camera") -> None:
        super().__init__()
        self._name = name
        self.resolution = (1024, 1024)
        self.temperature = -70.0
        self.exposure_time = 100.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"frame": "ndarray2d", "temperature": "float64"},
            settable={"exposure_time_ms": "float64", "temperature": "float64"},
            units={"temperature": "°C"},
            limits={"exposure_time_ms": (0.001, 10000.0), "temperature": (-80.0, 25.0)},
            tags=["Mock", "Camera", "CCD", "Andor"],
        )

    def _connect_sync(self) -> None:
        """Simulate connection."""
        pass

    def _disconnect_sync(self) -> None:
        """Simulate disconnection."""
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated CCD frame."""
        frame = np.random.randint(0, 1000, self.resolution, dtype=np.uint16)
        # Add a bright spot to simulate a real scene
        y, x = self.resolution[0] // 2, self.resolution[1] // 2
        frame[y - 50 : y + 50, x - 50 : x + 50] += 2000
        frame = np.clip(frame, 0, 65535).astype(np.uint16)
        return {"frame": frame.tolist(), "temperature": float(self.temperature)}

    async def set_exposure_time_ms(self, value: float) -> None:
        self.exposure_time = float(value)

    async def set_temperature(self, value: float) -> None:
        self.temperature = float(value)


class MockEMCCDCamera(AdapterBase):
    """Electron-multiplied CCD mock (EMCCD simulation)."""

    def __init__(self, name: str = "mock_emccd_camera") -> None:
        super().__init__()
        self._name = name
        self.resolution = (512, 512)
        self.em_gain = 1.0
        self.exposure_time = 50.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"frame": "ndarray2d", "em_gain": "float64"},
            settable={"exposure_time_ms": "float64", "em_gain": "float64"},
            units={},
            limits={"exposure_time_ms": (0.001, 5000.0), "em_gain": (1.0, 1000.0)},
            tags=["Mock", "Camera", "EMCCD"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated EMCCD frame with gain-dependent noise."""
        # EM-CCDs have characteristic multiplication noise
        noise_level = int(10 * np.log10(self.em_gain))
        frame = np.random.randint(0, 500, self.resolution, dtype=np.uint16)
        frame += np.random.randint(0, noise_level, self.resolution, dtype=np.uint16)
        return {"frame": frame.tolist(), "em_gain": float(self.em_gain)}

    async def set_exposure_time_ms(self, value: float) -> None:
        self.exposure_time = float(value)

    async def set_em_gain(self, value: float) -> None:
        self.em_gain = float(value)


class MockScientificCamera(AdapterBase):
    """Scientific CMOS camera mock (Hamamatsu simulation)."""

    def __init__(self, name: str = "mock_scientific_camera") -> None:
        super().__init__()
        self._name = name
        self.resolution = (2048, 2048)
        self.fps = 30.0
        self.exposure_time = 33.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"frame": "ndarray2d", "fps": "float64"},
            settable={"exposure_time_ms": "float64", "fps": "float64"},
            units={},
            limits={"exposure_time_ms": (0.1, 10000.0), "fps": (1.0, 100.0)},
            tags=["Mock", "Camera", "sCMOS", "Scientific"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated sCMOS frame."""
        frame = np.random.randint(100, 1000, self.resolution, dtype=np.uint16)
        # Add structured noise pattern
        for i in range(0, self.resolution[0], 16):
            frame[i : i + 4, :] += np.random.randint(0, 50)
        return {"frame": np.clip(frame, 0, 65535).astype(np.uint16).tolist(), "fps": float(self.fps)}

    async def set_exposure_time_ms(self, value: float) -> None:
        self.exposure_time = float(value)

    async def set_fps(self, value: float) -> None:
        self.fps = float(value)


class MockHighSpeedCamera(AdapterBase):
    """High-speed camera mock."""

    def __init__(self, name: str = "mock_high_speed_camera") -> None:
        super().__init__()
        self._name = name
        self.resolution = (640, 480)
        self.fps_max = 10000.0
        self.fps = 1000.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"frame": "ndarray2d"},
            settable={"fps": "float64"},
            units={},
            limits={"fps": (100.0, 10000.0)},
            tags=["Mock", "Camera", "HighSpeed"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated high-speed frame."""
        frame = np.random.randint(0, 255, self.resolution, dtype=np.uint8)
        return {"frame": frame.tolist()}

    async def set_fps(self, value: float) -> None:
        self.fps = float(value)


class MockThermalCamera(AdapterBase):
    """Thermal/IR camera mock."""

    def __init__(self, name: str = "mock_thermal_camera") -> None:
        super().__init__()
        self._name = name
        self.resolution = (640, 480)
        self.temperature_range = (-40.0, 120.0)
        self.exposure_time = 50.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"frame": "ndarray2d", "min_temp": "float64", "max_temp": "float64"},
            settable={"exposure_time_ms": "float64"},
            units={"min_temp": "°C", "max_temp": "°C"},
            limits={"exposure_time_ms": (1.0, 5000.0)},
            tags=["Mock", "Camera", "Thermal", "IR"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated thermal image."""
        # Thermal data as 16-bit temperature in Kelvin
        base_temp = 300  # 27°C in K
        frame = np.random.randint(base_temp - 50, base_temp + 50, self.resolution, dtype=np.uint16)
        # Add a hot spot
        y, x = self.resolution[0] // 2, self.resolution[1] // 2
        frame[y - 30 : y + 30, x - 30 : x + 30] += 100
        return {
            "frame": frame.tolist(),
            "min_temp": float(np.min(frame) - 273),
            "max_temp": float(np.max(frame) - 273),
        }

    async def set_exposure_time_ms(self, value: float) -> None:
        self.exposure_time = float(value)


class MockLineScanCamera(AdapterBase):
    """Line scan camera mock."""

    def __init__(self, name: str = "mock_line_scan_camera") -> None:
        super().__init__()
        self._name = name
        self.pixels = 4096
        self.scan_rate = 50000.0
        self.exposure_time = 20.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"line": "ndarray1d"},
            settable={"exposure_time_us": "float64", "scan_rate": "float64"},
            units={},
            limits={"exposure_time_us": (0.1, 1000.0), "scan_rate": (1000.0, 500000.0)},
            tags=["Mock", "Camera", "LineScan"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Return simulated line scan data."""
        line = np.random.randint(100, 900, self.pixels, dtype=np.uint16)
        # Add a feature to simulate real data
        line[1000:1500] += 2000
        return {"line": np.clip(line, 0, 65535).astype(np.uint16).tolist()}

    async def set_exposure_time_us(self, value: float) -> None:
        self.exposure_time = float(value)

    async def set_scan_rate(self, value: float) -> None:
        self.scan_rate = float(value)


# Register all camera adapters
adapter_registry.register("mock_ccd_camera", MockCCDCamera)
adapter_registry.register("mock_emccd_camera", MockEMCCDCamera)
adapter_registry.register("mock_scientific_camera", MockScientificCamera)
adapter_registry.register("mock_high_speed_camera", MockHighSpeedCamera)
adapter_registry.register("mock_thermal_camera", MockThermalCamera)
adapter_registry.register("mock_line_scan_camera", MockLineScanCamera)
