"""Auto-generated PyMeasure adapters for rohdeschwarz instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.rohdeschwarz classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.rohdeschwarz.hmp import HMP4040
    from pymeasure.instruments.rohdeschwarz.sfm import SFM
except ImportError:
    HMP4040 = SFM = None

if HMP4040 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class HMP4040Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.rohdeschwarz.hmp.HMP4040."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HMP4040, resource=resource, name=name or "pymeasure_h_m_p4040", **kwargs)

    adapter_registry.register("pymeasure_h_m_p4040", HMP4040Adapter)

    class SFMAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.rohdeschwarz.sfm.SFM."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SFM, resource=resource, name=name or "pymeasure_s_f_m", **kwargs)

    adapter_registry.register("pymeasure_s_f_m", SFMAdapter)

