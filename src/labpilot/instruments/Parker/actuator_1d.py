"""Auto-generated PyMeasure adapters for parker instruments (actuator_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.parker classes, verified against the installed
pymeasure library. Type classification ("actuator_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.parker.parkerGV6 import ParkerGV6
except ImportError:
    ParkerGV6 = None

if ParkerGV6 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class ParkerGV6Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.parker.parkerGV6.ParkerGV6."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ParkerGV6, resource=resource, name=name or "pymeasure_parker_g_v6", **kwargs)

    adapter_registry.register("pymeasure_parker_g_v6", ParkerGV6Adapter)

