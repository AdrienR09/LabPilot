"""Mock Lock-in Amplifier Adapters for LabPilot testing and development."""

from typing import Any
import numpy as np
from labpilot_core.adapters._base import AdapterBase, adapter_registry
from labpilot_core.device.schema import DeviceSchema


class MockLockInAmplifier(AdapterBase):
    """Single-channel lock-in amplifier mock (SRS SR830 simulation)."""

    def __init__(self, name: str = "mock_lock_in") -> None:
        super().__init__()
        self._name = name
        self.frequency = 1000.0
        self.phase = 0.0
        self.sensitivity = 100e-9

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"x": "float64", "y": "float64", "r": "float64", "theta": "float64"},
            settable={"frequency": "float64", "phase": "float64", "sensitivity": "float64"},
            units={"frequency": "Hz", "phase": "degrees", "x": "V", "y": "V", "r": "V"},
            limits={"frequency": (0.01, 100000.0), "phase": (-180.0, 180.0)},
            tags=["Mock", "LockIn", "SRS830"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate lock-in output (X, Y channels)."""
        # Simulated input signal
        t_offset = np.random.uniform(0, 1)
        signal = np.sin(2 * np.pi * self.frequency * t_offset / 1e6)
        noise = np.random.normal(0, 0.01)
        x = (signal + noise) * self.sensitivity * 1e9
        y = (np.cos(2 * np.pi * self.frequency * t_offset / 1e6) + np.random.normal(0, 0.01)) * self.sensitivity * 1e9
        r = np.sqrt(x**2 + y**2)
        theta = np.arctan2(y, x) * 180 / np.pi
        return {
            "x": float(x),
            "y": float(y),
            "r": float(r),
            "theta": float(theta),
        }


class MockDualChannelLockin(AdapterBase):
    """Dual-channel lock-in amplifier mock."""

    def __init__(self, name: str = "mock_dual_lockin") -> None:
        super().__init__()
        self._name = name
        self.frequency = 1000.0
        self.channels = 2
        self.phase = 0.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                "x1": "float64",
                "y1": "float64",
                "x2": "float64",
                "y2": "float64",
            },
            settable={"frequency": "float64", "phase": "float64"},
            units={"frequency": "Hz", "phase": "degrees", "x1": "V", "y1": "V", "x2": "V", "y2": "V"},
            limits={"frequency": (0.01, 100000.0)},
            tags=["Mock", "LockIn", "DualChannel"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate dual channel output."""
        # Channel 1
        signal1 = np.sin(2 * np.pi * self.frequency * np.random.uniform(0, 1) / 1e6)
        x1 = (signal1 + np.random.normal(0, 0.01)) * 1e-6
        y1 = (np.cos(2 * np.pi * self.frequency * np.random.uniform(0, 1) / 1e6) + np.random.normal(0, 0.01)) * 1e-6
        # Channel 2 (90° out of phase)
        x2 = (np.cos(2 * np.pi * self.frequency * np.random.uniform(0, 1) / 1e6) + np.random.normal(0, 0.01)) * 1e-6
        y2 = (-np.sin(2 * np.pi * self.frequency * np.random.uniform(0, 1) / 1e6) + np.random.normal(0, 0.01)) * 1e-6
        return {"x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2)}


class MockMultiPhaseLocking(AdapterBase):
    """Multi-phase lock-in amplifier mock (4 phases)."""

    def __init__(self, name: str = "mock_multi_phase_lockin") -> None:
        super().__init__()
        self._name = name
        self.phases = [0.0, 90.0, 180.0, 270.0]
        self.frequency = 1000.0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                "phase_0": "float64",
                "phase_90": "float64",
                "phase_180": "float64",
                "phase_270": "float64",
            },
            settable={"frequency": "float64"},
            units={"frequency": "Hz", "phase_0": "V", "phase_90": "V", "phase_180": "V", "phase_270": "V"},
            limits={"frequency": (0.01, 100000.0)},
            tags=["Mock", "LockIn", "MultiPhase"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Simulate 4-phase lock-in output."""
        outputs = {}
        for i, phase in enumerate(self.phases):
            phase_rad = np.deg2rad(phase)
            signal = np.sin(phase_rad + 2 * np.pi * self.frequency * np.random.uniform(0, 1) / 1e6)
            outputs[f"phase_{int(phase)}"] = float((signal + np.random.normal(0, 0.01)) * 1e-6)
        return outputs


# Register all lock-in amplifier adapters
adapter_registry.register("mock_lock_in", MockLockInAmplifier)
adapter_registry.register("mock_dual_lockin", MockDualChannelLockin)
adapter_registry.register("mock_multi_phase_lockin", MockMultiPhaseLocking)
