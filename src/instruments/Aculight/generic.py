"""Auto-generated PyMeasure adapters for aculight instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.aculight classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.aculight.argos import Argos
except ImportError:
    Argos = None

if Argos is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ArgosAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aculight.argos.Argos."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Argos, resource=resource, name=name or "pymeasure_argos", **kwargs)

    adapter_registry.register("pymeasure_argos", ArgosAdapter)

