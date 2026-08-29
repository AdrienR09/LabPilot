"""Auto-generated PyMeasure adapters for anritsu instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.anritsu classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.anritsu.anritsuMG3692C import AnritsuMG3692C
except ImportError:
    AnritsuMG3692C = None

if AnritsuMG3692C is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class AnritsuMG3692CAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anritsu.anritsuMG3692C.AnritsuMG3692C."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AnritsuMG3692C, resource=resource, name=name or "pymeasure_anritsu_m_g3692_c", **kwargs)

    adapter_registry.register("pymeasure_anritsu_m_g3692_c", AnritsuMG3692CAdapter)

