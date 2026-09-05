"""Auto-generated PyMeasure adapters for anaheimautomation instruments (actuator_1d).

Thin wrappers around PyMeasureGenericAdapter (introspection-based schema)
for real pymeasure.instruments.anaheimautomation classes, verified against the installed
pymeasure library. Type classification ("actuator_1d") is a best-effort heuristic —
review before relying on it for UI layout decisions.
"""

from __future__ import annotations

try:
    from pymeasure.instruments.anaheimautomation.dpseriesmotorcontroller import (
        DPSeriesMotorController,
    )
except ImportError:
    DPSeriesMotorController = None

if DPSeriesMotorController is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pymeasure import PyMeasureGenericAdapter

    class DPSeriesMotorControllerAdapter(PyMeasureGenericAdapter):
        """Auto-generated adapter for pymeasure.instruments.anaheimautomation.dpseriesmotorcontroller.DPSeriesMotorController."""

        def __init__(self, resource: str, name: str | None = None, **kwargs) -> None:
            super().__init__(instrument_class=DPSeriesMotorController, resource=resource, name=name or "pymeasure_d_p_series_motor_controller", **kwargs)

    adapter_registry.register("pymeasure_d_p_series_motor_controller", DPSeriesMotorControllerAdapter)

