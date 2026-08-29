"""Auto-generated PyMeasure adapters for proterial instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.proterial classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.proterial.rod4 import ROD4
except ImportError:
    ROD4 = None

if ROD4 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ROD4Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.proterial.rod4.ROD4."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ROD4, resource=resource, name=name or "pymeasure_r_o_d4", **kwargs)

    adapter_registry.register("pymeasure_r_o_d4", ROD4Adapter)

