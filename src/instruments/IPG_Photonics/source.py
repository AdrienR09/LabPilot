"""Auto-generated PyMeasure adapters for ipgphotonics instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.ipgphotonics classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.ipgphotonics.yar import YAR
except ImportError:
    YAR = None

if YAR is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class YARAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.ipgphotonics.yar.YAR."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=YAR, resource=resource, name=name or "pymeasure_y_a_r", **kwargs)

    adapter_registry.register("pymeasure_y_a_r", YARAdapter)

