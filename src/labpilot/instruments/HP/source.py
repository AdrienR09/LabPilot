"""Auto-generated PyMeasure adapters for hp instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.hp classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.hp.hp8116a import HP8116A
    from pymeasure.instruments.hp.hpsystempsu import HP6632A, HP6633A, HP6634A
except ImportError:
    HP6632A = HP6633A = HP6634A = HP8116A = None

if HP6632A is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class HP6632AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hpsystempsu.HP6632A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP6632A, resource=resource, name=name or "pymeasure_h_p6632_a", **kwargs)

    adapter_registry.register("pymeasure_h_p6632_a", HP6632AAdapter)

    class HP6633AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hpsystempsu.HP6633A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP6633A, resource=resource, name=name or "pymeasure_h_p6633_a", **kwargs)

    adapter_registry.register("pymeasure_h_p6633_a", HP6633AAdapter)

    class HP6634AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hpsystempsu.HP6634A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP6634A, resource=resource, name=name or "pymeasure_h_p6634_a", **kwargs)

    adapter_registry.register("pymeasure_h_p6634_a", HP6634AAdapter)

    class HP8116AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp8116a.HP8116A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP8116A, resource=resource, name=name or "pymeasure_h_p8116_a", **kwargs)

    adapter_registry.register("pymeasure_h_p8116_a", HP8116AAdapter)

