"""Auto-generated pylablib camera adapters for SiliconSoftware (SiliconSoftwareCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import SiliconSoftware
except ImportError:
    SiliconSoftware = None

if SiliconSoftware is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibCameraAdapter

    class SiliconSoftwareCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.SiliconSoftware.SiliconSoftwareCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=SiliconSoftware.SiliconSoftwareCamera, name=name or "pylablib_silicon_software_camera", **device_kwargs)

    adapter_registry.register("pylablib_silicon_software_camera", SiliconSoftwareCameraAdapter)

