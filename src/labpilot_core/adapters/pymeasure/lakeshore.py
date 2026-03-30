"""Lakeshore temperature controller adapters.

Wraps PyMeasure Lakeshore instruments with accurate DeviceSchema.

Supported instruments:
- Lakeshore 336 temperature controller

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.lakeshore import LakeShore336
except ImportError:
    LakeShore336 = None

if LakeShore336 is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class Lakeshore336Adapter(AdapterBase):
        """Lakeshore 336 temperature controller adapter.

        4-channel cryogenic temperature controller with:
        - Temperature range: 300 mK - 1500 K
        - 4 sensor inputs
        - 2 heater outputs (50W each)
        - PID control

        Args:
            resource: VISA resource string.
            channel: Sensor channel (A, B, C, or D).
            name: Device name.
        """

        def __init__(
            self, resource: str, channel: str = "A", name: str = "lakeshore_336"
        ) -> None:
            super().__init__()
            self._resource = resource
            self._channel = channel
            self._name = name
            self._instrument: LakeShore336 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"temperature": "float64"},
                settable={"setpoint": "float64", "heater_range": "int32"},
                units={"temperature": "K", "setpoint": "K"},
                limits={"setpoint": (0.3, 1500.0), "heater_range": (0, 5)},
                tags=["Lakeshore", "temperature", "cryogenic", "VISA", "GPIB"],
            )

        def _connect_sync(self) -> None:
            self._instrument = LakeShore336(self._resource)

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

            # Read temperature from specified channel
            temp = getattr(self._instrument, f"temperature_{self._channel}")
            return {"temperature": float(temp)}

    adapter_registry.register("lakeshore_336", Lakeshore336Adapter)
