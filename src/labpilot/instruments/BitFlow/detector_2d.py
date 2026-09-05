"""Auto-generated pylablib camera adapters for BitFlow (BitFlowCamera).

Thin wrappers around PylablibCameraAdapter (uses the common ICamera
interface: open/close/snap/get_detector_size) for real pylablib classes,
verified against the installed pylablib 1.4.3.
"""

from __future__ import annotations

try:
    from pylablib.devices import BitFlow
except ImportError:
    BitFlow = None

if BitFlow is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibCameraAdapter

    class BitFlowCameraAdapter(PylablibCameraAdapter):
        """Auto-generated adapter for pylablib.devices.BitFlow.BitFlowCamera."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=BitFlow.BitFlowCamera, name=name or "pylablib_bit_flow_camera", **device_kwargs)

    adapter_registry.register("pylablib_bit_flow_camera", BitFlowCameraAdapter)

