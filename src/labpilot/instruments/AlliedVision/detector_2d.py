"""Auto-generated pylablib camera adapters for AlliedVision (BonitoIMAQCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import AlliedVision
except ImportError:
    AlliedVision = None

if AlliedVision is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibCameraAdapter

    class BonitoIMAQCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.AlliedVision.BonitoIMAQCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=AlliedVision.BonitoIMAQCamera, name=name or "pylablib_bonito_i_m_a_q_camera", **device_kwargs)

    adapter_registry.register("pylablib_bonito_i_m_a_q_camera", BonitoIMAQCameraAdapter)

