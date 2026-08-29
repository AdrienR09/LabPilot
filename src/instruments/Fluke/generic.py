"""Auto-generated PyMeasure adapters for fluke instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.fluke classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.fluke.fluke7341 import Fluke7341
except ImportError:
    Fluke7341 = None

if Fluke7341 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Fluke7341Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.fluke.fluke7341.Fluke7341."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Fluke7341, resource=resource, name=name or "pymeasure_fluke7341", **kwargs)

    adapter_registry.register("pymeasure_fluke7341", Fluke7341Adapter)

