"""Auto-generated PyMeasure adapters for yokogawa instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.yokogawa classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.yokogawa.aq6370series import (
        AQ6370C,
        AQ6370D,
        AQ6370E,
        AQ6373,
        AQ6373B,
        AQ6375,
        AQ6375B,
        AQ6370Series,
    )
except ImportError:
    AQ6370C = AQ6370D = AQ6370E = AQ6370Series = AQ6373 = AQ6373B = AQ6375 = AQ6375B = None

if AQ6370C is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class AQ6370CAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6370C."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6370C, resource=resource, name=name or "pymeasure_a_q6370_c", **kwargs)

    adapter_registry.register("pymeasure_a_q6370_c", AQ6370CAdapter)

    class AQ6370DAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6370D."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6370D, resource=resource, name=name or "pymeasure_a_q6370_d", **kwargs)

    adapter_registry.register("pymeasure_a_q6370_d", AQ6370DAdapter)

    class AQ6370EAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6370E."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6370E, resource=resource, name=name or "pymeasure_a_q6370_e", **kwargs)

    adapter_registry.register("pymeasure_a_q6370_e", AQ6370EAdapter)

    class AQ6370SeriesAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6370Series."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6370Series, resource=resource, name=name or "pymeasure_a_q6370_series", **kwargs)

    adapter_registry.register("pymeasure_a_q6370_series", AQ6370SeriesAdapter)

    class AQ6373Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6373."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6373, resource=resource, name=name or "pymeasure_a_q6373", **kwargs)

    adapter_registry.register("pymeasure_a_q6373", AQ6373Adapter)

    class AQ6373BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6373B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6373B, resource=resource, name=name or "pymeasure_a_q6373_b", **kwargs)

    adapter_registry.register("pymeasure_a_q6373_b", AQ6373BAdapter)

    class AQ6375Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6375."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6375, resource=resource, name=name or "pymeasure_a_q6375", **kwargs)

    adapter_registry.register("pymeasure_a_q6375", AQ6375Adapter)

    class AQ6375BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.yokogawa.aq6370series.AQ6375B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AQ6375B, resource=resource, name=name or "pymeasure_a_q6375_b", **kwargs)

    adapter_registry.register("pymeasure_a_q6375_b", AQ6375BAdapter)

