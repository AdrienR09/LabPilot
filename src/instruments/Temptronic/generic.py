"""Auto-generated PyMeasure adapters for temptronic instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.temptronic classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.temptronic.temptronic_base import ATSBase
except ImportError:
    ATSBase = None

if ATSBase is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class ATSBaseAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.temptronic.temptronic_base.ATSBase."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=ATSBase, resource=resource, name=name or "pymeasure_a_t_s_base", **kwargs)

    adapter_registry.register("pymeasure_a_t_s_base", ATSBaseAdapter)

