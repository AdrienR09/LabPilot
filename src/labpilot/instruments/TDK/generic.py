"""Auto-generated PyMeasure adapters for tdk instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.tdk classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.tdk.tdk_gen40_38 import TDK_Gen40_38
    from pymeasure.instruments.tdk.tdk_gen80_65 import TDK_Gen80_65
except ImportError:
    TDK_Gen40_38 = TDK_Gen80_65 = None

if TDK_Gen40_38 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class TDK_Gen40_38Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.tdk.tdk_gen40_38.TDK_Gen40_38."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TDK_Gen40_38, resource=resource, name=name or "pymeasure_t_d_k_gen40_38", **kwargs)

    adapter_registry.register("pymeasure_t_d_k_gen40_38", TDK_Gen40_38Adapter)

    class TDK_Gen80_65Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.tdk.tdk_gen80_65.TDK_Gen80_65."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TDK_Gen80_65, resource=resource, name=name or "pymeasure_t_d_k_gen80_65", **kwargs)

    adapter_registry.register("pymeasure_t_d_k_gen80_65", TDK_Gen80_65Adapter)

