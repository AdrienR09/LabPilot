"""Auto-generated PyMeasure adapters for danfysik instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.danfysik classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.danfysik.danfysik8500 import Danfysik8500
except ImportError:
    Danfysik8500 = None

if Danfysik8500 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Danfysik8500Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.danfysik.danfysik8500.Danfysik8500."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Danfysik8500, resource=resource, name=name or "pymeasure_danfysik8500", **kwargs)

    adapter_registry.register("pymeasure_danfysik8500", Danfysik8500Adapter)

