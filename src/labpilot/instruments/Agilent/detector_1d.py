"""Auto-generated PyMeasure adapters for agilent instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.agilent classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.agilent.agilent8722ES import Agilent8722ES
    from pymeasure.instruments.agilent.agilentE4408B import AgilentE4408B
    from pymeasure.instruments.agilent.agilentE5062A import AgilentE5062A
    from pymeasure.instruments.agilent.agilentE5270B import AgilentE5270B
except ImportError:
    Agilent8722ES = AgilentE4408B = AgilentE5062A = AgilentE5270B = None

if Agilent8722ES is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Agilent8722ESAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilent8722ES.Agilent8722ES."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Agilent8722ES, resource=resource, name=name or "pymeasure_agilent8722_e_s", **kwargs)

    adapter_registry.register("pymeasure_agilent8722_e_s", Agilent8722ESAdapter)

    class AgilentE4408BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentE4408B.AgilentE4408B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentE4408B, resource=resource, name=name or "pymeasure_agilent_e4408_b", **kwargs)

    adapter_registry.register("pymeasure_agilent_e4408_b", AgilentE4408BAdapter)

    class AgilentE5062AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentE5062A.AgilentE5062A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentE5062A, resource=resource, name=name or "pymeasure_agilent_e5062_a", **kwargs)

    adapter_registry.register("pymeasure_agilent_e5062_a", AgilentE5062AAdapter)

    class AgilentE5270BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.agilent.agilentE5270B.AgilentE5270B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AgilentE5270B, resource=resource, name=name or "pymeasure_agilent_e5270_b", **kwargs)

    adapter_registry.register("pymeasure_agilent_e5270_b", AgilentE5270BAdapter)

