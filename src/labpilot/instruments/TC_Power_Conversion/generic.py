"""Auto-generated PyMeasure adapters for tcpowerconversion instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.tcpowerconversion classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.tcpowerconversion.tccxn import CXN
except ImportError:
    CXN = None

if CXN is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class CXNAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.tcpowerconversion.tccxn.CXN."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=CXN, resource=resource, name=name or "pymeasure_c_x_n", **kwargs)

    adapter_registry.register("pymeasure_c_x_n", CXNAdapter)

