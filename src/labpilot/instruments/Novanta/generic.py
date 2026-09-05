"""Auto-generated PyMeasure adapters for novanta instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.novanta classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.novanta.fpu60 import Fpu60
except ImportError:
    Fpu60 = None

if Fpu60 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Fpu60Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.novanta.fpu60.Fpu60."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Fpu60, resource=resource, name=name or "pymeasure_fpu60", **kwargs)

    adapter_registry.register("pymeasure_fpu60", Fpu60Adapter)

