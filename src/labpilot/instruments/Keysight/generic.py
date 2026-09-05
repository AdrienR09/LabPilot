"""Auto-generated PyMeasure adapters for keysight instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.keysight classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.keysight.keysightN7776C import KeysightN7776C
except ImportError:
    KeysightN7776C = None

if KeysightN7776C is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class KeysightN7776CAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysightN7776C.KeysightN7776C."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeysightN7776C, resource=resource, name=name or "pymeasure_keysight_n7776_c", **kwargs)

    adapter_registry.register("pymeasure_keysight_n7776_c", KeysightN7776CAdapter)

