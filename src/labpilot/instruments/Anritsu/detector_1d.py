"""Auto-generated PyMeasure adapters for anritsu instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.anritsu classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.anritsu.anritsuMS464xB import (
        AnritsuMS464xB,
        AnritsuMS4642B,
        AnritsuMS4644B,
        AnritsuMS4645B,
        AnritsuMS4647B,
    )
    from pymeasure.instruments.anritsu.anritsuMS2090A import AnritsuMS2090A
    from pymeasure.instruments.anritsu.anritsuMS9710C import AnritsuMS9710C
    from pymeasure.instruments.anritsu.anritsuMS9740A import AnritsuMS9740A
except ImportError:
    AnritsuMS2090A = AnritsuMS4642B = AnritsuMS4644B = AnritsuMS4645B = AnritsuMS4647B = AnritsuMS464xB = AnritsuMS9710C = AnritsuMS9740A = None

if AnritsuMS2090A is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class AnritsuMS2090AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS2090A.AnritsuMS2090A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS2090A, resource=resource, name=name or "pymeasure_anritsu_m_s2090_a", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s2090_a", AnritsuMS2090AAdapter)

    class AnritsuMS4642BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS464xB.AnritsuMS4642B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS4642B, resource=resource, name=name or "pymeasure_anritsu_m_s4642_b", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s4642_b", AnritsuMS4642BAdapter)

    class AnritsuMS4644BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS464xB.AnritsuMS4644B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS4644B, resource=resource, name=name or "pymeasure_anritsu_m_s4644_b", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s4644_b", AnritsuMS4644BAdapter)

    class AnritsuMS4645BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS464xB.AnritsuMS4645B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS4645B, resource=resource, name=name or "pymeasure_anritsu_m_s4645_b", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s4645_b", AnritsuMS4645BAdapter)

    class AnritsuMS4647BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS464xB.AnritsuMS4647B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS4647B, resource=resource, name=name or "pymeasure_anritsu_m_s4647_b", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s4647_b", AnritsuMS4647BAdapter)

    class AnritsuMS464xBAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS464xB.AnritsuMS464xB."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS464xB, resource=resource, name=name or "pymeasure_anritsu_m_s464x_b", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s464x_b", AnritsuMS464xBAdapter)

    class AnritsuMS9710CAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS9710C.AnritsuMS9710C."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS9710C, resource=resource, name=name or "pymeasure_anritsu_m_s9710_c", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s9710_c", AnritsuMS9710CAdapter)

    class AnritsuMS9740AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMS9740A.AnritsuMS9740A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMS9740A, resource=resource, name=name or "pymeasure_anritsu_m_s9740_a", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_s9740_a", AnritsuMS9740AAdapter)

