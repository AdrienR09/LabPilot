"""Auto-generated pylablib camera adapters for PhotonFocus (IPhotonFocusCamera, PhotonFocusBitFlowCamera, PhotonFocusIMAQCamera, PhotonFocusSiSoCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import PhotonFocus
except ImportError:
    PhotonFocus = None

if PhotonFocus is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibCameraAdapter

    class IPhotonFocusCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.PhotonFocus.IPhotonFocusCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=PhotonFocus.IPhotonFocusCamera, name=name or "pylablib_i_photon_focus_camera", **device_kwargs)

    adapter_registry.register("pylablib_i_photon_focus_camera", IPhotonFocusCameraAdapter)

    class PhotonFocusBitFlowCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.PhotonFocus.PhotonFocusBitFlowCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=PhotonFocus.PhotonFocusBitFlowCamera, name=name or "pylablib_photon_focus_bit_flow_camera", **device_kwargs)

    adapter_registry.register("pylablib_photon_focus_bit_flow_camera", PhotonFocusBitFlowCameraAdapter)

    class PhotonFocusIMAQCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.PhotonFocus.PhotonFocusIMAQCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=PhotonFocus.PhotonFocusIMAQCamera, name=name or "pylablib_photon_focus_i_m_a_q_camera", **device_kwargs)

    adapter_registry.register("pylablib_photon_focus_i_m_a_q_camera", PhotonFocusIMAQCameraAdapter)

    class PhotonFocusSiSoCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.PhotonFocus.PhotonFocusSiSoCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=PhotonFocus.PhotonFocusSiSoCamera, name=name or "pylablib_photon_focus_si_so_camera", **device_kwargs)

    adapter_registry.register("pylablib_photon_focus_si_so_camera", PhotonFocusSiSoCameraAdapter)

