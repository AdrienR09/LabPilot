"""Generic, per-InstrumentType methods — the method half of the
"metaobject" (`generic_params.py` is the parameter half). Each mixin is
built entirely on `read()`/`write()`/`stage()`/`unstage()`, so a concrete
adapter gets the generic surface for free the moment it implements the
matching `set_<key>` methods for its type's `GENERIC_PARAMS` — no
per-adapter code needed beyond that.

Opt-in by inheritance, not automatic: `class MyMotor(AdapterBase,
MotorMixin): ...`. Existing adapters are not required to adopt these; this
establishes the pattern for new ones (and for restating what an existing
adapter's generic behavior looks like) rather than retrofitting the
entire ~300-adapter catalog in one pass.
"""

from __future__ import annotations

from typing import Any

__all__ = ["MotorMixin", "DetectorMixin", "SourceMixin"]


class MotorMixin:
    """Generic single-axis actuator (ACTUATOR_0D/1D) methods, in terms of
    the "position" generic parameter (`generic_params.GENERIC_PARAMS`).
    Not for ACTUATOR_ND — multi-axis position key names vary by device."""

    async def move_to(self: Any, position: float) -> None:
        await self.write({"position": position})

    async def home(self: Any) -> None:
        await self.write({"position": 0.0})

    async def position(self: Any) -> float:
        data = await self.read()
        return float(data["position"])


class DetectorMixin:
    """Generic detector (DETECTOR_0D/1D/2D/ND) methods, in terms of the
    "integration_time_ms" generic parameter."""

    async def acquire_once(self: Any) -> dict[str, Any]:
        """Stage, read one frame/reading, unstage — the common
        single-shot acquisition pattern every detector supports."""
        await self.stage()
        try:
            return await self.read()
        finally:
            await self.unstage()

    async def set_integration_time(self: Any, ms: float) -> None:
        await self.write({"integration_time_ms": ms})


class SourceMixin:
    """Generic source (SOURCE) methods, in terms of the "output_enabled"
    generic parameter."""

    async def enable(self: Any) -> None:
        await self.write({"output_enabled": True})

    async def disable(self: Any) -> None:
        await self.write({"output_enabled": False})
