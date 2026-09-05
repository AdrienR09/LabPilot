"""Auto-generated pylablib camera adapters for IMAQdx (EthernetIMAQdxCamera, IMAQdxCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import IMAQdx
except ImportError:
    IMAQdx = None

if IMAQdx is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibCameraAdapter

    class EthernetIMAQdxCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.IMAQdx.EthernetIMAQdxCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=IMAQdx.EthernetIMAQdxCamera, name=name or "pylablib_ethernet_i_m_a_qdx_camera", **device_kwargs)

    adapter_registry.register("pylablib_ethernet_i_m_a_qdx_camera", EthernetIMAQdxCameraAdapter)

    class IMAQdxCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.IMAQdx.IMAQdxCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=IMAQdx.IMAQdxCamera, name=name or "pylablib_i_m_a_qdx_camera", **device_kwargs)

    adapter_registry.register("pylablib_i_m_a_qdx_camera", IMAQdxCameraAdapter)

