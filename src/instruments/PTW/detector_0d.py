"""Auto-generated PyMeasure adapters for ptw instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.ptw classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.ptw.ptwDIAMENTOR import ptwDIAMENTOR
    from pymeasure.instruments.ptw.ptwUNIDOS import ptwUNIDOS
except ImportError:
    ptwDIAMENTOR = ptwUNIDOS = None

if ptwDIAMENTOR is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ptwDIAMENTORAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.ptw.ptwDIAMENTOR.ptwDIAMENTOR."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ptwDIAMENTOR, resource=resource, name=name or "pymeasure_ptw_d_i_a_m_e_n_t_o_r", **kwargs)

    adapter_registry.register("pymeasure_ptw_d_i_a_m_e_n_t_o_r", ptwDIAMENTORAdapter)

    class ptwUNIDOSAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.ptw.ptwUNIDOS.ptwUNIDOS."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ptwUNIDOS, resource=resource, name=name or "pymeasure_ptw_u_n_i_d_o_s", **kwargs)

    adapter_registry.register("pymeasure_ptw_u_n_i_d_o_s", ptwUNIDOSAdapter)

