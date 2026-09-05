"""Auto-generated PyMeasure adapters for hp instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.hp classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.hp.hp856Xx import HP8560A, HP8561B
except ImportError:
    HP8560A = HP8561B = None

if HP8560A is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class HP8560AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp856Xx.HP8560A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP8560A, resource=resource, name=name or "pymeasure_h_p8560_a", **kwargs)

    adapter_registry.register("pymeasure_h_p8560_a", HP8560AAdapter)

    class HP8561BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp856Xx.HP8561B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP8561B, resource=resource, name=name or "pymeasure_h_p8561_b", **kwargs)

    adapter_registry.register("pymeasure_h_p8561_b", HP8561BAdapter)

