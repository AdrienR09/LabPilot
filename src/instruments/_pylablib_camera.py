"""Shared, capability-gated setters for the hand-written pylablib camera
adapters (Andor, Basler, Hamamatsu, Photometrics, Princeton, Thorlabs).

Why this exists: `AdapterBase.write()` dispatches `{"exposure": 0.1}` to a
`set_exposure()` coroutine by naming convention (instruments/_base.py). Six
camera adapters declared `exposure`/`gain`/`roi`/... as settable — complete
with units and limits, so the GUI rendered controls for them — while
implementing none of the matching setters, so every one of those writes
raised `NotImplementedError` at runtime. `generic_params.validate_write_dispatch`
detects exactly that and is now run over the whole registry by
`tests/test_adapter_contracts.py`.

Each method below delegates to a method pylablib genuinely provides, checked
against the installed pylablib (1.4.3) per camera class rather than assumed:
`set_exposure`/`set_roi`/`set_temperature`/`set_frame_period` come from the
`IExposureCamera`/`IROICamera` interfaces or the concrete class, and `gain`
falls back to the GenICam-style attribute interface (`IAttributeCamera`) for
the cameras that expose it that way and nothing more specific.

An adapter must only declare a key settable if its camera class actually
supports it — mixing this in does not make a capability appear. Where the
underlying class had no route at all (DCAM frame rate, which is derived from
exposure, not set directly) the declaration was removed instead.

Expects the host adapter to hold its open camera on `self._camera` and to
provide `AdapterBase._to_thread`.
"""

from __future__ import annotations

from typing import Any

__all__ = ["PylablibCameraControls"]

# Vendor attribute names, most specific first, consulted only when the camera
# class exposes no dedicated method for the same setting.
_GAIN_ATTRS = ("Gain", "GAIN", "gain", "AnalogGain")
_TEMPERATURE_ATTRS = (
    "SensorTemperatureSetPoint",  # Picam
    "TargetSensorTemperature",
    "SENSOR TEMPERATURE TARGET",  # DCAM-style, space-separated
    "Temperature",
)


class PylablibCameraControls:
    """Mixin supplying the `set_<key>` coroutines `AdapterBase.write()`
    dispatches to. Mix in *before* `AdapterBase` so these win over nothing
    in particular — they are additive, not overrides."""

    def _camera_or_raise(self) -> Any:
        camera = getattr(self, "_camera", None)
        if camera is None:
            raise RuntimeError(
                f"{type(self).__name__} is not connected — call connect() before writing settings"
            )
        return camera

    async def set_exposure(self, value: float) -> None:
        """Exposure time, in seconds (pylablib's own unit for `set_exposure`)."""
        camera = self._camera_or_raise()
        await self._to_thread(camera.set_exposure, float(value))

    async def set_roi(self, value: tuple) -> None:
        """Region of interest as `(hstart, hend, vstart, vend)`, splatted into
        pylablib's positional `set_roi` signature."""
        camera = self._camera_or_raise()
        await self._to_thread(lambda: camera.set_roi(*tuple(value)))

    async def set_temperature(self, value: float) -> None:
        """Target sensor temperature, in °C. Andor exposes a dedicated
        `set_temperature`; Picam only reaches it through the attribute
        interface, so both routes are tried before giving up."""
        camera = self._camera_or_raise()

        if hasattr(camera, "set_temperature"):
            await self._to_thread(camera.set_temperature, float(value))
            return
        if hasattr(camera, "set_attribute_value"):
            name = await self._to_thread(self._resolve_attribute, camera, _TEMPERATURE_ATTRS)
            if name is not None:
                await self._to_thread(camera.set_attribute_value, name, float(value))
                return

        raise NotImplementedError(
            f"{type(camera).__name__} exposes no temperature setpoint via pylablib"
        )

    async def set_framerate(self, value: float) -> None:
        """Frames per second, expressed to pylablib as its reciprocal frame
        period — only for classes exposing `set_frame_period`."""
        camera = self._camera_or_raise()
        rate = float(value)
        if rate <= 0:
            raise ValueError(f"framerate must be positive, got {rate}")
        await self._to_thread(camera.set_frame_period, 1.0 / rate)

    async def set_gain(self, value: float) -> None:
        """Master analog gain. Uses whichever route the camera class provides:
        a dedicated `set_gain`, uc480's multi-channel `set_gains`, or the
        attribute interface. Raises if the camera exposes none of them, rather
        than silently accepting a value it will never apply."""
        camera = self._camera_or_raise()

        if hasattr(camera, "set_gain"):
            await self._to_thread(camera.set_gain, float(value))
            return
        if hasattr(camera, "set_gains"):
            # uc480: (master, red, green, blue) — only the master is generic.
            await self._to_thread(camera.set_gains, float(value))
            return
        if hasattr(camera, "set_attribute_value"):
            name = await self._to_thread(self._resolve_attribute, camera, _GAIN_ATTRS)
            if name is not None:
                await self._to_thread(camera.set_attribute_value, name, float(value))
                return

        raise NotImplementedError(
            f"{type(camera).__name__} exposes no gain control via pylablib "
            f"(no set_gain/set_gains, and no matching attribute in {_GAIN_ATTRS})"
        )

    @staticmethod
    def _resolve_attribute(camera: Any, candidates: tuple[str, ...]) -> str | None:
        """First of `candidates` the camera actually advertises. Attribute
        names are vendor-specific, so this is resolved against the live device
        rather than hardcoded per manufacturer."""
        try:
            available = set(camera.get_all_attributes())
        except Exception:
            return None
        return next((name for name in candidates if name in available), None)
