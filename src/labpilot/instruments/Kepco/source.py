"""Auto-generated PyMeasure adapters for kepco instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.kepco classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.kepco.kepcobop import KepcoBOP3612
except ImportError:
    KepcoBOP3612 = None

if KepcoBOP3612 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class KepcoBOP3612Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.kepco.kepcobop.KepcoBOP3612."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KepcoBOP3612, resource=resource, name=name or "pymeasure_kepco_b_o_p3612", **kwargs)

    adapter_registry.register("pymeasure_kepco_b_o_p3612", KepcoBOP3612Adapter)

