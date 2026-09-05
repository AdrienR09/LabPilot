"""Auto-generated PyMeasure adapters for keysight instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.keysight classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.keysight.keysight33250A import Keysight33250A
    from pymeasure.instruments.keysight.keysight81160A import Keysight81160A
    from pymeasure.instruments.keysight.keysightE3631A import KeysightE3631A
    from pymeasure.instruments.keysight.keysightE36312A import KeysightE36312A
    from pymeasure.instruments.keysight.keysightN5767A import KeysightN5767A
except ImportError:
    Keysight33250A = Keysight81160A = KeysightE36312A = KeysightE3631A = KeysightN5767A = None

if Keysight33250A is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class Keysight33250AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysight33250A.Keysight33250A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keysight33250A, resource=resource, name=name or "pymeasure_keysight33250_a", **kwargs)

    adapter_registry.register("pymeasure_keysight33250_a", Keysight33250AAdapter)

    class Keysight81160AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysight81160A.Keysight81160A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=Keysight81160A, resource=resource, name=name or "pymeasure_keysight81160_a", **kwargs)

    adapter_registry.register("pymeasure_keysight81160_a", Keysight81160AAdapter)

    class KeysightE36312AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysightE36312A.KeysightE36312A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeysightE36312A, resource=resource, name=name or "pymeasure_keysight_e36312_a", **kwargs)

    adapter_registry.register("pymeasure_keysight_e36312_a", KeysightE36312AAdapter)

    class KeysightE3631AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysightE3631A.KeysightE3631A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeysightE3631A, resource=resource, name=name or "pymeasure_keysight_e3631_a", **kwargs)

    adapter_registry.register("pymeasure_keysight_e3631_a", KeysightE3631AAdapter)

    class KeysightN5767AAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.keysight.keysightN5767A.KeysightN5767A."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=KeysightN5767A, resource=resource, name=name or "pymeasure_keysight_n5767_a", **kwargs)

    adapter_registry.register("pymeasure_keysight_n5767_a", KeysightN5767AAdapter)

