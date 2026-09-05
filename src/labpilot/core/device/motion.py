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
from typing import Any

__all__ = [
    "DEFAULT_MAX_POLLS",
    "DEFAULT_TOLERANCE",
    "POLL_INTERVAL",
    "is_settled",
    "move_and_settle",
    "move_and_settle_by_moving_flag",
    "resolve_targets",
]

DEFAULT_TOLERANCE = 0.02
DEFAULT_MAX_POLLS = 5000
POLL_INTERVAL = 0.01
"""A real delay, not a bare yield: some actuators simulate (or really do
have) motion coupled to wall-clock time rather than to how often they are
read, so yielding without sleeping spins through `max_polls` before any
real progress happens."""


def is_settled(position: dict[str, Any], targets: dict[str, float],
               tolerance: float = DEFAULT_TOLERANCE) -> bool:
    """Whether every commanded axis has reached its target.

    Split out from `move_and_settle` so the console's synchronous
    instrument handles (`core/notebook_api.py`) decide "has it arrived"
    by the same rule as a workflow template, rather than reimplementing
    it against the same hardware with a different tolerance.
    """
    return all(
        abs(position[axis] - value) <= tolerance for axis, value in targets.items()
    )


def resolve_targets(args: tuple, kwargs: dict, axes: list[str],
                    device_name: str) -> dict[str, float]:
    """Normalise the three move calling conventions to `{axis: value}`.

    `move_abs(5.0)` (single-axis devices only), `move_abs("x", 5.0)`, or
    `move_abs(x=5.0, y=2.0)`. Shared by the in-process `Motor` wrapper and
    the console's remote one so the two accept exactly the same calls.
    """
    if kwargs:
        return {name: float(value) for name, value in kwargs.items()}
    if len(args) == 2 and isinstance(args[0], str):
        return {args[0]: float(args[1])}
    if len(args) == 1:
        if len(axes) != 1:
            raise TypeError(
                f"move_abs(value)/move_rel(value) need exactly one axis, but "
                f"{device_name} has {axes} — use move_abs(axis, value) or "
                f"move_abs(**{{axis: value}}) instead"
            )
        return {axes[0]: float(args[0])}
    raise TypeError(
        "move_abs()/move_rel() need a value (single-axis device), an "
        "(axis, value) pair, or axis=value keyword arguments"
    )


async def move_and_settle(actuator, targets: dict[str, float],
                           tolerance: float = DEFAULT_TOLERANCE,
                           max_polls: int = DEFAULT_MAX_POLLS) -> dict:
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
        if is_settled(position, targets, tolerance):
            return position
        await asyncio.sleep(POLL_INTERVAL)
    raise RuntimeError(f"Actuator did not reach {targets} after {max_polls} polls")


async def move_and_settle_by_moving_flag(actuator, targets: dict[str, float],
                                          moving_key: str = "moving",
                                          max_polls: int = DEFAULT_MAX_POLLS) -> dict:
    """Write `targets`, then poll `read()` until `moving_key` reads False —
    for actuators that report a boolean in-motion flag rather than (or
    instead of relying on) a tolerance-comparable position readback.
    """
    await actuator.write(targets)
    for _ in range(max_polls):
        state = await actuator.read()
        if not state.get(moving_key, False):
            return state
        await asyncio.sleep(POLL_INTERVAL)
    raise RuntimeError(f"Actuator did not settle at {targets} after {max_polls} polls")
