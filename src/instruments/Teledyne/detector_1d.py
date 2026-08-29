"""Auto-generated PyMeasure adapters for teledyne instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.teledyne classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.teledyne.teledyneMAUI import TeledyneMAUI
    from pymeasure.instruments.teledyne.teledyne_oscilloscope import TeledyneOscilloscope
except ImportError:
    TeledyneMAUI = TeledyneOscilloscope = None

if TeledyneMAUI is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class TeledyneMAUIAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.teledyne.teledyneMAUI.TeledyneMAUI."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TeledyneMAUI, resource=resource, name=name or "pymeasure_teledyne_m_a_u_i", **kwargs)

    adapter_registry.register("pymeasure_teledyne_m_a_u_i", TeledyneMAUIAdapter)

    class TeledyneOscilloscopeAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.teledyne.teledyne_oscilloscope.TeledyneOscilloscope."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TeledyneOscilloscope, resource=resource, name=name or "pymeasure_teledyne_oscilloscope", **kwargs)

    adapter_registry.register("pymeasure_teledyne_oscilloscope", TeledyneOscilloscopeAdapter)

