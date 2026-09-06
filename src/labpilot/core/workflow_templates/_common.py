"""Shared helpers for role-based workflow templates (core/workflow_templates/).

Every template references its instruments by role (`session.get(ROLE)`) and
returns a plain dict — the spectrum-key-detection logic below was previously
copy-pasted near-identically into several templates; extracted here so a new
template doesn't need to re-derive it, and a fix only has to land in one
place.

`move_and_settle`/`move_and_settle_by_moving_flag` themselves now live in
`core/device/motion.py` (re-exported here unchanged) — `instruments/kinds.py`'s
`Motor.move_abs()`/`.move_rel()` need the exact same settle-polling logic,
and `instruments/` must not import from `core/workflow_templates/` (a
low-level driver-wrapping package depending on user-editable script
templates would be the wrong dependency direction).
"""

from __future__ import annotations

import numpy as np

from labpilot.core.data.dataset import Dataset
from labpilot.core.device.motion import move_and_settle, move_and_settle_by_moving_flag
from labpilot.core.device.parameter import ParamRole
from labpilot.core.device.schema import DeviceSchema

__all__ = [
    "move_and_settle", "move_and_settle_by_moving_flag", "integration_time_key", "spectrum_key",
    "detector_axes",
]

_AXIS_KEY_HINTS = ("wavelength", "wavelengths", "time", "times", "frequency", "frequencies")


def integration_time_key(detector) -> str | None:
    """This detector's integration-time settable key name, or None.

    Different adapters name it integration_time_ms, integration_time_s,
    exposure_time_ms, ... The adapter tags whichever one it is (see
    `core/device/parameter.py`), so this asks the schema rather than
    searching its key names for a substring — the same question the Qt
    settings dock and `core/device/kinds.py` also used to answer for
    themselves, with two different rules between them.
    """
    parameter = detector.schema.integration_time
    return parameter.name if parameter is not None else None


def spectrum_key(detector) -> str:
    """This detector's value-array readable key name.

    Now one question asked of the schema (`DeviceSchema.primary`) rather
    than a rule about names. The old rule — everything except a key
    containing "wavelength", take the first — returned the *axis* for a
    Raman spectrometer reporting `shift`/`intensity`.
    """
    primary = detector.schema.primary
    if primary is not None:
        return primary.name
    return next(iter(detector.schema.readable))


def detector_axes(readable, sample_reading: dict) -> tuple[str, list[str], list[list[float]]]:
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
    # A reading is a `Dataset` now (core/data/dataset.py) and answers this
    # outright — which array is the measurement, which axes index it, in
    # what units — so nothing below runs for a live detector. The rest is
    # the compatibility path for a workflow instance saved as source
    # before `Dataset` existed, which passes the legacy `schema.readable`
    # dict and a plain dict reading.
    if isinstance(sample_reading, Dataset):
        primary = sample_reading.primary()
        axes = sample_reading.axes()
        return (
            primary.name,
            [axis.name for axis in axes],
            [[float(v) for v in axis.values] for axis in axes],
        )

    schema = readable if isinstance(readable, DeviceSchema) else None
    declared_axis = None
    if schema is not None:
        readable = schema.readable
        declared = schema.find(role=ParamRole.AXIS, readable=True)
        declared_axis = declared[0].name if declared else None

    array_keys = [k for k, dt in readable.items() if isinstance(dt, str) and dt.startswith("ndarray")]
    if not array_keys:
        # 0D — no extra axes; a single scalar reading per actuator
        # position, the original omniscan behavior.
        value_key = next(iter(readable.keys()))
        return value_key, [], []

    axis_key = declared_axis or next(
        (k for k in array_keys if k.lower() in _AXIS_KEY_HINTS), None
    )
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
