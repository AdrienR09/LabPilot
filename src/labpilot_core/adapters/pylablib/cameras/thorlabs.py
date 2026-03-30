"""Thorlabs camera adapters for pylablib.

Supports Thorlabs cameras via TLCamera SDK and IDS uEye.

Supported cameras:
- Scientific cameras (Zelux, Kiralux) via TLCamera SDK
- Industrial cameras (DCC series) via IDS uEye (UC480)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from pylablib.devices import Thorlabs
except ImportError:
    Thorlabs = None

if Thorlabs is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Triggerable
    from labpilot_core.device.schema import DeviceSchema

    class ThorlabsTLCameraAdapter(AdapterBase, Triggerable):
        """Thorlabs TLCamera SDK adapter (Zelux, Kiralux).

        Scientific CMOS cameras with:
        - Up to 9 fps (5 MP sensor)
        - Low noise
        - USB 3.0 interface
        - Hardware/software triggering

        Args:
            camera_index: Camera index (default 0).
            name: Device name.
        """

        def __init__(self, camera_index: int = 0, name: str = "thorlabs_tlcamera") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: Thorlabs.ThorlabsTLCamera | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"frame": "ndarray2d"},
                settable={"exposure": "float64", "gain": "float64", "roi": "tuple"},
                units={"frame": "counts", "exposure": "s", "gain": "dB"},
                limits={"exposure": (0.00001, 1.0), "gain": (0.0, 48.0)},
                trigger_modes=["software", "hardware", "free_run"],
                tags=["Thorlabs", "camera", "TLCamera", "Zelux", "Kiralux"],
            )

        def _connect_sync(self) -> None:
            self._camera = Thorlabs.ThorlabsTLCamera(idx=self._camera_index)
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
            mode_map = {"software": 0, "hardware": 1, "free_run": 0}
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

    class UC480Adapter(AdapterBase, Triggerable):
        """IDS uEye (UC480) camera adapter for Thorlabs DCC series.

        Industrial cameras with:
        - VGA to 5 MP sensors
        - USB 2.0/3.0 interface
        - Compact form factor

        Args:
            camera_index: Camera index (default 0).
            name: Device name.
        """

        def __init__(self, camera_index: int = 0, name: str = "uc480") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: Thorlabs.UC480Camera | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"frame": "ndarray2d"},
                settable={"exposure": "float64", "gain": "int32"},
                units={"frame": "counts", "exposure": "s"},
                limits={"exposure": (0.0001, 1.0), "gain": (0, 100)},
                trigger_modes=["software", "hardware", "free_run"],
                tags=["Thorlabs", "camera", "UC480", "uEye", "DCC"],
            )

        def _connect_sync(self) -> None:
            self._camera = Thorlabs.UC480Camera(idx=self._camera_index)

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
            mode_map = {"software": "software", "hardware": "hardware", "free_run": "software"}
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

    adapter_registry.register("thorlabs_tlcamera", ThorlabsTLCameraAdapter)
    adapter_registry.register("uc480", UC480Adapter)
