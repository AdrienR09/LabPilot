"""Auto-generated PyMeasure adapters for philips instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.philips classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.philips.PM6669 import PM6669
except ImportError:
    PM6669 = None

if PM6669 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class PM6669Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.philips.PM6669.PM6669."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=PM6669, resource=resource, name=name or "pymeasure_p_m6669", **kwargs)

    adapter_registry.register("pymeasure_p_m6669", PM6669Adapter)

