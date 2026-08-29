"""Auto-generated PyMeasure adapters for aja instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.aja classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.aja.dcxs import DCXS
except ImportError:
    DCXS = None

if DCXS is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class DCXSAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.aja.dcxs.DCXS."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=DCXS, resource=resource, name=name or "pymeasure_d_c_x_s", **kwargs)

    adapter_registry.register("pymeasure_d_c_x_s", DCXSAdapter)

