"""Pressure sensor adapters for pylablib.

Supports vacuum pressure gauges.

Supported devices:
- Pfeiffer TPG261 pressure gauge

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Pfeiffer
except ImportError:
    Pfeiffer = None

if Pfeiffer is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class PfeifferTPG261Adapter(AdapterBase):
        """Pfeiffer TPG261 pressure gauge adapter.

        Vacuum pressure measurement with:
        - Pressure range: 10^-9 to 10^3 mbar
        - Multiple gauge types (Pirani, cold cathode)
        - RS232/RS485 interface

        Args:
            port: Serial port (e.g., "COM3", "/dev/ttyUSB0").
            name: Device name.
        """

        def __init__(self, port: str, name: str = "pfeiffer_tpg261") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._gauge: Pfeiffer.TPG261 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={
                    "pressure_1": "float64",
                    "pressure_2": "float64",
                },
                settable={},
                units={
                    "pressure_1": "mbar",
                    "pressure_2": "mbar",
                },
                limits={
                    "pressure_1": (1e-9, 1e3),
                    "pressure_2": (1e-9, 1e3),
                },
                tags=["Pfeiffer", "pressure", "TPG261", "vacuum"],
            )

        def _connect_sync(self) -> None:
            self._gauge = Pfeiffer.TPG261(self._port)

        def _disconnect_sync(self) -> None:
            if self._gauge:
                try:
                    self._gauge.close()
                except Exception:
                    pass
                self._gauge = None

        def _read_sync(self) -> dict[str, Any]:
            if self._gauge is None:
                raise RuntimeError("Not connected")

            data = {}
            try:
                p1 = self._gauge.get_pressure(1)
                data["pressure_1"] = float(p1)
            except Exception:
                pass

            try:
                p2 = self._gauge.get_pressure(2)
                data["pressure_2"] = float(p2)
            except Exception:
                pass

            return data

    adapter_registry.register("pfeiffer_tpg261", PfeifferTPG261Adapter)
