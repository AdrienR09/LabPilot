"""Auto-generated PyMeasure adapters for agilent instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.agilent classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.agilent.agilent34410A import Agilent34410A
    from pymeasure.instruments.agilent.agilent34450A import Agilent34450A
    from pymeasure.instruments.agilent.agilent4284A import Agilent4284A
    from pymeasure.instruments.agilent.agilent4294A import Agilent4294A
    from pymeasure.instruments.agilent.agilentB298x import AgilentB2981, AgilentB2983, AgilentB2985, AgilentB2987
    from pymeasure.instruments.agilent.agilentE4980 import AgilentE4980
except ImportError:
    Agilent34410A = Agilent34450A = Agilent4284A = Agilent4294A = AgilentB2981 = AgilentB2983 = AgilentB2985 = AgilentB2987 = AgilentE4980 = None

if Agilent34410A is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Agilent34410AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent34410A.Agilent34410A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent34410A, resource=resource, name=name or "pymeasure_agilent34410_a", **kwargs)

    adapter_registry.register("pymeasure_agilent34410_a", Agilent34410AAdapter)

    class Agilent34450AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent34450A.Agilent34450A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent34450A, resource=resource, name=name or "pymeasure_agilent34450_a", **kwargs)

    adapter_registry.register("pymeasure_agilent34450_a", Agilent34450AAdapter)

    class Agilent4284AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent4284A.Agilent4284A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent4284A, resource=resource, name=name or "pymeasure_agilent4284_a", **kwargs)

    adapter_registry.register("pymeasure_agilent4284_a", Agilent4284AAdapter)

    class Agilent4294AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent4294A.Agilent4294A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent4294A, resource=resource, name=name or "pymeasure_agilent4294_a", **kwargs)

    adapter_registry.register("pymeasure_agilent4294_a", Agilent4294AAdapter)

    class AgilentB2981Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentB298x.AgilentB2981."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentB2981, resource=resource, name=name or "pymeasure_agilent_b2981", **kwargs)

    adapter_registry.register("pymeasure_agilent_b2981", AgilentB2981Adapter)

    class AgilentB2983Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentB298x.AgilentB2983."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentB2983, resource=resource, name=name or "pymeasure_agilent_b2983", **kwargs)

    adapter_registry.register("pymeasure_agilent_b2983", AgilentB2983Adapter)

    class AgilentB2985Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentB298x.AgilentB2985."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentB2985, resource=resource, name=name or "pymeasure_agilent_b2985", **kwargs)

    adapter_registry.register("pymeasure_agilent_b2985", AgilentB2985Adapter)

    class AgilentB2987Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentB298x.AgilentB2987."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentB2987, resource=resource, name=name or "pymeasure_agilent_b2987", **kwargs)

    adapter_registry.register("pymeasure_agilent_b2987", AgilentB2987Adapter)

    class AgilentE4980Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentE4980.AgilentE4980."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentE4980, resource=resource, name=name or "pymeasure_agilent_e4980", **kwargs)

    adapter_registry.register("pymeasure_agilent_e4980", AgilentE4980Adapter)

