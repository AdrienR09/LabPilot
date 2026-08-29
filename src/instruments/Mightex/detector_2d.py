"""Auto-generated pylablib camera adapters for Mightex (MightexSSeriesCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import Mightex
except ImportError:
    Mightex = None

if Mightex is not None:
    from instruments._generic_pylablib import PylablibCameraAdapter
    from instruments._base import adapter_registry

    class MightexSSeriesCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.Mightex.MightexSSeriesCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Mightex.MightexSSeriesCamera, name=name or "pylablib_mightex_s_series_camera", **device_kwargs)

    adapter_registry.register("pylablib_mightex_s_series_camera", MightexSSeriesCameraAdapter)

