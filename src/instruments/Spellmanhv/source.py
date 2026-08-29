"""Auto-generated PyMeasure adapters for spellmanhv instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.spellmanhv classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.spellmanhv.spellmanXRV import SpellmanXRV
except ImportError:
    SpellmanXRV = None

if SpellmanXRV is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class SpellmanXRVAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.spellmanhv.spellmanXRV.SpellmanXRV."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SpellmanXRV, resource=resource, name=name or "pymeasure_spellman_x_r_v", **kwargs)

    adapter_registry.register("pymeasure_spellman_x_r_v", SpellmanXRVAdapter)

