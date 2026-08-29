"""Auto-generated pylablib stage adapters for Trinamic (TMCM1110, TMCMx110).

Thin wrappers around PylablibStageAdapter (uses get_position()/move_to(),
verified present on these specific classes — pylablib stages do not share
a fully uniform API, see _generic_pylablib.py).
"""

from __future__ import annotations

try:
    from pylablib.devices import Trinamic
except ImportError:
    Trinamic = None

if Trinamic is not None:
    from instruments._generic_pylablib import PylablibStageAdapter
    from instruments._base import adapter_registry

    class TMCM1110Adapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.Trinamic.TMCM1110."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Trinamic.TMCM1110, name=name or "pylablib_t_m_c_m1110", **device_kwargs)

    adapter_registry.register("pylablib_t_m_c_m1110", TMCM1110Adapter)

    class TMCMx110Adapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.Trinamic.TMCMx110."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Trinamic.TMCMx110, name=name or "pylablib_t_m_c_mx110", **device_kwargs)

    adapter_registry.register("pylablib_t_m_c_mx110", TMCMx110Adapter)

