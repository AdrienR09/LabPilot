"""Auto-generated PyMeasure adapters for lakeshore instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.lakeshore classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.lakeshore.lakeshore3xx import LakeShore3xx
    from pymeasure.instruments.lakeshore.lakeshore211 import LakeShore211
    from pymeasure.instruments.lakeshore.lakeshore224 import LakeShore224
    from pymeasure.instruments.lakeshore.lakeshore331 import LakeShore331
    from pymeasure.instruments.lakeshore.lakeshore421 import LakeShore421
    from pymeasure.instruments.lakeshore.lakeshore425 import LakeShore425
except ImportError:
    LakeShore211 = LakeShore224 = LakeShore331 = LakeShore3xx = LakeShore421 = LakeShore425 = None

if LakeShore211 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class LakeShore211Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lakeshore.lakeshore211.LakeShore211."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LakeShore211, resource=resource, name=name or "pymeasure_lake_shore211", **kwargs)

    adapter_registry.register("pymeasure_lake_shore211", LakeShore211Adapter)

    class LakeShore224Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lakeshore.lakeshore224.LakeShore224."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LakeShore224, resource=resource, name=name or "pymeasure_lake_shore224", **kwargs)

    adapter_registry.register("pymeasure_lake_shore224", LakeShore224Adapter)

    class LakeShore331Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lakeshore.lakeshore331.LakeShore331."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LakeShore331, resource=resource, name=name or "pymeasure_lake_shore331", **kwargs)

    adapter_registry.register("pymeasure_lake_shore331", LakeShore331Adapter)

    class LakeShore3xxAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lakeshore.lakeshore3xx.LakeShore3xx."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LakeShore3xx, resource=resource, name=name or "pymeasure_lake_shore3xx", **kwargs)

    adapter_registry.register("pymeasure_lake_shore3xx", LakeShore3xxAdapter)

    class LakeShore421Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lakeshore.lakeshore421.LakeShore421."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LakeShore421, resource=resource, name=name or "pymeasure_lake_shore421", **kwargs)

    adapter_registry.register("pymeasure_lake_shore421", LakeShore421Adapter)

    class LakeShore425Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.lakeshore.lakeshore425.LakeShore425."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=LakeShore425, resource=resource, name=name or "pymeasure_lake_shore425", **kwargs)

    adapter_registry.register("pymeasure_lake_shore425", LakeShore425Adapter)

