"""Auto-generated PyMeasure adapters for activetechnologies instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.activetechnologies classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.activetechnologies.AWG401x import AWG401x_AFG, AWG401x_AWG
except ImportError:
    AWG401x_AFG = AWG401x_AWG = None

if AWG401x_AFG is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class AWG401x_AFGAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.activetechnologies.AWG401x.AWG401x_AFG."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AWG401x_AFG, resource=resource, name=name or "pymeasure_a_w_g401x_a_f_g", **kwargs)

    adapter_registry.register("pymeasure_a_w_g401x_a_f_g", AWG401x_AFGAdapter)

    class AWG401x_AWGAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.activetechnologies.AWG401x.AWG401x_AWG."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AWG401x_AWG, resource=resource, name=name or "pymeasure_a_w_g401x_a_w_g", **kwargs)

    adapter_registry.register("pymeasure_a_w_g401x_a_w_g", AWG401x_AWGAdapter)

