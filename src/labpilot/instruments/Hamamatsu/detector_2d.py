"""Hamamatsu camera adapters for pylablib.

Supports Hamamatsu cameras via DCAM-API (Orca, ImagEM series).

Supported cameras:
- Orca-Flash (sCMOS)
- ImagEM (EMCCD)
- Orca-Fusion (sCMOS)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import DCAM
except ImportError:
    DCAM = None

if DCAM is not None:
    from labpilot.core.device.parameter import Parameter, ParamRole
    from labpilot.core.device.schema import DeviceSchema
    from labpilot.instruments._base import AdapterBase, adapter_registry
    from labpilot.instruments._pylablib_camera import PylablibCameraControls

    class DCAMAdapter(PylablibCameraControls, AdapterBase):
        """Hamamatsu DCAM camera adapter (Orca, ImagEM).

        High-speed scientific cameras with:
        - Frame rates up to 100 fps (model dependent)
        - Low noise (< 2 e⁻ read noise for EMCCD)
        - Large sensor area
        - USB 3.0 or CameraLink interface

        Args:
            camera_index: Camera index (default 0).
            name: Device name.
        """

        def __init__(self, camera_index: int = 0, name: str = "hamamatsu_dcam") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: DCAM.DCAMCamera | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                parameters=(
                    Parameter(
                        "frame", shape=(None, None), unit="counts",
                        description="One image, snapped if the camera is idle",
                    ),
                    Parameter(
                        "exposure", unit="s", settable=True, role=ParamRole.SETTING,
                        limits=(0.00001, 10.0),
                    ),
                    # No "framerate": DCAM derives the frame period from
                    # exposure and readout rather than accepting a setpoint —
                    # pylablib exposes get_frame_period() but no setter, so
                    # declaring it settable would render a GUI control that
                    # cannot work.
                    Parameter(
                        "roi", dtype="str", settable=True, readable=False,
                        role=ParamRole.SETTING,
                        description="(hstart, hend, vstart, vend) in pixels",
                    ),
                    # Which camera this is, which the adapter could not say
                    # before: `labpilot probe` on an unknown camera reported
                    # a frame and nothing to identify the instrument by.
                    Parameter("vendor", dtype="str", role=ParamRole.STATUS),
                    Parameter("model", dtype="str", role=ParamRole.STATUS),
                    Parameter("serial_number", dtype="str", role=ParamRole.STATUS),
                    Parameter("camera_version", dtype="str", role=ParamRole.STATUS),
                    Parameter(
                        "sensor_width", dtype="i8", unit="px", role=ParamRole.STATUS,
                        description="Full sensor, whatever the ROI is set to",
                    ),
                    Parameter(
                        "sensor_height", dtype="i8", unit="px", role=ParamRole.STATUS,
                    ),
                    Parameter(
                        "frame_period", unit="s", role=ParamRole.STATUS,
                        description=(
                            "What the camera derived from the exposure and its "
                            "readout — the real frame rate, which is not a "
                            "setpoint on DCAM"
                        ),
                    ),
                ),
                trigger_modes=["software", "hardware", "free_run"],
                tags=["Hamamatsu", "camera", "DCAM", "Orca", "ImagEM"],
            )

        def _connect_sync(self) -> None:
            self._camera = DCAM.DCAMCamera(idx=self._camera_index)
            self._camera.set_acquisition_mode("single")

        def _disconnect_sync(self) -> None:
            if self._camera:
                try:
                    self._camera.close()
                except Exception:
                    pass
                self._camera = None

        def _stage_sync(self) -> None:
            if self._camera:
                self._camera.start_acquisition()

        def _unstage_sync(self) -> None:
            if self._camera:
                try:
                    self._camera.stop_acquisition()
                except Exception:
                    pass

        def _arm_sync(self, mode: str) -> None:
            if self._camera is None:
                raise RuntimeError("Not connected")

            mode_map = {"software": "int", "hardware": "ext", "free_run": "int"}
            if mode not in mode_map:
                raise ValueError(f"Invalid trigger mode: {mode}")

            self._camera.set_trigger_mode(mode_map[mode])

        async def arm(self, mode: str) -> None:
            await self._to_thread(self._arm_sync, mode)

        def _trigger_sync(self) -> None:
            if self._camera is None:
                raise RuntimeError("Not connected")
            _ = self._camera.wait_for_frame(timeout=30.0)

        async def trigger(self) -> None:
            await self._to_thread(self._trigger_sync)

        def _read_sync(self) -> dict[str, Any]:
            if self._camera is None:
                raise RuntimeError("Not connected")

            reading: dict[str, Any] = {
                "frame": self.frame_sync(),
                "exposure": float(self._camera.get_exposure()),
                **self.camera_status(),
            }
            try:
                reading["frame_period"] = float(self._camera.get_frame_period())
            except Exception:
                reading["frame_period"] = 0.0
            return reading

    adapter_registry.register("hamamatsu_dcam", DCAMAdapter)
