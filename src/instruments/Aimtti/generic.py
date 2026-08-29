"""Auto-generated PyMeasure adapters for aimtti instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.aimtti classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.aimtti.ld400p import LD400P
    from pymeasure.instruments.aimtti.aimttiPL import PL068P, PL155P, PL303P, PL303QMDP, PL303QMTP, PL601P
except ImportError:
    LD400P = PL068P = PL155P = PL303P = PL303QMDP = PL303QMTP = PL601P = None

if LD400P is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class LD400PAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.ld400p.LD400P."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LD400P, resource=resource, name=name or "pymeasure_l_d400_p", **kwargs)

    adapter_registry.register("pymeasure_l_d400_p", LD400PAdapter)

    class PL068PAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.aimttiPL.PL068P."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PL068P, resource=resource, name=name or "pymeasure_p_l068_p", **kwargs)

    adapter_registry.register("pymeasure_p_l068_p", PL068PAdapter)

    class PL155PAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.aimttiPL.PL155P."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PL155P, resource=resource, name=name or "pymeasure_p_l155_p", **kwargs)

    adapter_registry.register("pymeasure_p_l155_p", PL155PAdapter)

    class PL303PAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.aimttiPL.PL303P."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PL303P, resource=resource, name=name or "pymeasure_p_l303_p", **kwargs)

    adapter_registry.register("pymeasure_p_l303_p", PL303PAdapter)

    class PL303QMDPAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.aimttiPL.PL303QMDP."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PL303QMDP, resource=resource, name=name or "pymeasure_p_l303_q_m_d_p", **kwargs)

    adapter_registry.register("pymeasure_p_l303_q_m_d_p", PL303QMDPAdapter)

    class PL303QMTPAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.aimttiPL.PL303QMTP."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PL303QMTP, resource=resource, name=name or "pymeasure_p_l303_q_m_t_p", **kwargs)

    adapter_registry.register("pymeasure_p_l303_q_m_t_p", PL303QMTPAdapter)

    class PL601PAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aimtti.aimttiPL.PL601P."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PL601P, resource=resource, name=name or "pymeasure_p_l601_p", **kwargs)

    adapter_registry.register("pymeasure_p_l601_p", PL601PAdapter)

