"""Auto-generated pylablib stage adapters for Arcus (Performax2EXStage, Performax4EXStage, PerformaxDMXJSAStage).

Thin wrappers around PylablibStageAdapter (uses get_position()/move_to(),
verified present on these specific classes — pylablib stages do not share
a fully uniform API, see _generic_pylablib.py).
"""

from __future__ import annotations

try:
    from pylablib.devices import Arcus
except ImportError:
    Arcus = None

if Arcus is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibStageAdapter

    class Performax2EXStageAdapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.Arcus.Performax2EXStage."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Arcus.Performax2EXStage, name=name or "pylablib_performax2_e_x_stage", **device_kwargs)

    adapter_registry.register("pylablib_performax2_e_x_stage", Performax2EXStageAdapter)

    class Performax4EXStageAdapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.Arcus.Performax4EXStage."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Arcus.Performax4EXStage, name=name or "pylablib_performax4_e_x_stage", **device_kwargs)

    adapter_registry.register("pylablib_performax4_e_x_stage", Performax4EXStageAdapter)

    class PerformaxDMXJSAStageAdapter(PylablibStageAdapter):
        """Auto-generated adapter for pylablib.devices.Arcus.PerformaxDMXJSAStage."""

        def __init__(self, name: str | None = None, **device_kwargs) -> None:
            super().__init__(device_class=Arcus.PerformaxDMXJSAStage, name=name or "pylablib_performax_d_m_x_j_s_a_stage", **device_kwargs)

    adapter_registry.register("pylablib_performax_d_m_x_j_s_a_stage", PerformaxDMXJSAStageAdapter)

