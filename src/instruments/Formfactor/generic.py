"""Auto-generated PyMeasure adapters for formfactor instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.formfactor classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.formfactor.velox import Velox
except ImportError:
    Velox = None

if Velox is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class VeloxAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.formfactor.velox.Velox."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Velox, resource=resource, name=name or "pymeasure_velox", **kwargs)

    adapter_registry.register("pymeasure_velox", VeloxAdapter)

