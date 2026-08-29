"""Shared helpers for role-based workflow templates (core/workflow_templates/).

Every template references its instruments by role (`session.get(ROLE)`) and
returns a plain dict — the settle-wait and spectrum-key-detection logic
below was previously copy-pasted near-identically into several templates;
extracted here so a new template doesn't need to re-derive it, and a fix
(e.g. a better settle heuristic) only has to land in one place.
"""

from __future__ import annotations

import asyncio

import numpy as np

__all__ = [
    "move_and_settle", "move_and_settle_by_moving_flag", "integration_time_key", "spectrum_key",
    "detector_axes",
]

_AXIS_KEY_HINTS = ("wavelength", "wavelengths", "time", "times", "frequency", "frequencies")


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


def integration_time_key(detector) -> str | None:
    """This detector's integration-time-like settable key name, or None if
    it doesn't have one — different adapters name it integration_time_ms,
    integration_time_s, etc., checked generically by substring rather than
    one hardcoded name.
    """
    for key in detector.schema.settable:
        if "integration_time" in key:
            return key
    return None


def spectrum_key(detector) -> str:
    """This 1D detector's intensity-array readable key name. Different
    adapters name it "spectrum", "intensities", etc.; "wavelength(s)" is
    the one readable that's never the value channel, so exclude it and
    take whatever's left.
    """
    readable = detector.schema.readable
    candidates = [k for k in readable if "wavelength" not in k.lower()]
    return candidates[0] if candidates else next(iter(readable))


def detector_axes(readable: dict, sample_reading: dict) -> tuple[str, list[str], list[list[float]]]:
    """(value_key, axis_names, axis_positions) describing a bound
    detector's OWN internal axes — empty for a 0D detector (a single
    scalar reading), one extra axis for a 1D detector (e.g. a
    spectrometer's wavelength axis), N extra axes for a genuinely ND
    detector (e.g. `MockBasicDetectorND`'s (x, y, wavelength)
    hyperspectral cube, `readable={"cube": "ndarray3d"}` —
    instruments/MockBasic/simple.py). These axes are never movable/
    scannable by any actuator (see omniscan.py) — just extra dimensions
    of what the detector hands back at every actuator position,
    generalizing a 0D-only detector to any dimensionality the same way
    omniscan generalizes a fixed xy actuator to any ND one.

    Rank is read off the *actual returned array's* `.ndim` rather than
    parsed from the dtype string (an earlier version matched literal
    `"ndarray1d"`/`"ndarray2d"` strings only, so a real `"ndarray3d"`
    detector silently fell through to the 0D case and its whole cube got
    treated as a single scalar) — this way any rank works without this
    function needing to enumerate `"ndarray1d"`, `"ndarray2d"`,
    `"ndarray3d"`, `"ndarray4d"`, ... by name as new ones appear.

    `sample_reading` (one real `read()` call, taken once up front before
    the main scan loop) is needed to learn the array's actual shape and,
    for a 1D detector with a companion axis-array reading (e.g.
    "wavelengths" alongside "spectrum"), its real per-sample values — a
    schema alone only declares dtypes, not sizes.
    """
    array_keys = [k for k, dt in readable.items() if isinstance(dt, str) and dt.startswith("ndarray")]
    if not array_keys:
        # 0D — no extra axes; a single scalar reading per actuator
        # position, the original omniscan behavior.
        value_key = next(iter(readable.keys()))
        return value_key, [], []

    axis_key = next((k for k in array_keys if k.lower() in _AXIS_KEY_HINTS), None)
    value_key = next((k for k in array_keys if k != axis_key), array_keys[0])
    array = np.asarray(sample_reading[value_key])

    if array.ndim == 1:
        if axis_key and axis_key in sample_reading:
            positions = [float(v) for v in sample_reading[axis_key]]
            name = axis_key
        else:
            positions = list(range(array.shape[0]))
            name = "sample"
        return value_key, [name], [positions]

    # 2D+ — no physical calibration assumed generically (that's what a
    # specific template like grating_spectrometer.py's own per-instrument
    # calibration logic does manually); index positions per own axis.
    # "row"/"col" matches the existing 2D naming convention already relied
    # on elsewhere; 3+ axes get a generic "dim{i}" name each.
    if array.ndim == 2:
        axis_names = ["row", "col"]
    else:
        axis_names = [f"dim{i}" for i in range(array.ndim)]
    axis_positions = [list(range(n)) for n in array.shape]
    return value_key, axis_names, axis_positions
