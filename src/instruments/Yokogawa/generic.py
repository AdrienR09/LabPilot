"""Auto-generated PyMeasure adapters for yokogawa instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.yokogawa classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.yokogawa.yokogawa7651 import Yokogawa7651
    from pymeasure.instruments.yokogawa.yokogawags200 import YokogawaGS200
except ImportError:
    Yokogawa7651 = YokogawaGS200 = None

if Yokogawa7651 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Yokogawa7651Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.yokogawa7651.Yokogawa7651."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Yokogawa7651, resource=resource, name=name or "pymeasure_yokogawa7651", **kwargs)

    adapter_registry.register("pymeasure_yokogawa7651", Yokogawa7651Adapter)

    class YokogawaGS200Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.yokogawags200.YokogawaGS200."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=YokogawaGS200, resource=resource, name=name or "pymeasure_yokogawa_g_s200", **kwargs)

    adapter_registry.register("pymeasure_yokogawa_g_s200", YokogawaGS200Adapter)

