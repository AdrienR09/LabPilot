"""Auto-generated PyMeasure adapters for newport instruments (actuator_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.newport classes, verified against the installed
pymeasure library. Type classification ("actuator_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.newport.esp300 import ESP300
except ImportError:
    ESP300 = None

if ESP300 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ESP300Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.newport.esp300.ESP300."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ESP300, resource=resource, name=name or "pymeasure_e_s_p300", **kwargs)

    adapter_registry.register("pymeasure_e_s_p300", ESP300Adapter)



# --- merged from pylablib/stages/newport.py ---
"""Newport stage adapters for pylablib.

Supports Newport motion controllers.

Supported devices:
- Picomotor 8742 controller

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""


from typing import Any

try:
    from pylablib.devices import Newport
except ImportError:
    Newport = None

if Newport is not None:
    from instruments._base import AdapterBase, adapter_registry
    from core.device.protocols import Movable
    from core.device.schema import DeviceSchema

    class Picomotor8742Adapter(AdapterBase, Movable):
        """Newport Picomotor 8742 controller adapter."""

        def __init__(self, port: str, axis: int = 1, name: str = "picomotor_8742") -> None:
            super().__init__()
            self._port = port
            self._axis = axis
            self._name = name
            self._controller: Newport.Picomotor8742 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "int32"},
                settable={"position": "int32"},
                units={"position": "steps"},
                limits={"position": (-2147483648, 2147483647)},
                tags=["Newport", "Picomotor", "8742"],
            )

        def _connect_sync(self) -> None:
            self._controller = Newport.Picomotor8742(self._port)

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
            return {"position": int(pos)}

        def _set_sync(self, value: int) -> None:
            if self._controller is None:
                raise RuntimeError("Not connected")
            self._controller.move_to(self._axis, value)
            self._controller.wait_for_stop(self._axis)

        async def set(self, value: Any, *, timeout: float = 10.0) -> None:
            await self._to_thread(self._set_sync, int(value))

        def _where_sync(self) -> int:
            if self._controller is None:
                raise RuntimeError("Not connected")
            return int(self._controller.get_position(self._axis))

        async def where(self) -> Any:
            return await self._to_thread(self._where_sync)

        def _stop_sync(self) -> None:
            if self._controller:
                self._controller.stop(self._axis)

        async def stop(self) -> None:
            await self._to_thread(self._stop_sync)

    adapter_registry.register("newport_picomotor_8742", Picomotor8742Adapter)
