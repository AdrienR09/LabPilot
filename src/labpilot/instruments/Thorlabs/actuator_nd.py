"""Thorlabs MDT69xA open-loop piezo controller adapter for pylablib.

3-channel (X/Y/Z) high-voltage piezo driver — common for beam-steering
mirrors, piezo stages, and nanopositioning stacks. Modeled as an
ACTUATOR_ND, matching the existing xyz-stage convention (settable x/y/z
keys) rather than MotorMixin's single-"position" convention.

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Thorlabs
except ImportError:
    Thorlabs = None

if Thorlabs is not None:
    from labpilot.core.device.schema import DeviceSchema
    from labpilot.instruments._base import AdapterBase, adapter_registry

    class MDT69xAAdapter(AdapterBase):
        """Thorlabs MDT69xA piezo controller adapter.

        Args:
            conn: Serial port (e.g. "COM5").
            voltage_range: (min, max) volts — verified per-model via
                Thorlabs.MDT69xA.get_voltage_range(); 0-150V is the common
                default across the MDT693A/694A family.
            name: Device name.
        """

        def __init__(
            self, conn: str, voltage_range: tuple[float, float] = (0.0, 150.0), name: str = "mdt69xa"
        ) -> None:
            super().__init__()
            self._conn = conn
            self._voltage_range = voltage_range
            self._name = name
            self._device: Thorlabs.MDT69xA | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"x": "float64", "y": "float64", "z": "float64"},
                settable={"x": "float64", "y": "float64", "z": "float64"},
                units={"x": "V", "y": "V", "z": "V"},
                limits={"x": self._voltage_range, "y": self._voltage_range, "z": self._voltage_range},
                tags=["Thorlabs", "MDT69xA", "piezo", "controller"],
            )

        def _connect_sync(self) -> None:
            self._device = Thorlabs.MDT69xA(self._conn)

        def _disconnect_sync(self) -> None:
            if self._device is not None:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None

        def _read_sync(self) -> dict[str, Any]:
            if self._device is None:
                raise RuntimeError("Not connected")
            return {
                "x": float(self._device.get_voltage(channel="x")),
                "y": float(self._device.get_voltage(channel="y")),
                "z": float(self._device.get_voltage(channel="z")),
            }

        async def _set_channel(self, channel: str, value: float) -> None:
            if self._device is None:
                raise RuntimeError("Not connected")
            await self._to_thread(self._device.set_voltage, float(value), channel=channel)

        async def set_x(self, value: float) -> None:
            await self._set_channel("x", value)

        async def set_y(self, value: float) -> None:
            await self._set_channel("y", value)

        async def set_z(self, value: float) -> None:
            await self._set_channel("z", value)

        def _self_test_sync(self) -> None:
            if self._device is None:
                raise RuntimeError("Not connected")
            _ = self._device.get_id()

    adapter_registry.register("thorlabs_mdt69xa", MDT69xAAdapter)
