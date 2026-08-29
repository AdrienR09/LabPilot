"""Auto-generated pylablib stage adapters for SmarAct (MCS2).

Thin wrappers around PylablibStageAdapter (uses get_position()/move_to(),
verified present on these specific classes — pylablib stages do not share
a fully uniform API, see _generic_pylablib.py).
"""

from __future__ import annotations

try:
    from pylablib.devices import SmarAct
except ImportError:
    SmarAct = None

if SmarAct is not None:
    from instruments._generic_pylablib import PylablibStageAdapter
    from instruments._base import adapter_registry

    class MCS2Adapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.SmarAct.MCS2."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=SmarAct.MCS2, name=name or "pylablib_m_c_s2", **device_kwargs)

    adapter_registry.register("pylablib_m_c_s2", MCS2Adapter)

