"""Mock digital pulse sequencer (Swabian Pulse Streamer / PulseBlaster-
class hardware), for timing-critical pulsed workflows like pulsed-ODMR,
Rabi, Ramsey, Hahn echo.

A sequence is a flat, ordered list of `{"duration_ns": float, "channels":
[int, ...]}` steps, played back once or looped — this is the real
programming model this class of hardware actually exposes (confirmed
against Swabian's own Pulse Streamer API and the general pattern
PulseBlaster-class sequencers use), not qudi's fuller
PulseBlockElement/PulseBlock/PulseBlockEnsemble model (per-element analog
waveform sampling functions, per-repetition length increments, block
nesting into sequences). That fuller generality targets true
arbitrary-waveform generators and is a deliberately deferred, later step
— see docs/workflows.md's ODMR notes. Digital/TTL channels only here.
"""

from typing import Any

from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema


class MockPulseSequencer(AdapterBase):
    """TTL step-list pulse sequencer mock."""

    def __init__(self, name: str = "mock_pulse_sequencer", n_channels: int = 8) -> None:
        super().__init__()
        self._name = name
        self.n_channels = n_channels
        self._sequence: list[dict] = []
        self._loop = False
        self._running = False

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="generic",
            readable={
                "running": "bool", "sequence_length": "int32", "total_duration_ns": "float64",
                "n_channels": "int32",
            },
            settable={"sequence": "json", "loop": "bool"},
            units={"total_duration_ns": "ns"},
            limits={},
            tags=["Mock", "PulseSequencer", "TTL", "Digital", "PulseStreamer", "PulseBlaster", "ODMR"],
            actions=["start", "stop"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "sequence_length": len(self._sequence),
            "total_duration_ns": float(sum(step["duration_ns"] for step in self._sequence)),
            "n_channels": self.n_channels,
        }

    async def set_sequence(self, value: list) -> None:
        """`value`: a list of `{"duration_ns": float, "channels": [int, ...]}`
        steps (channel indices active — high — for that step's duration).
        Replaces any previously uploaded sequence; does not start playback
        (see start())."""
        self._sequence = list(value)

    async def set_loop(self, value: bool) -> None:
        self._loop = bool(value)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False


adapter_registry.register("mock_pulse_sequencer", MockPulseSequencer)
