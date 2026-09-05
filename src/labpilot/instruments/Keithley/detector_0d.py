"""Auto-generated PyMeasure adapters for keithley instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.keithley classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.keithley.keithley2000 import Keithley2000
    from pymeasure.instruments.keithley.keithley2182 import Keithley2182
    from pymeasure.instruments.keithley.keithley2700 import Keithley2700
    from pymeasure.instruments.keithley.keithley2750 import Keithley2750
    from pymeasure.instruments.keithley.keithley6517b import Keithley6517B
    from pymeasure.instruments.keithley.keithleyDAQ6510 import KeithleyDAQ6510
    from pymeasure.instruments.keithley.keithleyDMM6500 import KeithleyDMM6500
except ImportError:
    Keithley2000 = Keithley2182 = Keithley2700 = Keithley2750 = Keithley6517B = KeithleyDAQ6510 = KeithleyDMM6500 = None

if Keithley2000 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Keithley2000Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley2000.Keithley2000."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley2000, resource=resource, name=name or "pymeasure_keithley2000", **kwargs)

    adapter_registry.register("pymeasure_keithley2000", Keithley2000Adapter)

    class Keithley2182Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley2182.Keithley2182."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley2182, resource=resource, name=name or "pymeasure_keithley2182", **kwargs)

    adapter_registry.register("pymeasure_keithley2182", Keithley2182Adapter)

    class Keithley2700Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley2700.Keithley2700."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley2700, resource=resource, name=name or "pymeasure_keithley2700", **kwargs)

    adapter_registry.register("pymeasure_keithley2700", Keithley2700Adapter)

    class Keithley2750Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley2750.Keithley2750."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley2750, resource=resource, name=name or "pymeasure_keithley2750", **kwargs)

    adapter_registry.register("pymeasure_keithley2750", Keithley2750Adapter)

    class Keithley6517BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley6517b.Keithley6517B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley6517B, resource=resource, name=name or "pymeasure_keithley6517_b", **kwargs)

    adapter_registry.register("pymeasure_keithley6517_b", Keithley6517BAdapter)

    class KeithleyDAQ6510Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithleyDAQ6510.KeithleyDAQ6510."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeithleyDAQ6510, resource=resource, name=name or "pymeasure_keithley_d_a_q6510", **kwargs)

    adapter_registry.register("pymeasure_keithley_d_a_q6510", KeithleyDAQ6510Adapter)

    class KeithleyDMM6500Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithleyDMM6500.KeithleyDMM6500."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeithleyDMM6500, resource=resource, name=name or "pymeasure_keithley_d_m_m6500", **kwargs)

    adapter_registry.register("pymeasure_keithley_d_m_m6500", KeithleyDMM6500Adapter)

