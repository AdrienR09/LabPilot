"""Auto-generated PyMeasure adapters for signalrecovery instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.signalrecovery classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.signalrecovery.dsp7225 import DSP7225
    from pymeasure.instruments.signalrecovery.dsp7265 import DSP7265
except ImportError:
    DSP7225 = DSP7265 = None

if DSP7225 is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class DSP7225Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.signalrecovery.dsp7225.DSP7225."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=DSP7225, resource=resource, name=name or "pymeasure_d_s_p7225", **kwargs)

    adapter_registry.register("pymeasure_d_s_p7225", DSP7225Adapter)

    class DSP7265Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.signalrecovery.dsp7265.DSP7265."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=DSP7265, resource=resource, name=name or "pymeasure_d_s_p7265", **kwargs)

    adapter_registry.register("pymeasure_d_s_p7265", DSP7265Adapter)

