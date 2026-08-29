"""Auto-generated PyMeasure adapters for toptica instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.toptica classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.toptica.ibeamsmart import IBeamSmart
except ImportError:
    IBeamSmart = None

if IBeamSmart is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class IBeamSmartAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.toptica.ibeamsmart.IBeamSmart."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=IBeamSmart, resource=resource, name=name or "pymeasure_i_beam_smart", **kwargs)

    adapter_registry.register("pymeasure_i_beam_smart", IBeamSmartAdapter)



# --- merged from pylablib/lasers/toptica.py ---
"""Toptica laser adapters for pylablib.

Supports Toptica lasers.

Supported lasers:
- iBeam Smart (diode laser)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""


from typing import Any

try:
    from pylablib.devices import Toptica
except ImportError:
    Toptica = None

if Toptica is not None:
    from instruments._base import AdapterBase, adapter_registry
    from core.device.schema import DeviceSchema

    class TopticaIBeamSmartAdapter(AdapterBase):
        """Toptica iBeam Smart diode laser adapter."""

        def __init__(self, port: str, name: str = "toptica_ibeam") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._laser: Toptica.TopticaIBeam | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={"power": "float64", "enabled": "bool"},
                settable={"power": "float64", "enabled": "bool"},
                units={"power": "mW"},
                limits={"power": (0.0, 200.0)},
                tags=["Toptica", "laser", "iBeam", "diode"],
            )

        def _connect_sync(self) -> None:
            # pylablib's real class is TopticaIBeam, not IBeamSmart (which
            # doesn't exist in pylablib.devices.Toptica — verified against
            # the installed package).
            self._laser = Toptica.TopticaIBeam(self._port)

        def _disconnect_sync(self) -> None:
            if self._laser:
                try:
                    self._laser.close()
                except Exception:
                    pass
                self._laser = None

        def _read_sync(self) -> dict[str, Any]:
            if self._laser is None:
                raise RuntimeError("Not connected")

            return {
                "power": float(self._laser.get_power()),
                "enabled": bool(self._laser.is_enabled()),
            }

    adapter_registry.register("toptica_ibeam_smart", TopticaIBeamSmartAdapter)
