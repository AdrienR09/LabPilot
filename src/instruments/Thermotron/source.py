"""Auto-generated PyMeasure adapters for thermotron instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.thermotron classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.thermotron.thermotron3800 import Thermotron3800
except ImportError:
    Thermotron3800 = None

if Thermotron3800 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class Thermotron3800Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thermotron.thermotron3800.Thermotron3800."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Thermotron3800, resource=resource, name=name or "pymeasure_thermotron3800", **kwargs)

    adapter_registry.register("pymeasure_thermotron3800", Thermotron3800Adapter)

