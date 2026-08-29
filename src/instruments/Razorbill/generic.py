"""Auto-generated PyMeasure adapters for razorbill instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.razorbill classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.razorbill.razorbillRP100 import razorbillRP100
except ImportError:
    razorbillRP100 = None

if razorbillRP100 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class razorbillRP100Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.razorbill.razorbillRP100.razorbillRP100."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=razorbillRP100, resource=resource, name=name or "pymeasure_razorbill_r_p100", **kwargs)

    adapter_registry.register("pymeasure_razorbill_r_p100", razorbillRP100Adapter)

