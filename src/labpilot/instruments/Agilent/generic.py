"""Auto-generated PyMeasure adapters for agilent instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.agilent classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.agilent.agilent4156 import Agilent4156
    from pymeasure.instruments.agilent.agilent8257D import Agilent8257D
except ImportError:
    Agilent4156 = Agilent8257D = None

if Agilent4156 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Agilent4156Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent4156.Agilent4156."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent4156, resource=resource, name=name or "pymeasure_agilent4156", **kwargs)

    adapter_registry.register("pymeasure_agilent4156", Agilent4156Adapter)

    class Agilent8257DAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent8257D.Agilent8257D."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent8257D, resource=resource, name=name or "pymeasure_agilent8257_d", **kwargs)

    adapter_registry.register("pymeasure_agilent8257_d", Agilent8257DAdapter)

