"""Andor camera adapters for pylablib.

Supports Andor SDK2 and SDK3 cameras via pylablib wrappers.

Supported cameras:
- Andor SDK2: iXon, Newton, Luca (EMCCD, CCD, ICCD)
- Andor SDK3: Zyla, Neo (sCMOS)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from pylablib.devices import Andor
except ImportError:
    # pylablib not installed - skip these adapters
    Andor = None

if Andor is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Triggerable
    from labpilot_core.device.schema import DeviceSchema

    class AndorSDK2Adapter(AdapterBase, Triggerable):
        """Andor SDK2 camera adapter (iXon, Newton, Luca).

        EMCCD/CCD cameras with :
        - Frame rates up to 35 fps (depending on model)
        - EM gain up to 1000x (EMCCD models)
        - Thermoelectric cooling to -100°C
        - Multiple trigger modes (software, hardware, external)

        Args:
            camera_index: Camera index (default 0, first camera).
            name: Device name (defaults to "andor_sdk2").

        Example:
            >>> camera = AndorSDK2Adapter(camera_index=0, name="ixon_camera")
            >>> await camera.connect()
            >>> await camera.arm("software")
            >>> await camera.trigger()
            >>> frame = await camera.read()
            >>> print(f"Frame shape: {frame['frame'].shape}")
        """

        def __init__(self, camera_index: int = 0, name: str = "andor_sdk2") -> None:
            """Initialize adapter.

            Args:
                camera_index: Camera index (0 for first camera).
                name: Device name for session registry.
            """
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: Andor.AndorSDK2Camera | None = None

        @property
        def schema(self) -> DeviceSchema:
            """Device schema for Andor SDK2 cameras."""
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={"frame": "ndarray2d"},  # 2D numpy array
                settable={
                    "exposure": "float64",  # Exposure time (s)
                    "temperature": "float64",  # Target temperature (°C)
                    "em_gain": "int32",  # EM gain (0-1000, EMCCD only)
                    "readout_rate": "int32",  # Readout rate index
                    "roi": "tuple",  # Region of interest (x0, x1, y0, y1)
                },
                units={
                    "frame": "counts",
                    "exposure": "s",
                    "temperature": "°C",
                },
                limits={
                    "exposure": (0.0001, 10.0),  # 0.1 ms - 10 s
                    "temperature": (-100.0, 25.0),  # Cooling range
                    "em_gain": (0, 1000),  # EM gain range (model dependent)
                },
                trigger_modes=["software", "hardware", "free_run"],
                tags=["Andor", "camera", "EMCCD", "CCD", "SDK2"],
            )

        def _connect_sync(self) -> None:
            """Connect to camera via SDK2."""
            self._camera = Andor.AndorSDK2Camera(idx=self._camera_index)
            # Set default acquisition mode
            self._camera.set_acquisition_mode("single")
            # Enable cooler
            self._camera.enable_cooler(True)

        def _disconnect_sync(self) -> None:
            """Disconnect and close camera."""
            if self._camera is not None:
                try:
                    self._camera.enable_cooler(False)  # Turn off cooler
                    self._camera.close()
                except Exception:
                    pass
                self._camera = None

        def _stage_sync(self) -> None:
            """Start acquisition engine."""
            if self._camera is not None:
                self._camera.start_acquisition()

        def _unstage_sync(self) -> None:
            """Stop acquisition engine."""
            if self._camera is not None:
                try:
                    self._camera.stop_acquisition()
                except Exception:
                    pass

        def _arm_sync(self, mode: str) -> None:
            """Configure trigger mode.

            Args:
                mode: "software", "hardware", or "free_run"
            """
            if self._camera is None:
                raise RuntimeError("Camera not connected")

            mode_map = {
                "software": "int",  # Internal trigger
                "hardware": "ext",  # External trigger
                "free_run": "int",  # Continuous acquisition
            }

            if mode not in mode_map:
                raise ValueError(
                    f"Invalid trigger mode: {mode}. "
                    f"Must be one of {list(mode_map.keys())}"
                )

            self._camera.set_trigger_mode(mode_map[mode])

        async def arm(self, mode: str) -> None:
            """Configure trigger mode (async wrapper)."""
            await self._to_thread(self._arm_sync, mode)

        def _trigger_sync(self) -> None:
            """Issue software trigger and wait for frame."""
            if self._camera is None:
                raise RuntimeError("Camera not connected")

            # Wait for next frame (blocking)
            _ = self._camera.wait_for_frame(timeout=30.0)

        async def trigger(self) -> None:
            """Issue software trigger (async wrapper)."""
            await self._to_thread(self._trigger_sync)

        def _read_sync(self) -> dict[str, Any]:
            """Read latest frame from camera buffer.

            Returns:
                Dict with "frame" key containing 2D numpy array.
            """
            if self._camera is None:
                raise RuntimeError("Camera not connected")

            # Read latest frame
            frame = self._camera.read_oldest_image()

            # Convert to numpy array if needed
            if not isinstance(frame, np.ndarray):
                frame = np.array(frame)

            return {"frame": frame}

        def _self_test_sync(self) -> None:
            """Test camera connectivity."""
            if self._camera is None:
                raise RuntimeError("Not connected")

            # Check temperature as connectivity test
            _ = self._camera.get_temperature()

    class AndorSDK3Adapter(AdapterBase, Triggerable):
        """Andor SDK3 camera adapter (Zyla, Neo sCMOS).

        High-speed sCMOS cameras with:
        - Frame rates up to 100 fps (2560×2160)
        - Low noise (< 2 e⁻ read noise)
        - Large sensor area (up to 16.6 mm diagonal)
        - USB 3.0 interface

        Args:
            camera_index: Camera index (default 0).
            name: Device name.
        """

        def __init__(self, camera_index: int = 0, name: str = "andor_sdk3") -> None:
            super().__init__()
            self._camera_index = camera_index
            self._name = name
            self._camera: Andor.AndorSDK3Camera | None = None

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
                tags=["Andor", "camera", "sCMOS", "SDK3", "Zyla", "Neo"],
            )

        def _connect_sync(self) -> None:
            self._camera = Andor.AndorSDK3Camera(idx=self._camera_index)
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

    # Register adapters
    adapter_registry.register("andor_sdk2", AndorSDK2Adapter)
    adapter_registry.register("andor_sdk3", AndorSDK3Adapter)
