"""Keysight/Agilent instrument adapters.

Wraps PyMeasure Keysight instruments with accurate DeviceSchema.

Supported instruments:
- Keysight B2900 series SMU (Source Measure Unit)

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.agilent import AgilentB2902A
except ImportError:
    AgilentB2902A = None

if AgilentB2902A is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class KeysightB2901Adapter(AdapterBase):
        """Keysight B2901A SMU adapter.

        Precision source-measure unit with:
        - Voltage: ±210V, 10.5W
        - Current: ±3A, 10.5W
        - 6.5-digit resolution

        Args:
            resource: VISA resource string.
            name: Device name.
        """

        def __init__(self, resource: str, name: str = "keysight_b2901") -> None:
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: AgilentB2902A | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={"voltage": "float64", "current": "float64"},
                settable={
                    "voltage": "float64",
                    "current": "float64",
                    "compliance_current": "float64",
                    "compliance_voltage": "float64",
                },
                units={
                    "voltage": "V",
                    "current": "A",
                    "compliance_current": "A",
                    "compliance_voltage": "V",
                },
                limits={
                    "voltage": (-210.0, 210.0),
                    "current": (-3.0, 3.0),
                    "compliance_current": (1e-9, 3.0),
                    "compliance_voltage": (0.2, 210.0),
                },
                tags=["Keysight", "Agilent", "SMU", "B2900", "VISA"],
            )

        def _connect_sync(self) -> None:
            self._instrument = AgilentB2902A(self._resource)
            self._instrument.reset()

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

            return {
                "voltage": float(self._instrument.voltage),
                "current": float(self._instrument.current),
            }

    adapter_registry.register("keysight_b2901", KeysightB2901Adapter)
