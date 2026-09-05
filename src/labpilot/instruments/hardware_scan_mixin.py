"""Hardware-timed scan contract — for a device that drives a scan axis'
position waveform and reads a detector back in lockstep, both clocked by
one shared hardware timebase (a NI DAQ card's sample clock, in practice),
with zero per-pixel software round-trip. Modeled directly on Qudi's real
`ScanningProbeInterface`/NI hardware module
(github.com/Ulm-IQO/qudi-iqo-modules — `interface/scanning_probe_interface.py`,
`hardware/ni_x_series/ni_x_series_finite_sampling_io.py`,
`hardware/interfuse/ni_scanning_probe_interfuse.py`), scoped to what that
reference implementation actually supports: 1D or 2D scans, since only
the fast (first) axis is genuinely hardware-clocked — a 3rd
simultaneously-hardware-timed axis isn't a real capability of this class
of card.

This is a fundamentally different contract from `AdapterBase.read()`/
`write()` — a scan isn't composable from repeated point reads/writes the
way `instruments/mixins.py`'s `MotorMixin`/`DetectorMixin` are, so this
mixin declares real (`NotImplementedError`-stub) methods instead of
building on the generic read/write dispatch. Opt-in by inheritance, same
convention as that module: `class MyScanner(HardwareScanMixin, AdapterBase): ...`.

See `core/workflow/capabilities.py`'s `HardwareTimedScanCapability` for
the engine that drives this contract, and
`core/workflow_library/hardware_timed_scan.py` for the workflow template
built on it.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["HardwareScanMixin", "build_scan_waveform"]


def build_scan_waveform(
    axes: list[str], ranges: dict[str, tuple[float, float]], resolution: dict[str, int],
) -> tuple[dict[str, np.ndarray], list[np.ndarray], int]:
    """The position waveform for one whole scan frame, built once ahead of
    time — mirrors the interfuse's own `_get_scan_lines()`: the fast
    (first) axis is tiled once per row of the slow axis, the slow axis is
    repeated once per fast-axis sample, both ending up as flat per-sample
    arrays of the same length (`frame_size`) in acquisition order (fast
    axis varies fastest). No flyback/backscan — out of scope here (see
    the workflow template's docstring).

    Returns `(flat_waveforms, axis_positions, frame_size)`:
    - `flat_waveforms`: `{axis: ndarray}`, one flat per-sample drive
      waveform per axis, length `frame_size` — what a real adapter hands
      to its AO task.
    - `axis_positions`: `[ndarray, ...]`, one per axis in `axes` order,
      each axis' own (non-flattened) linspace — for reshaping/labeling
      the final image, matching `ScanCapability.run_grid`'s own
      `positions` convention.
    - `frame_size`: total sample count.
    """
    if len(axes) == 1:
        axis = axes[0]
        lo, hi = ranges[axis]
        n = int(resolution[axis])
        positions = np.linspace(lo, hi, n)
        return {axis: positions}, [positions], n
    if len(axes) == 2:
        fast_axis, slow_axis = axes
        lo_f, hi_f = ranges[fast_axis]
        lo_s, hi_s = ranges[slow_axis]
        n_f, n_s = int(resolution[fast_axis]), int(resolution[slow_axis])
        fast_positions = np.linspace(lo_f, hi_f, n_f)
        slow_positions = np.linspace(lo_s, hi_s, n_s)
        flat_fast = np.tile(fast_positions, n_s)
        flat_slow = np.repeat(slow_positions, n_f)
        return {fast_axis: flat_fast, slow_axis: flat_slow}, [fast_positions, slow_positions], n_f * n_s
    raise ValueError(f"HardwareScanMixin only supports 1D or 2D scans, got axes={axes!r}")


class HardwareScanMixin:
    """A device that can scan a hardware-clocked position waveform against
    a synchronized detector readback, configured once per whole frame."""

    async def configure_scan(
        self, axes: list[str], ranges: dict[str, tuple[float, float]],
        resolution: dict[str, int], frequency: float,
    ) -> None:
        """Programs the whole frame (position waveform + synchronized
        detector clock) ahead of time — does not start acquiring yet (see
        `start_scan`). `frequency` is the fast (first) axis' pixel rate,
        in Hz — matching `ScanSettings.frequency`'s own convention."""
        raise NotImplementedError

    async def start_scan(self) -> None:
        """Starts the already-configured frame's hardware-clocked
        acquisition. Returns immediately — poll `get_scan_data()` for
        progress, same as Qudi's own non-blocking `start_scan()`."""
        raise NotImplementedError

    async def get_scan_data(self) -> dict[str, Any]:
        """Whatever's been acquired so far: `{"data": flat list — one
        entry per sample in acquisition order, `None` for a not-yet-
        acquired cell, "completed": int, "total": int, "done": bool}`.
        Safe to call repeatedly while a scan is running or after it's
        finished (returns the same, complete data)."""
        raise NotImplementedError

    async def stop_scan(self) -> None:
        """Stops the frame's hardware task, whether it finished or was
        cancelled early."""
        raise NotImplementedError
