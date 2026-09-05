"""Auto-generated PyMeasure adapters for tektronix instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.tektronix classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.tektronix.afg3152c import AFG3152C
except ImportError:
    AFG3152C = None

if AFG3152C is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class AFG3152CAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.tektronix.afg3152c.AFG3152C."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AFG3152C, resource=resource, name=name or "pymeasure_a_f_g3152_c", **kwargs)

    adapter_registry.register("pymeasure_a_f_g3152_c", AFG3152CAdapter)

