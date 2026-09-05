"""Auto-generated PyMeasure adapters for mksinst instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.mksinst classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.mksinst.mks937b import MKS937B
    from pymeasure.instruments.mksinst.mks974b import MKS974B
except ImportError:
    MKS937B = MKS974B = None

if MKS937B is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class MKS937BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.mksinst.mks937b.MKS937B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=MKS937B, resource=resource, name=name or "pymeasure_m_k_s937_b", **kwargs)

    adapter_registry.register("pymeasure_m_k_s937_b", MKS937BAdapter)

    class MKS974BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.mksinst.mks974b.MKS974B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=MKS974B, resource=resource, name=name or "pymeasure_m_k_s974_b", **kwargs)

    adapter_registry.register("pymeasure_m_k_s974_b", MKS974BAdapter)

