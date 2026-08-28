"""Device protocols and schema for LabPilot."""

from __future__ import annotations

from core.device.protocols import Movable, Readable, Triggerable
from core.device.schema import DeviceSchema

__all__ = ["DeviceSchema", "Movable", "Readable", "Triggerable"]
