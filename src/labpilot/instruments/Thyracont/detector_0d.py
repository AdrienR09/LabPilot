"""Auto-generated PyMeasure adapters for thyracont instruments (detector_0d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.thyracont classes, verified against the installed
pymeasure library. Type classification ("detector_0d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.thyracont.smartline_v1 import SmartlineV1
    from pymeasure.instruments.thyracont.smartline_v2 import (
        VSH,
        VSM,
        VSP,
        VSR,
        SmartlineV2,
    )
except ImportError:
    SmartlineV1 = SmartlineV2 = VSH = VSM = VSP = VSR = None

if SmartlineV1 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class SmartlineV1Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thyracont.smartline_v1.SmartlineV1."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SmartlineV1, resource=resource, name=name or "pymeasure_smartline_v1", **kwargs)

    adapter_registry.register("pymeasure_smartline_v1", SmartlineV1Adapter)

    class SmartlineV2Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thyracont.smartline_v2.SmartlineV2."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=SmartlineV2, resource=resource, name=name or "pymeasure_smartline_v2", **kwargs)

    adapter_registry.register("pymeasure_smartline_v2", SmartlineV2Adapter)

    class VSHAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thyracont.smartline_v2.VSH."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=VSH, resource=resource, name=name or "pymeasure_v_s_h", **kwargs)

    adapter_registry.register("pymeasure_v_s_h", VSHAdapter)

    class VSMAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thyracont.smartline_v2.VSM."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=VSM, resource=resource, name=name or "pymeasure_v_s_m", **kwargs)

    adapter_registry.register("pymeasure_v_s_m", VSMAdapter)

    class VSPAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thyracont.smartline_v2.VSP."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=VSP, resource=resource, name=name or "pymeasure_v_s_p", **kwargs)

    adapter_registry.register("pymeasure_v_s_p", VSPAdapter)

    class VSRAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.thyracont.smartline_v2.VSR."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=VSR, resource=resource, name=name or "pymeasure_v_s_r", **kwargs)

    adapter_registry.register("pymeasure_v_s_r", VSRAdapter)

