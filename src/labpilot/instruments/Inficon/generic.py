"""Auto-generated PyMeasure adapters for inficon instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.inficon classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.inficon.sqm160 import SQM160
except ImportError:
    SQM160 = None

if SQM160 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class SQM160Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.inficon.sqm160.SQM160."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SQM160, resource=resource, name=name or "pymeasure_s_q_m160", **kwargs)

    adapter_registry.register("pymeasure_s_q_m160", SQM160Adapter)

