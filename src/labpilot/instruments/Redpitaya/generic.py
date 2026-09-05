"""Auto-generated PyMeasure adapters for redpitaya instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.redpitaya classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.redpitaya.redpitaya_scpi import RedPitayaScpi
except ImportError:
    RedPitayaScpi = None

if RedPitayaScpi is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class RedPitayaScpiAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.redpitaya.redpitaya_scpi.RedPitayaScpi."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=RedPitayaScpi, resource=resource, name=name or "pymeasure_red_pitaya_scpi", **kwargs)

    adapter_registry.register("pymeasure_red_pitaya_scpi", RedPitayaScpiAdapter)

