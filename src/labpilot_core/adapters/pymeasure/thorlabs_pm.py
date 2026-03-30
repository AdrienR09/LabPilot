"""Thorlabs power meter adapters.

Wraps PyMeasure Thorlabs instruments with accurate DeviceSchema.

Supported instruments:
- Thorlabs PM100 series power/energy meters

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.thorlabs import PM100USB
except ImportError:
    PM100USB = None

if PM100USB is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class ThorlabsPM100Adapter(AdapterBase):
        """Thorlabs PM100 power meter adapter.

        Optical power/energy meter with:
        - Power range: 50 nW - 200 mW (sensor dependent)
        - Wavelength: 200 - 11000 nm
        - USB interface

        Args:
            resource: VISA resource string (USB).
            name: Device name.
        """

        def __init__(self, resource: str, name: str = "thorlabs_pm100") -> None:
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: PM100USB | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"power": "float64"},
                settable={"wavelength": "float64"},
                units={"power": "W", "wavelength": "nm"},
                limits={
                    "power": (50e-9, 0.2),
                    "wavelength": (200.0, 11000.0),
                },
                tags=["Thorlabs", "power_meter", "PM100", "VISA", "USB"],
            )

        def _connect_sync(self) -> None:
            self._instrument = PM100USB(self._resource)

        def _disconnect_sync(self) -> None:
            if self._instrument:
                try:
                    self._instrument.shutdown()
                except Exception:
                    pass
                self._instrument = None

        def _read_sync(self) -> dict[str, Any]:
            if self._instrument is None:
                raise RuntimeError("Not connected")

            return {"power": float(self._instrument.power)}

    adapter_registry.register("thorlabs_pm100", ThorlabsPM100Adapter)
