"""Auto-generated pylablib camera adapters for IMAQ (IMAQCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import IMAQ
except ImportError:
    IMAQ = None

if IMAQ is not None:
    from instruments._generic_pylablib import PylablibCameraAdapter
    from instruments._base import adapter_registry

    class IMAQCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.IMAQ.IMAQCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=IMAQ.IMAQCamera, name=name or "pylablib_i_m_a_q_camera", **device_kwargs)

    adapter_registry.register("pylablib_i_m_a_q_camera", IMAQCameraAdapter)

