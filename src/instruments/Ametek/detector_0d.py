"""Auto-generated PyMeasure adapters for ametek instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.ametek classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.ametek.ametek7270 import Ametek7270
except ImportError:
    Ametek7270 = None

if Ametek7270 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Ametek7270Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.ametek.ametek7270.Ametek7270."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Ametek7270, resource=resource, name=name or "pymeasure_ametek7270", **kwargs)

    adapter_registry.register("pymeasure_ametek7270", Ametek7270Adapter)

