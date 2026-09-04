"""Mock acousto-optic modulator (AOM), for gating a laser's optical path
in a pulsed-optics workflow (e.g. ODMR's laser init/readout gating).

Digital gate only for now — analog amplitude/waveform-shaped modulation
(driving the AOM from an arbitrary-waveform generator instead of a plain
TTL) is a deliberately deferred, later step; see docs/workflows.md's ODMR
notes. Follows the same binary-actuator shape as
test_fixtures.FakeSwitchAdapter ("shutters, relays, laser enable, etc."),
just named/tagged for this role specifically.
"""

from typing import Any

from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema


class MockAOM(AdapterBase):
    """Digital-gate-only acousto-optic modulator mock."""

    def __init__(self, name: str = "mock_aom") -> None:
        super().__init__()
        self._name = name
        self._gate_open = False

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"gate_open": "bool"},
            settable={"gate_open": "bool"},
            units={},
            limits={},
            tags=["Mock", "AOM", "OpticalModulator", "Gate", "ODMR"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"gate_open": self._gate_open}

    async def set_gate_open(self, value: bool) -> None:
        self._gate_open = bool(value)


adapter_registry.register("mock_aom", MockAOM)
