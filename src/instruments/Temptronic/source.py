"""Auto-generated PyMeasure adapters for temptronic instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.temptronic classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.temptronic.temptronic_ats525 import ATS525
    from pymeasure.instruments.temptronic.temptronic_ats545 import ATS545
    from pymeasure.instruments.temptronic.temptronic_eco560 import ECO560
except ImportError:
    ATS525 = ATS545 = ECO560 = None

if ATS525 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ATS525Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.temptronic.temptronic_ats525.ATS525."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ATS525, resource=resource, name=name or "pymeasure_a_t_s525", **kwargs)

    adapter_registry.register("pymeasure_a_t_s525", ATS525Adapter)

    class ATS545Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.temptronic.temptronic_ats545.ATS545."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ATS545, resource=resource, name=name or "pymeasure_a_t_s545", **kwargs)

    adapter_registry.register("pymeasure_a_t_s545", ATS545Adapter)

    class ECO560Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.temptronic.temptronic_eco560.ECO560."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ECO560, resource=resource, name=name or "pymeasure_e_c_o560", **kwargs)

    adapter_registry.register("pymeasure_e_c_o560", ECO560Adapter)

