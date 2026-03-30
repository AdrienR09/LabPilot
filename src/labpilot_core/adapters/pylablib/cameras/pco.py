"""PCO camera adapters for pylablib.

Supports PCO cameras.

Supported cameras:
- pco.edge (sCMOS)
- pco.pixelfly

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from pylablib.devices import PCO
except ImportError:
    PCO = None

if PCO is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Triggerable
    from labpilot_core.device.schema import DeviceSchema

    class PCOAdapter(AdapterBase, Triggerable):
        """PCO camera adapter."""

        def __init__(self, camera_index: int = 0, name: str = "pco") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: PCO.PCOCamera | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"frame": "ndarray2d"},
                settable={"exposure": "float64"},
                units={"frame": "counts", "exposure": "s"},
                limits={"exposure": (0.00001, 10.0)},
                trigger_modes=["software", "hardware", "free_run"],
                tags=["PCO", "camera", "edge", "sCMOS"],
            )

        def _connect_sync(self) -> None:
            self._camera = PCO.PCOCamera(idx=self._camera_index)

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

    adapter_registry.register("pco", PCOAdapter)
