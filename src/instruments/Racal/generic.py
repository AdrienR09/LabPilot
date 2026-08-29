"""Auto-generated PyMeasure adapters for racal instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.racal classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.racal.racal1992 import Racal1992
except ImportError:
    Racal1992 = None

if Racal1992 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Racal1992Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.racal.racal1992.Racal1992."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Racal1992, resource=resource, name=name or "pymeasure_racal1992", **kwargs)

    adapter_registry.register("pymeasure_racal1992", Racal1992Adapter)

