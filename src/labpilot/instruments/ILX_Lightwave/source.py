"""Auto-generated PyMeasure adapters for ilxlightwave instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.ilxlightwave classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.ilxlightwave.ldp3811 import LDP3811
except ImportError:
    LDP3811 = None

if LDP3811 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class LDP3811Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.ilxlightwave.ldp3811.LDP3811."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LDP3811, resource=resource, name=name or "pymeasure_l_d_p3811", **kwargs)

    adapter_registry.register("pymeasure_l_d_p3811", LDP3811Adapter)

