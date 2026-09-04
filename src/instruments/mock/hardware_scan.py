"""Mock hardware-timed (NI-card-style) scanner — see
instruments/hardware_scan_mixin.py for the contract this implements, and
instruments/NI/generic.py's NIDAQScannerAdapter for the real pylablib-
backed equivalent.

Reuses MockBasic/simple.py's `_SimulatedSample` (a real, position-
dependent Gaussian-peak signal — the same "give a scan/optimizer
something real to fit, not noise" convention every other MockBasic
instrument already uses) so this mock's data is physically meaningful.

Timing is paced by real elapsed wall-clock time against the configured
`frequency`, not by any artificial per-sample delay: `get_scan_data()`
computes how many samples a real hardware clock running at `frequency`
Hz would have produced by now, and fills exactly that many — the same
"total time = samples / sample_rate, nothing else" behavior real
hardware-timed scanning gets, for the same reason (no per-pixel
software round-trip).
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from instruments._base import AdapterBase, adapter_registry
from instruments.hardware_scan_mixin import HardwareScanMixin, build_scan_waveform
from instruments.MockBasic.simple import _SimulatedSample
from core.device.schema import DeviceSchema

_PEAK_WIDTH = 1.5


class MockNIScanner(HardwareScanMixin, AdapterBase):
    """Mock combined position+detector scanning unit — kind="generic"
    (doesn't fit the plain motor/detector split, same call already made
    for mock_pulse_sequencer): the real interaction here is
    configure_scan/start_scan/get_scan_data/stop_scan, not read()/write()
    point-by-point."""

    def __init__(self, name: str = "mock_ni_scanner", sample: str = "ni_scanner") -> None:
        super().__init__()
        self._name = name
        self._sample_name = sample
        self._axes: list[str] = []
        self._ranges: dict[str, tuple[float, float]] = {}
        self._resolution: dict[str, int] = {}
        self._frequency = 1.0
        self._flat_waveforms: dict[str, np.ndarray] = {}
        self._frame_size = 0
        self._data: list[float | None] = []
        self._filled_count = 0
        self._start_time = 0.0
        self._running = False

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="generic",
            readable={"status": "str"},
            settable={},
            tags=["Mock", "NI", "DAQ", "HardwareScan", "Scanner"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"status": "scanning" if self._running else "idle"}

    async def configure_scan(
        self, axes: list[str], ranges: dict[str, tuple[float, float]],
        resolution: dict[str, int], frequency: float,
    ) -> None:
        self._axes = list(axes)
        self._ranges = dict(ranges)
        self._resolution = dict(resolution)
        self._frequency = max(1.0, float(frequency))
        self._flat_waveforms, _axis_positions, self._frame_size = build_scan_waveform(axes, ranges, resolution)
        self._data = [None] * self._frame_size
        self._filled_count = 0
        self._running = False

    async def start_scan(self) -> None:
        self._start_time = time.monotonic()
        self._running = True

    async def get_scan_data(self) -> dict[str, Any]:
        sample = _SimulatedSample.get(self._sample_name, tuple(self._axes))
        if self._running:
            elapsed = time.monotonic() - self._start_time
            samples_ready = min(self._frame_size, int(elapsed * self._frequency))
        else:
            samples_ready = self._filled_count

        for i in range(self._filled_count, samples_ready):
            position = {axis: float(self._flat_waveforms[axis][i]) for axis in self._axes}
            sample.update_position(position)
            signal = math.exp(-sample.distance_sq(tuple(self._axes)) / (2 * _PEAK_WIDTH**2))
            noise = np.random.normal(0, 0.02)
            self._data[i] = float(signal + noise)
        self._filled_count = samples_ready

        done = samples_ready >= self._frame_size
        if done:
            self._running = False
        return {
            "data": list(self._data), "completed": samples_ready,
            "total": self._frame_size, "done": done,
        }

    async def stop_scan(self) -> None:
        self._running = False


adapter_registry.register("mock_ni_scanner", MockNIScanner)
