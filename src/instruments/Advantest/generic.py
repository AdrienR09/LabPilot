"""Auto-generated PyMeasure adapters for advantest instruments (generic).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.advantest classes, verified against the installed
pymeasure library. Type classification ("generic") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.advantest.advantestR3767CG import AdvantestR3767CG
    from pymeasure.instruments.advantest.advantestR624X import AdvantestR6245, AdvantestR6246
except ImportError:
    AdvantestR3767CG = AdvantestR6245 = AdvantestR6246 = None

if AdvantestR3767CG is not None:
    from instruments._generic_pymeasure import PyMeasureGenericAdapter
    from instruments._base import adapter_registry

    class AdvantestR3767CGAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.advantest.advantestR3767CG.AdvantestR3767CG."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AdvantestR3767CG, resource=resource, name=name or "pymeasure_advantest_r3767_c_g", **kwargs)

    adapter_registry.register("pymeasure_advantest_r3767_c_g", AdvantestR3767CGAdapter)

    class AdvantestR6245Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.advantest.advantestR624X.AdvantestR6245."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AdvantestR6245, resource=resource, name=name or "pymeasure_advantest_r6245", **kwargs)

    adapter_registry.register("pymeasure_advantest_r6245", AdvantestR6245Adapter)

    class AdvantestR6246Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.advantest.advantestR624X.AdvantestR6246."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=AdvantestR6246, resource=resource, name=name or "pymeasure_advantest_r6246", **kwargs)

    adapter_registry.register("pymeasure_advantest_r6246", AdvantestR6246Adapter)

