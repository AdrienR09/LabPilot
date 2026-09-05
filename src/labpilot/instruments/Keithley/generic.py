"""Auto-generated PyMeasure adapters for keithley instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.keithley classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.keithley.keithley2306 import Keithley2306
    from pymeasure.instruments.keithley.keithley2510 import Keithley2510
except ImportError:
    Keithley2306 = Keithley2510 = None

if Keithley2306 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Keithley2306Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley2306.Keithley2306."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley2306, resource=resource, name=name or "pymeasure_keithley2306", **kwargs)

    adapter_registry.register("pymeasure_keithley2306", Keithley2306Adapter)

    class Keithley2510Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keithley.keithley2510.Keithley2510."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keithley2510, resource=resource, name=name or "pymeasure_keithley2510", **kwargs)

    adapter_registry.register("pymeasure_keithley2510", Keithley2510Adapter)

