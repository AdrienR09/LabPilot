"""Auto-generated PyMeasure adapters for lecroy instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.lecroy classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.lecroy.lecroyT3DSO1204 import LeCroyT3DSO1204
except ImportError:
    LeCroyT3DSO1204 = None

if LeCroyT3DSO1204 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class LeCroyT3DSO1204Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lecroy.lecroyT3DSO1204.LeCroyT3DSO1204."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LeCroyT3DSO1204, resource=resource, name=name or "pymeasure_le_croy_t3_d_s_o1204", **kwargs)

    adapter_registry.register("pymeasure_le_croy_t3_d_s_o1204", LeCroyT3DSO1204Adapter)

