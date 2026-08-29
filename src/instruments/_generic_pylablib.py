"""Generic pylablib wrappers, one per device category with a genuinely
uniform API — unlike pymeasure's `Instrument`, pylablib devices don't share
one common base across all categories, so this is scoped to the two
categories that do: cameras (`interface.camera.ICamera`) and stages with a
`get_position()`/`move_to()` pair (most, not all — see catalog.py notes).

Do NOT extend this pattern to other pylablib categories (sensors, lasers,
sources) without verifying the target classes actually share the method
names used here — pylablib's device APIs are otherwise heterogeneous per
manufacturer (verified via introspection, not assumed).
"""

from __future__ import annotations

from typing import Any

from instruments._base import AdapterBase, adapter_registry
from core.device.schema import DeviceSchema


class PylablibCameraAdapter(AdapterBase):
    """Wraps any pylablib camera class implementing `interface.camera.ICamera`.

    Args:
        device_class: The pylablib camera class (e.g. `Andor.AndorSDK2Camera`).
        name: Device name.
        **device_kwargs: Passed to the camera class constructor (e.g.
            `idx=0`, `serial=...`, `cam_id=...` — varies per manufacturer).
    """

    def __init__(self, device_class: type, name: str | None = None, **device_kwargs: Any) -> None:
        super().__init__()
        self._device_class = device_class
        self._device_kwargs = device_kwargs
        self._name = name or f"pylablib_{device_class.__name__.lower()}"
        self._device = None

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={"image": "ndarray2d"},
            settable={},
            units={"image": "counts"},
            tags=["pylablib", self._device_class.__name__, "camera"],
        )

    def _connect_sync(self) -> None:
        self._device = self._device_class(**self._device_kwargs)
        if hasattr(self._device, "open") and not self._device.is_opened():
            self._device.open()

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
        return {"image": self._device.snap()}


class PylablibStageAdapter(AdapterBase):
    """Wraps any pylablib stage class exposing `get_position()`/`move_to()`.

    Not all pylablib stage classes share this pair (some are `move_by()`-only
    relative actuators, or use entirely different APIs) — only register
    classes verified to have both. See catalog.py for the verified list.

    Args:
        device_class: The pylablib stage class (e.g. `Thorlabs.KinesisMotor`).
        name: Device name.
        **device_kwargs: Passed to the stage class constructor (e.g.
            `conn=...`, `serial=...` — varies per manufacturer).
    """

    def __init__(self, device_class: type, name: str | None = None, **device_kwargs: Any) -> None:
        super().__init__()
        self._device_class = device_class
        self._device_kwargs = device_kwargs
        self._name = name or f"pylablib_{device_class.__name__.lower()}"
        self._device = None

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={"position": "float64"},
            settable={"position": "float64"},
            units={"position": "steps"},
            tags=["pylablib", self._device_class.__name__, "stage"],
        )

    def _connect_sync(self) -> None:
        self._device = self._device_class(**self._device_kwargs)
        if hasattr(self._device, "open") and not self._device.is_opened():
            self._device.open()

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
        return {"position": float(self._device.get_position())}

    # --- Movable protocol (core.device.protocols.Movable) ---

    async def set(self, value: Any, *, timeout: float = 10.0) -> None:
        """Move to target position and wait for completion."""
        if self._device is None:
            raise RuntimeError("Not connected")

        def _move() -> None:
            self._device.move_to(value)
            if hasattr(self._device, "wait_move"):
                self._device.wait_move(timeout=timeout)

        await self._to_thread(_move)

    async def set_position(self, value: float) -> None:
        """Alias for set() under the schema's own key name — the generic
        write() dispatch (AdapterBase.write) looks for set_<key> per
        schema.settable key ("position" here), which set() alone doesn't
        satisfy even though it's the same operation. Without this, every
        adapter built on PylablibStageAdapter would raise NotImplementedError
        the moment anything (e.g. a workflow script's `motor.write(...)`)
        tried to move it — found via generic_params.validate_write_dispatch."""
        await self.set(value)

    async def stop(self) -> None:
        """Halt any in-progress motion, if the device supports it."""
        if self._device is not None and hasattr(self._device, "stop"):
            await self._to_thread(self._device.stop)

    async def where(self) -> float:
        """Get current position."""
        data = await self.read()
        return data["position"]


class PylablibAWGAdapter(AdapterBase):
    """Wraps any pylablib.devices.AWG function-generator class — they all
    share GenericAWG's frequency/amplitude/offset/output-enable API
    (verified directly against the installed package: every AWG.* class
    subclasses GenericAWG, and its methods all default `channel=None`, so
    single-channel use needs no extra config).

    Args:
        device_class: The pylablib AWG class (e.g. `AWG.RigolDG1000`).
        name: Device name.
        **device_kwargs: Passed to the class constructor (typically `addr=`,
            a VISA resource string).
    """

    def __init__(self, device_class: type, name: str | None = None, **device_kwargs: Any) -> None:
        super().__init__()
        self._device_class = device_class
        self._device_kwargs = device_kwargs
        self._name = name or f"pylablib_{device_class.__name__.lower()}"
        self._device = None

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={"frequency": "float64", "amplitude": "float64", "offset": "float64", "enabled": "bool"},
            settable={"frequency": "float64", "amplitude": "float64", "offset": "float64", "enabled": "bool"},
            units={"frequency": "Hz", "amplitude": "V", "offset": "V"},
            tags=["pylablib", self._device_class.__name__, "awg", "function-generator"],
        )

    def _connect_sync(self) -> None:
        self._device = self._device_class(**self._device_kwargs)

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
            "frequency": float(self._device.get_frequency()),
            "amplitude": float(self._device.get_amplitude()),
            "offset": float(self._device.get_offset()),
            "enabled": bool(self._device.is_output_enabled()),
        }

    async def set_frequency(self, value: float) -> None:
        if self._device is None:
            raise RuntimeError("Not connected")
        await self._to_thread(self._device.set_frequency, float(value))

    async def set_amplitude(self, value: float) -> None:
        if self._device is None:
            raise RuntimeError("Not connected")
        await self._to_thread(self._device.set_amplitude, float(value))

    async def set_offset(self, value: float) -> None:
        if self._device is None:
            raise RuntimeError("Not connected")
        await self._to_thread(self._device.set_offset, float(value))

    async def set_enabled(self, value: bool) -> None:
        if self._device is None:
            raise RuntimeError("Not connected")
        await self._to_thread(self._device.enable_output, bool(value))
