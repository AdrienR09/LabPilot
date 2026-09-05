"""Auto-generated PyMeasure adapters for anapico instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.anapico classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.anapico.apsin12G import APSIN12G
except ImportError:
    APSIN12G = None

if APSIN12G is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class APSIN12GAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anapico.apsin12G.APSIN12G."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=APSIN12G, resource=resource, name=name or "pymeasure_a_p_s_i_n12_g", **kwargs)

    adapter_registry.register("pymeasure_a_p_s_i_n12_g", APSIN12GAdapter)

