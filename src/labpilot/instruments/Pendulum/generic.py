"""Auto-generated PyMeasure adapters for pendulum instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.pendulum classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.pendulum.cnt91 import CNT91
except ImportError:
    CNT91 = None

if CNT91 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class CNT91Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.pendulum.cnt91.CNT91."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=CNT91, resource=resource, name=name or "pymeasure_c_n_t91", **kwargs)

    adapter_registry.register("pymeasure_c_n_t91", CNT91Adapter)

