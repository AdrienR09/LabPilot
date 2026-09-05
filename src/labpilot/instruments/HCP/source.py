"""Auto-generated PyMeasure adapters for hcp instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.hcp classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.hcp.tc038 import TC038
    from pymeasure.instruments.hcp.tc038d import TC038D
except ImportError:
    TC038 = TC038D = None

if TC038 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class TC038Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hcp.tc038.TC038."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TC038, resource=resource, name=name or "pymeasure_t_c038", **kwargs)

    adapter_registry.register("pymeasure_t_c038", TC038Adapter)

    class TC038DAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hcp.tc038d.TC038D."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TC038D, resource=resource, name=name or "pymeasure_t_c038_d", **kwargs)

    adapter_registry.register("pymeasure_t_c038_d", TC038DAdapter)

