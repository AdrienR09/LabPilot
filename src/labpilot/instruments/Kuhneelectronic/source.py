"""Auto-generated PyMeasure adapters for kuhneelectronic instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.kuhneelectronic classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.kuhneelectronic.kusg245_250a import Kusg245_250A
except ImportError:
    Kusg245_250A = None

if Kusg245_250A is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Kusg245_250AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.kuhneelectronic.kusg245_250a.Kusg245_250A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Kusg245_250A, resource=resource, name=name or "pymeasure_kusg245_250_a", **kwargs)

    adapter_registry.register("pymeasure_kusg245_250_a", Kusg245_250AAdapter)

