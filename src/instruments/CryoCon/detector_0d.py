"""Cryo-Con 14C temperature controller adapter (placeholder implementation).

Note: this adapter has no real pylablib/vendor driver wired up yet — connect
and read are stubs. Kept registered so it shows up in discovery/catalog, but
treat it as a template rather than a working integration.
"""

from __future__ import annotations

from typing import Any

from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema


class Cryocon14CAdapter(AdapterBase):
    """Cryocon 14C temperature controller adapter."""

    def __init__(self, port: str, name: str = "cryocon_14c") -> None:
        super().__init__()
        self._port = port
        self._name = name
        self._controller = None  # Generic placeholder

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"temperature": "float64"},
            settable={"setpoint": "float64"},
            units={"temperature": "K", "setpoint": "K"},
            limits={"temperature": (1.4, 400.0), "setpoint": (1.4, 400.0)},
            tags=["Cryocon", "temperature", "14C", "controller"],
        )

    def _connect_sync(self) -> None:
        # Placeholder - would need actual Cryocon driver
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        if self._controller is None:
            raise RuntimeError("Not connected")
        # Placeholder implementation
        return {"temperature": 300.0}


adapter_registry.register("cryocon_14c", Cryocon14CAdapter)
