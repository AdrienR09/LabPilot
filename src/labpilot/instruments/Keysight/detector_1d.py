"""Auto-generated PyMeasure adapters for keysight instruments (detector_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.keysight classes, verified against the installed
pymeasure library. Type classification ("detector_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.keysight.keysightDSOX1102G import KeysightDSOX1102G
    from pymeasure.instruments.keysight.keysightPNA import KeysightPNA
except ImportError:
    KeysightDSOX1102G = KeysightPNA = None

if KeysightDSOX1102G is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class KeysightDSOX1102GAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysightDSOX1102G.KeysightDSOX1102G."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeysightDSOX1102G, resource=resource, name=name or "pymeasure_keysight_d_s_o_x1102_g", **kwargs)

    adapter_registry.register("pymeasure_keysight_d_s_o_x1102_g", KeysightDSOX1102GAdapter)

    class KeysightPNAAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysightPNA.KeysightPNA."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeysightPNA, resource=resource, name=name or "pymeasure_keysight_p_n_a", **kwargs)

    adapter_registry.register("pymeasure_keysight_p_n_a", KeysightPNAAdapter)

