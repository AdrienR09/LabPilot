"""Auto-generated PyMeasure adapters for hp instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.hp classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.hp.hp11713a import HP11713A
    from pymeasure.instruments.hp.hp33120A import HP33120A
    from pymeasure.instruments.hp.hp437b import HP437B
    from pymeasure.instruments.hp.hp8657b import HP8657B
    from pymeasure.instruments.hp.hp8753e import HP8753E
    from pymeasure.instruments.hp.hplegacyinstrument import HPLegacyInstrument
except ImportError:
    HP11713A = HP33120A = HP437B = HP8657B = HP8753E = HPLegacyInstrument = None

if HP11713A is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class HP11713AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp11713a.HP11713A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP11713A, resource=resource, name=name or "pymeasure_h_p11713_a", **kwargs)

    adapter_registry.register("pymeasure_h_p11713_a", HP11713AAdapter)

    class HP33120AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp33120A.HP33120A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP33120A, resource=resource, name=name or "pymeasure_h_p33120_a", **kwargs)

    adapter_registry.register("pymeasure_h_p33120_a", HP33120AAdapter)

    class HP437BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp437b.HP437B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP437B, resource=resource, name=name or "pymeasure_h_p437_b", **kwargs)

    adapter_registry.register("pymeasure_h_p437_b", HP437BAdapter)

    class HP8657BAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp8657b.HP8657B."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP8657B, resource=resource, name=name or "pymeasure_h_p8657_b", **kwargs)

    adapter_registry.register("pymeasure_h_p8657_b", HP8657BAdapter)

    class HP8753EAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hp8753e.HP8753E."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HP8753E, resource=resource, name=name or "pymeasure_h_p8753_e", **kwargs)

    adapter_registry.register("pymeasure_h_p8753_e", HP8753EAdapter)

    class HPLegacyInstrumentAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.hp.hplegacyinstrument.HPLegacyInstrument."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=HPLegacyInstrument, resource=resource, name=name or "pymeasure_h_p_legacy_instrument", **kwargs)

    adapter_registry.register("pymeasure_h_p_legacy_instrument", HPLegacyInstrumentAdapter)

