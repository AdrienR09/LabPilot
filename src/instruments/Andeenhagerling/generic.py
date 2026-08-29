"""Auto-generated PyMeasure adapters for andeenhagerling instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.andeenhagerling classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.andeenhagerling.ah2500a import AH2500A
except ImportError:
    AH2500A = None

if AH2500A is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class AH2500AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.andeenhagerling.ah2500a.AH2500A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AH2500A, resource=resource, name=name or "pymeasure_a_h2500_a", **kwargs)

    adapter_registry.register("pymeasure_a_h2500_a", AH2500AAdapter)

