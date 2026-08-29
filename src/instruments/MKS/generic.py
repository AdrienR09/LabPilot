"""Auto-generated PyMeasure adapters for mksinst instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.mksinst classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.mksinst.mksinst import MKSInstrument
except ImportError:
    MKSInstrument = None

if MKSInstrument is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class MKSInstrumentAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.mksinst.mksinst.MKSInstrument."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=MKSInstrument, resource=resource, name=name or "pymeasure_m_k_s_instrument", **kwargs)

    adapter_registry.register("pymeasure_m_k_s_instrument", MKSInstrumentAdapter)

