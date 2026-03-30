"""Wavemeter adapters for pylablib.

Supports optical wavemeters.

Supported devices:
- HighFinesse WS6 wavemeter

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import HighFinesse
except ImportError:
    HighFinesse = None

if HighFinesse is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class HighFinesseWS6Adapter(AdapterBase):
        """HighFinesse WS6 wavemeter adapter.

        Precision wavemeter with:
        - Wavelength range: 350-1100 nm
        - Accuracy: ±0.002 nm
        - USB interface

        Args:
            name: Device name.
        """

        def __init__(self, name: str = "wavemeter_ws6") -> None:
            super().__init__()
            self._name = name
            self._wavemeter: HighFinesse.WS6 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"wavelength": "float64", "frequency": "float64"},
                settable={},
                units={"wavelength": "nm", "frequency": "THz"},
                limits={"wavelength": (350.0, 1100.0)},
                tags=["HighFinesse", "wavemeter", "WS6"],
            )

        def _connect_sync(self) -> None:
            self._wavemeter = HighFinesse.WS6()

        def _disconnect_sync(self) -> None:
            if self._wavemeter:
                try:
                    self._wavemeter.close()
                except Exception:
                    pass
                self._wavemeter = None

        def _read_sync(self) -> dict[str, Any]:
            if self._wavemeter is None:
                raise RuntimeError("Not connected")

            wl = self._wavemeter.get_wavelength()
            freq = self._wavemeter.get_frequency()

            return {
                "wavelength": float(wl),
                "frequency": float(freq),
            }

    adapter_registry.register("highfinesse_ws6", HighFinesseWS6Adapter)
