"""Mock laser adapters for LabPilot testing and development.

A fixed-wavelength CW pump laser (e.g. 532nm, matching real adapters like
Laser Quantum Finesse) — power control plus a software/TTL enable. Not to
be confused with test_fixtures.TunableLaserMotorAdapter, which simulates
wavelength as a swept 1D motor axis for spectroscopy workflows; an ODMR
pump laser is normally fixed-wavelength and is gated on/off by an AOM
(see optical_modulators.py) rather than tuned.
"""

from typing import Any

from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry


class MockLaser(AdapterBase):
    """Fixed-wavelength CW pump laser mock."""

    def __init__(self, name: str = "mock_laser", wavelength_nm: float = 532.0) -> None:
        super().__init__()
        self._name = name
        self.wavelength_nm = wavelength_nm
        self.power_mw = 0.0
        self._enabled = False

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"power_mw": "float64", "enabled": "bool", "wavelength_nm": "float64"},
            settable={"power_mw": "float64", "enabled": "bool"},
            units={"power_mw": "mW", "wavelength_nm": "nm"},
            limits={"power_mw": (0.0, 500.0)},
            tags=["Mock", "Laser", "CW", "Pump", "ODMR"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {
            "power_mw": self.power_mw if self._enabled else 0.0,
            "enabled": self._enabled,
            "wavelength_nm": self.wavelength_nm,
        }

    async def set_power_mw(self, value: float) -> None:
        self.power_mw = float(value)

    async def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)


adapter_registry.register("mock_laser", MockLaser)
