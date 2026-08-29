"""Ophir power meter adapter (pylablib backend).

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Ophir
except ImportError:
    Ophir = None

if Ophir is not None:
    from instruments._base import AdapterBase, adapter_registry
    from core.device.schema import DeviceSchema

    class OphirAdapter(AdapterBase):
        """Ophir power meter adapter."""

        def __init__(self, port: str, name: str = "ophir") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._meter: Ophir.VegaPowerMeter | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"power": "float64"},
                settable={"wavelength": "float64"},
                units={"power": "W", "wavelength": "nm"},
                limits={"wavelength": (200.0, 2000.0)},
                tags=["Ophir", "power_meter"],
            )

        def _connect_sync(self) -> None:
            # pylablib's real class is VegaPowerMeter (OphirDevice is
            # the base class, not directly usable) — verified against
            # the installed package.
            self._meter = Ophir.VegaPowerMeter(self._port)

        def _disconnect_sync(self) -> None:
            if self._meter:
                try:
                    self._meter.close()
                except Exception:
                    pass
                self._meter = None

        def _read_sync(self) -> dict[str, Any]:
            if self._meter is None:
                raise RuntimeError("Not connected")
            return {"power": float(self._meter.get_power())}

    adapter_registry.register("ophir", OphirAdapter)
