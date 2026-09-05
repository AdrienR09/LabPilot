"""Auto-generated PyMeasure adapters for texio instruments (source).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.texio classes, verified against the installed
pymeasure library. Type classification ("source") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.texio.texioPSW360L30 import TexioPSW360L30
except ImportError:
    TexioPSW360L30 = None

if TexioPSW360L30 is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class TexioPSW360L30Adapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.texio.texioPSW360L30.TexioPSW360L30."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=TexioPSW360L30, resource=resource, name=name or "pymeasure_texio_p_s_w360_l30", **kwargs)

    adapter_registry.register("pymeasure_texio_p_s_w360_l30", TexioPSW360L30Adapter)

