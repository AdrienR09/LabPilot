"""Attocube stage adapters for pylablib.

Supports Attocube positioner controllers.

Supported devices:
- ANC300 piezo controller
- ANC350 piezo controller

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Attocube
except ImportError:
    Attocube = None

if Attocube is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Movable
    from labpilot_core.device.schema import DeviceSchema

    class ANC300Adapter(AdapterBase, Movable):
        """Attocube ANC300 piezo controller adapter."""

        def __init__(self, port: str, axis: int = 0, name: str = "anc300") -> None:
            super().__init__()
            self._port = port
            self._axis = axis
            self._name = name
            self._controller: Attocube.ANC300 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "float64"},
                settable={"position": "float64"},
                units={"position": "µm"},
                limits={"position": (0.0, 50.0)},
                tags=["Attocube", "piezo", "ANC300"],
            )

        def _connect_sync(self) -> None:
            self._controller = Attocube.ANC300(self._port)

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
            pos = self._controller.get_position(self._axis)
            return {"position": float(pos)}

        def _set_sync(self, value: float) -> None:
            if self._controller is None:
                raise RuntimeError("Not connected")
            self._controller.move_to(self._axis, value)
            self._controller.wait_for_stop(self._axis)

        async def set(self, value: Any, *, timeout: float = 10.0) -> None:
            await self._to_thread(self._set_sync, float(value))

        def _where_sync(self) -> float:
            if self._controller is None:
                raise RuntimeError("Not connected")
            return float(self._controller.get_position(self._axis))

        async def where(self) -> Any:
            return await self._to_thread(self._where_sync)

        def _stop_sync(self) -> None:
            if self._controller:
                self._controller.stop(self._axis)

        async def stop(self) -> None:
            await self._to_thread(self._stop_sync)

    class ANC350Adapter(AdapterBase, Movable):
        """Attocube ANC350 piezo controller adapter."""

        def __init__(self, serial: str, axis: int = 0, name: str = "anc350") -> None:
            super().__init__()
            self._serial = serial
            self._axis = axis
            self._name = name
            self._controller: Attocube.ANC350 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "float64"},
                settable={"position": "float64"},
                units={"position": "µm"},
                limits={"position": (0.0, 50.0)},
                tags=["Attocube", "piezo", "ANC350"],
            )

        def _connect_sync(self) -> None:
            self._controller = Attocube.ANC350(self._serial)

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
            pos = self._controller.get_position(self._axis)
            return {"position": float(pos)}

        def _set_sync(self, value: float) -> None:
            if self._controller is None:
                raise RuntimeError("Not connected")
            self._controller.move_to(self._axis, value)
            self._controller.wait_for_stop(self._axis)

        async def set(self, value: Any, *, timeout: float = 10.0) -> None:
            await self._to_thread(self._set_sync, float(value))

        def _where_sync(self) -> float:
            if self._controller is None:
                raise RuntimeError("Not connected")
            return float(self._controller.get_position(self._axis))

        async def where(self) -> Any:
            return await self._to_thread(self._where_sync)

        def _stop_sync(self) -> None:
            if self._controller:
                self._controller.stop(self._axis)

        async def stop(self) -> None:
            await self._to_thread(self._stop_sync)

    adapter_registry.register("attocube_anc300", ANC300Adapter)
    adapter_registry.register("attocube_anc350", ANC350Adapter)
