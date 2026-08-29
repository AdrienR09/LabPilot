"""Auto-generated PyMeasure adapters for ami instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.ami classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.ami.ami430 import AMI430
except ImportError:
    AMI430 = None

if AMI430 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class AMI430Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.ami.ami430.AMI430."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AMI430, resource=resource, name=name or "pymeasure_a_m_i430", **kwargs)

    adapter_registry.register("pymeasure_a_m_i430", AMI430Adapter)

