"""Auto-generated PyMeasure adapters for hp instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.hp classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.hp.hp3437A import HP3437A
    from pymeasure.instruments.hp.hp3478A import HP3478A
    from pymeasure.instruments.hp.hp34401A import HP34401A
except ImportError:
    HP3437A = HP34401A = HP3478A = None

if HP3437A is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class HP3437AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp3437A.HP3437A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP3437A, resource=resource, name=name or "pymeasure_h_p3437_a", **kwargs)

    adapter_registry.register("pymeasure_h_p3437_a", HP3437AAdapter)

    class HP34401AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp34401A.HP34401A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP34401A, resource=resource, name=name or "pymeasure_h_p34401_a", **kwargs)

    adapter_registry.register("pymeasure_h_p34401_a", HP34401AAdapter)

    class HP3478AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp3478A.HP3478A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP3478A, resource=resource, name=name or "pymeasure_h_p3478_a", **kwargs)

    adapter_registry.register("pymeasure_h_p3478_a", HP3478AAdapter)

