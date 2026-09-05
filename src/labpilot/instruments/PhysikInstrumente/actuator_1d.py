"""Auto-generated pylablib stage adapters for PhysikInstrumente (PIE515).

Thin wrappers around PylablibStageAdapter (uses get_position()/move_to(),
verified present on these specific classes — pylablib stages do not share
a fully uniform API, see _generic_pylablib.py).
"""

from __future__ import annotations

try:
    from pylablib.devices import PhysikInstrumente
except ImportError:
    PhysikInstrumente = None

if PhysikInstrumente is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibStageAdapter

    class PIE515Adapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.PhysikInstrumente.PIE515."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=PhysikInstrumente.PIE515, name=name or "pylablib_p_i_e515", **device_kwargs)

    adapter_registry.register("pylablib_p_i_e515", PIE515Adapter)

