"""Auto-generated PyMeasure adapters for siglenttechnologies instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.siglenttechnologies classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.siglenttechnologies.siglent_spd1168x import SPD1168X
    from pymeasure.instruments.siglenttechnologies.siglent_spd1305x import SPD1305X
except ImportError:
    SPD1168X = SPD1305X = None

if SPD1168X is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class SPD1168XAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.siglenttechnologies.siglent_spd1168x.SPD1168X."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SPD1168X, resource=resource, name=name or "pymeasure_s_p_d1168_x", **kwargs)

    adapter_registry.register("pymeasure_s_p_d1168_x", SPD1168XAdapter)

    class SPD1305XAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.siglenttechnologies.siglent_spd1305x.SPD1305X."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SPD1305X, resource=resource, name=name or "pymeasure_s_p_d1305_x", **kwargs)

    adapter_registry.register("pymeasure_s_p_d1305_x", SPD1305XAdapter)

