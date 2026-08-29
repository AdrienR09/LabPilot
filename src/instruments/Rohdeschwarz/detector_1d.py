"""Auto-generated PyMeasure adapters for rohdeschwarz instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.rohdeschwarz classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.rohdeschwarz.fsseries import FSL, FSW
except ImportError:
    FSL = FSW = None

if FSL is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class FSLAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.rohdeschwarz.fsseries.FSL."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=FSL, resource=resource, name=name or "pymeasure_f_s_l", **kwargs)

    adapter_registry.register("pymeasure_f_s_l", FSLAdapter)

    class FSWAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.rohdeschwarz.fsseries.FSW."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=FSW, resource=resource, name=name or "pymeasure_f_s_w", **kwargs)

    adapter_registry.register("pymeasure_f_s_w", FSWAdapter)

