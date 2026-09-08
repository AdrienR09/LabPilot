"""Which axes a workflow scans, read from its own parameters.

A template declares its grid as module-level constants — omniscan-style
`AXIS_RANGES` + `SCAN_AXES`, or a fixed `X_POSITIONS`/`Y_POSITIONS` pair
with the axis names coming from `RESULT_UI`'s crosshair. Turning that into
"the axes this run actually sweeps" means intersecting the declaration with
what the bound actuator can really move: `AXIS_RANGES` is authored
generically (x/y/z) while the instrument bound to the role may only have
some of them.

That intersection was computed in two places — `server.py`, to decide what
the optimizer sweeps and which step each progress update belongs to, and
`workflow_window.py`, to lay out one optimizer pane per step. Their own
docstrings said they "must agree", and one of them recorded the case where
they do not: narrowing the axis set can change how the *remaining* axes
pair up, so the server recomputes a decomposition the panes were not built
from and a step's results land in the wrong pane.

Two copies of a rule cannot be made to agree by saying they must. This is
the rule, once, as a pure function of the parameters and the actuator's
settable names — no session, no hardware, no Qt — so both callers get the
same answer by construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = ["resolve_scan_axes", "settable_names"]

#: The span given to an axis whose workflow declares no positions for it.
#: Harmless: it only seeds a default search range, which the caller
#: overrides whenever it has a real one.
_PLACEHOLDER_SPAN = (-0.5, 0.5, 5)


def settable_names(actuator_schema: Any) -> set[str]:
    """The parameters an actuator can be told to move.

    Accepts a `DeviceSchema` (the server holds one) or the plain dict the
    REST API serves (what the desktop app has), because the two callers of
    `resolve_scan_axes` each have a different one and the difference is not
    interesting to the rule.
    """
    if actuator_schema is None:
        return set()
    settable = getattr(actuator_schema, "settable", None)
    if settable is None and isinstance(actuator_schema, dict):
        settable = actuator_schema.get("settable")
    return set(settable or ())


def resolve_scan_axes(
    params: Mapping[str, Any],
    actuator_schema: Any = None,
    x_axis: str | None = None,
    y_axis: str | None = None,
    requested_axes: Sequence[str] | None = None,
) -> tuple[list[str], dict[str, tuple[float, float, int]]]:
    """The axes this workflow sweeps, and each one's declared span.

    Prefers an omniscan-style `AXIS_RANGES`/`SCAN_AXES` declaration — any
    number of axes, intersected with what the bound actuator actually has.
    Falls back to the crosshair's fixed `x_axis`/`y_axis` pair for a
    workflow that declares neither (confocal_scanner.py), taking a span
    from whatever `X_POSITIONS`/`Y_POSITIONS` list it has.

    `requested_axes` narrows the result to a subset — "optimize along one
    dimension or several". A requested axis this workflow does not have is
    dropped rather than raising, matching how an unavailable `SCAN_AXES`
    entry is already treated.

    The span is `(start, stop, points)` and is only ever used to *derive a
    default*; a caller with a real range of its own passes it instead.
    """
    # No schema at all means "do not filter" — the desktop app resolves
    # these before it knows which instrument is bound. An actuator that
    # declares nothing settable is a different case, and does filter
    # everything out, which falls through to the crosshair pair below.
    available = settable_names(actuator_schema) if actuator_schema is not None else None
    axis_ranges = params.get("AXIS_RANGES")
    scan_axes = params.get("SCAN_AXES")

    if isinstance(axis_ranges, dict) and isinstance(scan_axes, list):
        axes = [
            axis for axis in scan_axes
            if axis in axis_ranges and (available is None or axis in available)
        ]
        if axes:
            axes = _narrow(axes, requested_axes)
            return axes, {axis: tuple(axis_ranges[axis]) for axis in axes}

    axes = _narrow([axis for axis in (x_axis, y_axis) if axis], requested_axes)
    ranges: dict[str, tuple[float, float, int]] = {}
    for axis, list_key in ((x_axis, "X_POSITIONS"), (y_axis, "Y_POSITIONS")):
        if not axis:
            continue
        positions = params.get(list_key)
        if isinstance(positions, list) and len(positions) >= 2:
            ranges[axis] = (float(min(positions)), float(max(positions)), len(positions))
        else:
            ranges[axis] = _PLACEHOLDER_SPAN
    return axes, ranges


def _narrow(axes: list[str], requested: Iterable[str] | None) -> list[str]:
    if requested is None:
        return axes
    return [axis for axis in requested if axis in axes]
