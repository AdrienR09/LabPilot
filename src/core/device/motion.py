"""Generic actuator move-and-wait helpers.

Lives under `core/device/` (not `core/workflow_templates/`) so both a
workflow template AND `instruments/kinds.py`'s `Motor` wrapper can use the
same settle-polling logic without `instruments/` (a low-level package other
adapters/drivers depend on) ever importing from `core/workflow_templates/`
(user-editable script templates) — the wrong dependency direction.
`core/workflow_templates/_common.py` re-exports these same two names
unchanged, so no existing template import needs to change.
"""

from __future__ import annotations

import asyncio

__all__ = ["move_and_settle", "move_and_settle_by_moving_flag"]


async def move_and_settle(actuator, targets: dict[str, float], tolerance: float = 0.02,
                           max_polls: int = 5000) -> dict:
    """Write `targets` (one or more axis: value pairs) to `actuator`, then
    poll `read()` until every target axis is within `tolerance` of its
    commanded value — covers both a single generic axis (e.g. a grating
    position) and several at once (e.g. an XY scanner's x and y). For an
    actuator that reports a boolean in-motion flag instead of a
    tolerance-comparable position, see `move_and_settle_by_moving_flag`.

    Raises RuntimeError if `actuator` never settles within `max_polls` —
    fails loudly rather than hanging the workflow forever on
    misconfigured hardware or an out-of-range target.
    """
    await actuator.write(targets)
    for _ in range(max_polls):
        position = await actuator.read()
        if all(abs(position[axis] - value) <= tolerance for axis, value in targets.items()):
            return position
        await asyncio.sleep(0.01)  # real, small delay — some actuators simulate
        # (or really do have) movement coupled to wall-clock time rather
        # than to how often they get read, so a no-op yield here would
        # spin through max_polls before any real progress happens.
    raise RuntimeError(f"Actuator did not reach {targets} after {max_polls} polls")


async def move_and_settle_by_moving_flag(actuator, targets: dict[str, float],
                                          moving_key: str = "moving",
                                          max_polls: int = 5000) -> dict:
    """Write `targets`, then poll `read()` until `moving_key` reads False —
    for actuators that report a boolean in-motion flag rather than (or
    instead of relying on) a tolerance-comparable position readback.
    """
    await actuator.write(targets)
    for _ in range(max_polls):
        state = await actuator.read()
        if not state.get(moving_key, False):
            return state
        await asyncio.sleep(0.01)
    raise RuntimeError(f"Actuator did not settle at {targets} after {max_polls} polls")
