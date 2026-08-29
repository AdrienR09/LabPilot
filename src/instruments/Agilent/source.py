"""Auto-generated PyMeasure adapters for agilent instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.agilent classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.agilent.agilent33220A import Agilent33220A
    from pymeasure.instruments.agilent.agilent33500 import Agilent33500
    from pymeasure.instruments.agilent.agilent33521A import Agilent33521A
    from pymeasure.instruments.agilent.agilentB1500 import AgilentB1500
    from pymeasure.instruments.agilent.agilentN8975A import AgilentN8975A
except ImportError:
    Agilent33220A = Agilent33500 = Agilent33521A = AgilentB1500 = AgilentN8975A = None

if Agilent33220A is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Agilent33220AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent33220A.Agilent33220A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent33220A, resource=resource, name=name or "pymeasure_agilent33220_a", **kwargs)

    adapter_registry.register("pymeasure_agilent33220_a", Agilent33220AAdapter)

    class Agilent33500Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent33500.Agilent33500."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent33500, resource=resource, name=name or "pymeasure_agilent33500", **kwargs)

    adapter_registry.register("pymeasure_agilent33500", Agilent33500Adapter)

    class Agilent33521AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent33521A.Agilent33521A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent33521A, resource=resource, name=name or "pymeasure_agilent33521_a", **kwargs)

    adapter_registry.register("pymeasure_agilent33521_a", Agilent33521AAdapter)

    class AgilentB1500Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentB1500.AgilentB1500."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentB1500, resource=resource, name=name or "pymeasure_agilent_b1500", **kwargs)

    adapter_registry.register("pymeasure_agilent_b1500", AgilentB1500Adapter)

    class AgilentN8975AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentN8975A.AgilentN8975A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentN8975A, resource=resource, name=name or "pymeasure_agilent_n8975_a", **kwargs)

    adapter_registry.register("pymeasure_agilent_n8975_a", AgilentN8975AAdapter)

