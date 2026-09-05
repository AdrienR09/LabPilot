"""Auto-generated PyMeasure adapters for heidenhain instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.heidenhain classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.heidenhain.nd287 import ND287
except ImportError:
    ND287 = None

if ND287 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class ND287Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.heidenhain.nd287.ND287."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ND287, resource=resource, name=name or "pymeasure_n_d287", **kwargs)

    adapter_registry.register("pymeasure_n_d287", ND287Adapter)

