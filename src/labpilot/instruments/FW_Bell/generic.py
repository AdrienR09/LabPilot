"""Auto-generated PyMeasure adapters for fwbell instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.fwbell classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.fwbell.fwbell5080 import FWBell5080
except ImportError:
    FWBell5080 = None

if FWBell5080 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class FWBell5080Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.fwbell.fwbell5080.FWBell5080."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=FWBell5080, resource=resource, name=name or "pymeasure_f_w_bell5080", **kwargs)

    adapter_registry.register("pymeasure_f_w_bell5080", FWBell5080Adapter)

