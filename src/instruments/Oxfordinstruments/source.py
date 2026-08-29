"""Auto-generated PyMeasure adapters for oxfordinstruments instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.oxfordinstruments classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.oxfordinstruments.ips120_10 import IPS120_10
    from pymeasure.instruments.oxfordinstruments.itc503 import ITC503
    from pymeasure.instruments.oxfordinstruments.mercuryitc import MercuryiTC
    from pymeasure.instruments.oxfordinstruments.ps120_10 import PS120_10
except ImportError:
    IPS120_10 = ITC503 = MercuryiTC = PS120_10 = None

if IPS120_10 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class IPS120_10Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.oxfordinstruments.ips120_10.IPS120_10."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=IPS120_10, resource=resource, name=name or "pymeasure_i_p_s120_10", **kwargs)

    adapter_registry.register("pymeasure_i_p_s120_10", IPS120_10Adapter)

    class ITC503Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.oxfordinstruments.itc503.ITC503."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ITC503, resource=resource, name=name or "pymeasure_i_t_c503", **kwargs)

    adapter_registry.register("pymeasure_i_t_c503", ITC503Adapter)

    class MercuryiTCAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.oxfordinstruments.mercuryitc.MercuryiTC."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=MercuryiTC, resource=resource, name=name or "pymeasure_mercuryi_t_c", **kwargs)

    adapter_registry.register("pymeasure_mercuryi_t_c", MercuryiTCAdapter)

    class PS120_10Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.oxfordinstruments.ps120_10.PS120_10."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PS120_10, resource=resource, name=name or "pymeasure_p_s120_10", **kwargs)

    adapter_registry.register("pymeasure_p_s120_10", PS120_10Adapter)

