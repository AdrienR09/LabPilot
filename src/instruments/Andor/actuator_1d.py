"""Andor Shamrock spectrograph adapter for pylablib.

The Shamrock is a motorized grating monochromator/spectrograph, typically
paired with an Andor camera (see `detector_2d.py` in this package) as the
dispersive element in a grating-based spectrometer — exactly the
"grating_actuator" role in `core/workflow_templates/grating_spectrometer.py`.

Modeled as a 1D actuator: its "position" is the center wavelength, moved
by `set_wavelength`/read via `get_wavelength`, matching how every other
ACTUATOR_1D adapter in this codebase exposes a scalar "position".

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Andor
except ImportError:
    Andor = None

if Andor is not None:
    from instruments._base import AdapterBase, adapter_registry
    from core.device.schema import DeviceSchema

    # Standard input slit index on a Shamrock — verified against
    # pylablib's ShamrockSpectrograph.{get,set}_slit_width(slit, ...)
    # signature (slit is a required index, 1 = input side slit on every
    # real Shamrock model).
    _INPUT_SLIT = 1

    class ShamrockSpectrographAdapter(AdapterBase):
        """Andor Shamrock spectrograph adapter.

        Args:
            camera_index: Shamrock unit index (default 0 — almost always
                correct for a single spectrograph).
            name: Device name.
        """

        def __init__(self, camera_index: int = 0, name: str = "shamrock") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._spectrograph: Andor.ShamrockSpectrograph | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "float64", "grating": "int32"},
                settable={"position": "float64", "grating": "int32", "slit_width": "float64"},
                units={"position": "nm", "slit_width": "μm"},
                limits={"position": (0.0, 1400.0)},  # typical Shamrock range; real limits vary by grating
                tags=["Andor", "Shamrock", "spectrograph", "monochromator", "grating"],
            )

        def _connect_sync(self) -> None:
            self._spectrograph = Andor.ShamrockSpectrograph(idx=self._camera_index)

        def _disconnect_sync(self) -> None:
            if self._spectrograph is not None:
                try:
                    self._spectrograph.close()
                except Exception:
                    pass
                self._spectrograph = None

        def _read_sync(self) -> dict[str, Any]:
            if self._spectrograph is None:
                raise RuntimeError("Not connected")
            return {
                "position": float(self._spectrograph.get_wavelength()),
                "grating": int(self._spectrograph.get_grating()),
            }

        async def set_position(self, value: float) -> None:
            if self._spectrograph is None:
                raise RuntimeError("Not connected")
            await self._to_thread(self._spectrograph.set_wavelength, float(value))

        async def set_grating(self, value: int) -> None:
            if self._spectrograph is None:
                raise RuntimeError("Not connected")
            await self._to_thread(self._spectrograph.set_grating, int(value))

        async def set_slit_width(self, value: float) -> None:
            if self._spectrograph is None:
                raise RuntimeError("Not connected")
            await self._to_thread(self._spectrograph.set_slit_width, _INPUT_SLIT, float(value))

        def _self_test_sync(self) -> None:
            if self._spectrograph is None:
                raise RuntimeError("Not connected")
            _ = self._spectrograph.get_wavelength()

    adapter_registry.register("andor_shamrock", ShamrockSpectrographAdapter)
