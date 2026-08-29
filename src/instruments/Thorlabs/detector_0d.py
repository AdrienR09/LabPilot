"""Thorlabs power meter adapters.

Wraps PyMeasure Thorlabs instruments with accurate DeviceSchema.

Supported instruments:
- Thorlabs PM100 series power/energy meters

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.thorlabs import ThorlabsPM100USB
except ImportError:
    ThorlabsPM100USB = None

if ThorlabsPM100USB is not None:
    from instruments._base import AdapterBase, adapter_registry
    from core.device.schema import DeviceSchema

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
            self._instrument: ThorlabsPM100USB | None = None

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
            self._instrument = ThorlabsPM100USB(self._resource)

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

        async def set_wavelength(self, value: float) -> None:
            if self._instrument is None:
                raise RuntimeError("Not connected")
            await self._to_thread(setattr, self._instrument, "wavelength", float(value))

    adapter_registry.register("thorlabs_pm100", ThorlabsPM100Adapter)


# --- merged from pylablib/sensors/powermeters.py ---
try:
    from pylablib.devices import Thorlabs as _ThorlabsPylablib
except ImportError:
    _ThorlabsPylablib = None

if _ThorlabsPylablib is not None:
    from instruments._base import AdapterBase as _AdapterBase, adapter_registry as _adapter_registry
    from core.device.schema import DeviceSchema as _DeviceSchema

    class ThorlabsPM160Adapter(_AdapterBase):
        """Thorlabs PM160 power meter adapter (pylablib backend)."""

        def __init__(self, port: str, name: str = "thorlabs_pm160") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._meter = None

        @property
        def schema(self) -> _DeviceSchema:
            return _DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"power": "float64"},
                settable={"wavelength": "float64"},
                units={"power": "W", "wavelength": "nm"},
                limits={"wavelength": (200.0, 2000.0)},
                tags=["Thorlabs", "power_meter", "PM160"],
            )

        def _connect_sync(self) -> None:
            self._meter = _ThorlabsPylablib.PM160(self._port)

        def _disconnect_sync(self) -> None:
            if self._meter:
                try:
                    self._meter.close()
                except Exception:
                    pass
                self._meter = None

        def _read_sync(self):
            if self._meter is None:
                raise RuntimeError("Not connected")
            return {"power": float(self._meter.get_power())}

    _adapter_registry.register("thorlabs_pm160", ThorlabsPM160Adapter)
