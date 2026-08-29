"""Auto-generated PyMeasure adapters for thorlabs instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.thorlabs classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.thorlabs.thorlabsmbxseries import ThorlabsMBXSeries
    from pymeasure.instruments.thorlabs.thorlabspro8000 import ThorlabsPro8000
except ImportError:
    ThorlabsMBXSeries = ThorlabsPro8000 = None

if ThorlabsMBXSeries is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ThorlabsMBXSeriesAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thorlabs.thorlabsmbxseries.ThorlabsMBXSeries."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ThorlabsMBXSeries, resource=resource, name=name or "pymeasure_thorlabs_m_b_x_series", **kwargs)

    adapter_registry.register("pymeasure_thorlabs_m_b_x_series", ThorlabsMBXSeriesAdapter)

    class ThorlabsPro8000Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thorlabs.thorlabspro8000.ThorlabsPro8000."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ThorlabsPro8000, resource=resource, name=name or "pymeasure_thorlabs_pro8000", **kwargs)

    adapter_registry.register("pymeasure_thorlabs_pro8000", ThorlabsPro8000Adapter)

