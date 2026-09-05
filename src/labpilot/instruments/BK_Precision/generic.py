"""Auto-generated PyMeasure adapters for bkprecision instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.bkprecision classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.bkprecision.bkprecision9130b import BKPrecision9130B
except ImportError:
    BKPrecision9130B = None

if BKPrecision9130B is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class BKPrecision9130BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.bkprecision.bkprecision9130b.BKPrecision9130B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=BKPrecision9130B, resource=resource, name=name or "pymeasure_b_k_precision9130_b", **kwargs)

    adapter_registry.register("pymeasure_b_k_precision9130_b", BKPrecision9130BAdapter)

