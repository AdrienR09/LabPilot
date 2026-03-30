"""Power meter adapters for pylablib.

Supports optical power meters.

Supported devices:
- Ophir power meters
- Thorlabs PM160 power meter

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Ophir, Thorlabs
except ImportError:
    Ophir = None
    Thorlabs = None

if Ophir is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class OphirAdapter(AdapterBase):
        """Ophir power meter adapter."""

        def __init__(self, port: str, name: str = "ophir") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._meter: Ophir.OphirPowerMeter | None = None

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
            self._meter = Ophir.OphirPowerMeter(self._port)

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

    class ThorlabsPM160Adapter(AdapterBase):
        """Thorlabs PM160 power meter adapter."""

        def __init__(self, port: str, name: str = "thorlabs_pm160") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._meter: Thorlabs.PM160 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"power": "float64"},
                settable={"wavelength": "float64"},
                units={"power": "W", "wavelength": "nm"},
                limits={"wavelength": (200.0, 2000.0)},
                tags=["Thorlabs", "power_meter", "PM160"],
            )

        def _connect_sync(self) -> None:
            self._meter = Thorlabs.PM160(self._port)

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
    adapter_registry.register("thorlabs_pm160", ThorlabsPM160Adapter)
