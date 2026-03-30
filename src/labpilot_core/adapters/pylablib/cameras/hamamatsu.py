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

import numpy as np

try:
    from pylablib.devices import DCAM
except ImportError:
    DCAM = None

if DCAM is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Triggerable
    from labpilot_core.device.schema import DeviceSchema

    class DCAMAdapter(AdapterBase, Triggerable):
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
                readable={"frame": "ndarray2d"},
                settable={
                    "exposure": "float64",
                    "framerate": "float64",
                    "roi": "tuple",
                },
                units={"frame": "counts", "exposure": "s", "framerate": "Hz"},
                limits={"exposure": (0.00001, 10.0), "framerate": (1.0, 100.0)},
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

            frame = self._camera.read_oldest_image()
            if not isinstance(frame, np.ndarray):
                frame = np.array(frame)

            return {"frame": frame}

    adapter_registry.register("hamamatsu_dcam", DCAMAdapter)
