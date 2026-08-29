"""Auto-generated PyMeasure adapters for siglenttechnologies instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.siglenttechnologies classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.siglenttechnologies.siglent_sds1000xhd import SDS1000XHD
    from pymeasure.instruments.siglenttechnologies.siglent_sds1072cml import SDS1072CML
except ImportError:
    SDS1000XHD = SDS1072CML = None

if SDS1000XHD is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class SDS1000XHDAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.siglenttechnologies.siglent_sds1000xhd.SDS1000XHD."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SDS1000XHD, resource=resource, name=name or "pymeasure_s_d_s1000_x_h_d", **kwargs)

    adapter_registry.register("pymeasure_s_d_s1000_x_h_d", SDS1000XHDAdapter)

    class SDS1072CMLAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.siglenttechnologies.siglent_sds1072cml.SDS1072CML."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SDS1072CML, resource=resource, name=name or "pymeasure_s_d_s1072_c_m_l", **kwargs)

    adapter_registry.register("pymeasure_s_d_s1072_c_m_l", SDS1072CMLAdapter)

