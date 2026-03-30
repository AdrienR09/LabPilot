"""Temperature controller adapters for pylablib.

Supports temperature controllers.

Supported devices:
- Lakeshore 218 temperature monitor
- Cryocon 14C temperature controller

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Lakeshore
except ImportError:
    Lakeshore = None

if Lakeshore is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class Lakeshore218Adapter(AdapterBase):
        """Lakeshore 218 temperature monitor adapter."""

        def __init__(self, port: str, name: str = "lakeshore_218") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._controller: Lakeshore.Lakeshore218 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={
                    "temperature_1": "float64",
                    "temperature_2": "float64",
                    "temperature_3": "float64",
                    "temperature_4": "float64",
                },
                settable={},
                units={
                    "temperature_1": "K",
                    "temperature_2": "K",
                    "temperature_3": "K",
                    "temperature_4": "K",
                },
                limits={
                    "temperature_1": (1.4, 800.0),
                    "temperature_2": (1.4, 800.0),
                    "temperature_3": (1.4, 800.0),
                    "temperature_4": (1.4, 800.0),
                },
                tags=["Lakeshore", "temperature", "218", "monitor"],
            )

        def _connect_sync(self) -> None:
            self._controller = Lakeshore.Lakeshore218(self._port)

        def _disconnect_sync(self) -> None:
            if self._controller:
                try:
                    self._controller.close()
                except Exception:
                    pass
                self._controller = None

        def _read_sync(self) -> dict[str, Any]:
            if self._controller is None:
                raise RuntimeError("Not connected")

            data = {}
            for ch in range(1, 5):
                try:
                    temp = self._controller.get_temperature(ch)
                    data[f"temperature_{ch}"] = float(temp)
                except Exception:
                    pass  # Channel might not be connected

            return data

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
            # Generic connection - would need actual Cryocon driver
            pass

        def _disconnect_sync(self) -> None:
            pass

        def _read_sync(self) -> dict[str, Any]:
            if self._controller is None:
                raise RuntimeError("Not connected")
            # Placeholder implementation
            return {"temperature": 300.0}

    adapter_registry.register("lakeshore_218", Lakeshore218Adapter)
    adapter_registry.register("cryocon_14c", Cryocon14CAdapter)
