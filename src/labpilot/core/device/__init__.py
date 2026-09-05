"""Device protocols and schema for LabPilot."""

from __future__ import annotations

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.protocols import Readable
from labpilot.core.device.schema import DeviceSchema

__all__ = ["DeviceSchema", "Parameter", "ParamRole", "Readable"]
