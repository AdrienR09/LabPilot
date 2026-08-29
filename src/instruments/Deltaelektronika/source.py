"""Auto-generated PyMeasure adapters for deltaelektronika instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.deltaelektronika classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.deltaelektronika.sm7045d import SM7045D
except ImportError:
    SM7045D = None

if SM7045D is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class SM7045DAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.deltaelektronika.sm7045d.SM7045D."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SM7045D, resource=resource, name=name or "pymeasure_s_m7045_d", **kwargs)

    adapter_registry.register("pymeasure_s_m7045_d", SM7045DAdapter)

