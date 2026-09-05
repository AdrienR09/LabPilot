"""Auto-generated PyMeasure adapters for teledyne instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.teledyne classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.teledyne.teledyneT3AFG import TeledyneT3AFG
except ImportError:
    TeledyneT3AFG = None

if TeledyneT3AFG is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class TeledyneT3AFGAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.teledyne.teledyneT3AFG.TeledyneT3AFG."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TeledyneT3AFG, resource=resource, name=name or "pymeasure_teledyne_t3_a_f_g", **kwargs)

    adapter_registry.register("pymeasure_teledyne_t3_a_f_g", TeledyneT3AFGAdapter)

