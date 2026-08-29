"""Auto-generated PyMeasure adapters for santec instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.santec classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.santec.tsl500series import TSL500Series
    from pymeasure.instruments.santec.tsl550 import TSL550
    from pymeasure.instruments.santec.tsl570 import TSL570
except ImportError:
    TSL500Series = TSL550 = TSL570 = None

if TSL500Series is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class TSL500SeriesAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.santec.tsl500series.TSL500Series."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TSL500Series, resource=resource, name=name or "pymeasure_t_s_l500_series", **kwargs)

    adapter_registry.register("pymeasure_t_s_l500_series", TSL500SeriesAdapter)

    class TSL550Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.santec.tsl550.TSL550."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TSL550, resource=resource, name=name or "pymeasure_t_s_l550", **kwargs)

    adapter_registry.register("pymeasure_t_s_l550", TSL550Adapter)

    class TSL570Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.santec.tsl570.TSL570."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TSL570, resource=resource, name=name or "pymeasure_t_s_l570", **kwargs)

    adapter_registry.register("pymeasure_t_s_l570", TSL570Adapter)

