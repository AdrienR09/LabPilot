"""Auto-generated PyMeasure adapters for edwards instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.edwards classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.edwards.nxds import Nxds
except ImportError:
    Nxds = None

if Nxds is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class NxdsAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.edwards.nxds.Nxds."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Nxds, resource=resource, name=name or "pymeasure_nxds", **kwargs)

    adapter_registry.register("pymeasure_nxds", NxdsAdapter)

