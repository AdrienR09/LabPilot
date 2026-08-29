"""Auto-generated PyMeasure adapters for rigol instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.rigol classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.rigol.rigol_dg800 import DG800
except ImportError:
    DG800 = None

if DG800 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class DG800Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.rigol.rigol_dg800.DG800."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=DG800, resource=resource, name=name or "pymeasure_d_g800", **kwargs)

    adapter_registry.register("pymeasure_d_g800", DG800Adapter)

