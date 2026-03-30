"""PI (Physik Instrumente) stage adapters for pylablib.

Supports PI piezo controllers.

Supported devices:
- PIE516 piezo controller

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import PI
except ImportError:
    PI = None

if PI is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Movable
    from labpilot_core.device.schema import DeviceSchema

    class PIE516Adapter(AdapterBase, Movable):
        """PI E516 piezo controller adapter."""

        def __init__(self, port: str, axis: int = 1, name: str = "pi_e516") -> None:
            super().__init__()
            self._port = port
            self._axis = axis
            self._name = name
            self._controller: PI.E516 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "float64"},
                settable={"position": "float64"},
                units={"position": "µm"},
                limits={"position": (0.0, 100.0)},
                tags=["PI", "piezo", "E516"],
            )

        def _connect_sync(self) -> None:
            self._controller = PI.E516(self._port)

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

    adapter_registry.register("pi_e516", PIE516Adapter)
