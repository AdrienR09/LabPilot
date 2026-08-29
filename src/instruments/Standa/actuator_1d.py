"""Auto-generated pylablib stage adapters for Standa (Standa8SMC).

Thin wrappers around PylablibStageAdapter (uses get_position()/move_to(),
verified present on these specific classes — pylablib stages do not share
a fully uniform API, see _generic_pylablib.py).
"""

from __future__ import annotations

try:
    from pylablib.devices import Standa
except ImportError:
    Standa = None

if Standa is not None:
    from instruments._generic_pylablib import PylablibStageAdapter
    from instruments._base import adapter_registry

    class Standa8SMCAdapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.Standa.Standa8SMC."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Standa.Standa8SMC, name=name or "pylablib_standa8_s_m_c", **device_kwargs)

    adapter_registry.register("pylablib_standa8_s_m_c", Standa8SMCAdapter)

