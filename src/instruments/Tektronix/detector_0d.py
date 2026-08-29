"""Auto-generated PyMeasure adapters for tektronix instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.tektronix classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.tektronix.tds2000 import TDS2000
except ImportError:
    TDS2000 = None

if TDS2000 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class TDS2000Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.tektronix.tds2000.TDS2000."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TDS2000, resource=resource, name=name or "pymeasure_t_d_s2000", **kwargs)

    adapter_registry.register("pymeasure_t_d_s2000", TDS2000Adapter)

