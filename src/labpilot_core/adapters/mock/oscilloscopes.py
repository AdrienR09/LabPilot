"""Mock Oscilloscope Adapters for LabPilot testing and development."""

from typing import Any
import numpy as np
from labpilot_core.adapters._base import AdapterBase, adapter_registry
from labpilot_core.device.schema import DeviceSchema


class MockOscilloscope(AdapterBase):
    """4-channel oscilloscope mock."""

    def __init__(self, name: str = "mock_oscilloscope") -> None:
        super().__init__()
        self._name = name
        self.channels = 4
        self.bandwidth = 1e9
        self.sample_rate = 1e9
        self.record_length = 1000

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                "ch1": "ndarray1d",
                "ch2": "ndarray1d",
                "ch3": "ndarray1d",
                "ch4": "ndarray1d",
            },
            settable={"sample_rate": "float64", "record_length": "int32"},
            units={"ch1": "V", "ch2": "V", "ch3": "V", "ch4": "V"},
            limits={"record_length": (100, 1000000)},
            tags=["Mock", "Oscilloscope", "4Channel"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate oscilloscope waveform capture."""
        t = np.linspace(0, 1, self.record_length)
        outputs = {}
        # Generate different waveforms per channel
        outputs["ch1"] = (5 * np.sin(2 * np.pi * 1e6 * t)).tolist()  # 1MHz sine
        outputs["ch2"] = (3 * np.cos(2 * np.pi * 2e6 * t)).tolist()  # 2MHz cosine
        outputs["ch3"] = (2 * (2 * (t % 0.5) - 0.5)).tolist()  # Triangle wave
        outputs["ch4"] = (
            np.where(np.sin(2 * np.pi * 500e3 * t) > 0, 1, -1) * 2
        ).tolist()  # Square wave
        return outputs


class MockUSBOscilloscope(AdapterBase):
    """USB-based 2-channel oscilloscope mock."""

    def __init__(self, name: str = "mock_usb_oscilloscope") -> None:
        super().__init__()
        self._name = name
        self.channels = 2
        self.bandwidth = 100e6
        self.sample_rate = 1e6
        self.record_length = 2000

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"ch1": "ndarray1d", "ch2": "ndarray1d"},
            settable={"sample_rate": "float64", "record_length": "int32"},
            units={"ch1": "V", "ch2": "V"},
            limits={"record_length": (100, 100000), "sample_rate": (1e3, 100e6)},
            tags=["Mock", "Oscilloscope", "USB", "2Channel"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate USB oscilloscope capture."""
        t = np.linspace(0, 1, self.record_length)
        # More realistic noisy signals
        ch1 = 2 * np.sin(2 * np.pi * 100e3 * t) + np.random.normal(0, 0.05, len(t))
        ch2 = 1.5 * np.cos(2 * np.pi * 150e3 * t) + np.random.normal(0, 0.03, len(t))
        return {"ch1": ch1.tolist(), "ch2": ch2.tolist()}


class MockHighSpeedOscilloscope(AdapterBase):
    """High-speed 8-channel oscilloscope mock."""

    def __init__(self, name: str = "mock_hs_oscilloscope") -> None:
        super().__init__()
        self._name = name
        self.channels = 8
        self.bandwidth = 10e9
        self.sample_rate = 50e9
        self.record_length = 10000

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                f"ch{i+1}": "ndarray1d" for i in range(self.channels)
            },
            settable={"sample_rate": "float64", "record_length": "int32"},
            units={f"ch{i+1}": "V" for i in range(self.channels)},
            limits={"record_length": (1000, 1000000), "sample_rate": (1e6, 50e9)},
            tags=["Mock", "Oscilloscope", "HighSpeed", "8Channel"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate high-speed 8-channel capture."""
        t = np.linspace(0, 1e-6, self.record_length)  # 1 microsecond record
        outputs = {}
        for ch in range(self.channels):
            freq = 1e9 + ch * 100e6  # Different frequencies per channel
            amplitude = 1 + ch * 0.2
            phase = ch * np.pi / 4
            waveform = amplitude * np.sin(2 * np.pi * freq * t + phase)
            outputs[f"ch{ch+1}"] = waveform.tolist()
        return outputs


# Register all oscilloscope adapters
adapter_registry.register("mock_oscilloscope", MockOscilloscope)
adapter_registry.register("mock_usb_oscilloscope", MockUSBOscilloscope)
adapter_registry.register("mock_hs_oscilloscope", MockHighSpeedOscilloscope)
