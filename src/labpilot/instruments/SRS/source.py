"""Auto-generated PyMeasure adapters for srs instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.srs classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.srs.ldc500series import LDC500Series
    from pymeasure.instruments.srs.sg380 import SG380
except ImportError:
    LDC500Series = SG380 = None

if LDC500Series is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class LDC500SeriesAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.srs.ldc500series.LDC500Series."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LDC500Series, resource=resource, name=name or "pymeasure_l_d_c500_series", **kwargs)

    adapter_registry.register("pymeasure_l_d_c500_series", LDC500SeriesAdapter)

    class SG380Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.srs.sg380.SG380."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SG380, resource=resource, name=name or "pymeasure_s_g380", **kwargs)

    adapter_registry.register("pymeasure_s_g380", SG380Adapter)

