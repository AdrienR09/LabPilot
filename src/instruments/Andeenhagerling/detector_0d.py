"""Auto-generated PyMeasure adapters for andeenhagerling instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.andeenhagerling classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.andeenhagerling.ah2700a import AH2700A
except ImportError:
    AH2700A = None

if AH2700A is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class AH2700AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.andeenhagerling.ah2700a.AH2700A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AH2700A, resource=resource, name=name or "pymeasure_a_h2700_a", **kwargs)

    adapter_registry.register("pymeasure_a_h2700_a", AH2700AAdapter)

