"""Princeton Instruments camera adapters for pylablib.

Supports Princeton cameras via Picam SDK.

Supported cameras:
- Princeton Instruments PIXIS, ProEM, PI-MAX (CCD, EMCCD, ICCD)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from pylablib.devices import PrincetonInstruments
except ImportError:
    PrincetonInstruments = None

if PrincetonInstruments is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Triggerable
    from labpilot_core.device.schema import DeviceSchema

    class PicamAdapter(AdapterBase, Triggerable):
        """Princeton Instruments Picam adapter."""

        def __init__(self, camera_index: int = 0, name: str = "princeton_picam") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: PrincetonInstruments.PicamCamera | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"frame": "ndarray2d"},
                settable={"exposure": "float64", "temperature": "float64", "gain": "int32"},
                units={"frame": "counts", "exposure": "s", "temperature": "°C"},
                limits={"exposure": (0.001, 10.0), "temperature": (-70.0, 25.0)},
                trigger_modes=["software", "hardware", "free_run"],
                tags=["Princeton", "camera", "Picam", "PIXIS", "ProEM"],
            )

        def _connect_sync(self) -> None:
            self._camera = PrincetonInstruments.PicamCamera(idx=self._camera_index)

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

    adapter_registry.register("princeton_picam", PicamAdapter)
