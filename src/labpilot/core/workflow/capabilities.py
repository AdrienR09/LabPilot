"""Superseded acquisition helpers, kept for workflows saved as source.

These were the shared move-and-read engines every scanning template was
built on. `core/run/plans.py` replaces them: a plan is described before it
runs, so the buffer, the counters, the progress frames, the per-point
patches, pause and abort belong to `Run` instead of to each caller — and a
scan's axes may span several instruments, where `ScanCapability` takes
exactly one actuator and one detector.

Nothing shipped uses this module any more. It stays because a workflow
*instance* saved before that change is a timestamped copy of its template's
source (see `core/workflow_library/`), and those copies import from here;
deleting it would break workflows a user already has loaded. Re-loading
such a workflow from its template moves it onto plans, after which this
module can go.

The optimizer that lived here is now `core/run/plans.py`'s `OptimizePlan`,
which no saved copy imports.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any, Awaitable, Callable, Optional

import numpy as np

from labpilot.core.analysis.fits import fit_peak, fit_peak_2d
from labpilot.core.workflow_templates._common import detector_axes, move_and_settle

__all__ = ["HardwareTimedScanCapability", "ScanCapability"]

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

# Sanity ceiling on the number of actuator grid points a single run_grid()
# call will attempt. A misconfigured AXIS_RANGES (e.g. 50x50x30 points
# where 5x5x3 was intended) previously ran to the point of building a
# multi-billion-element result array before anything caught it — by then
# the process was already thrashing memory and unresponsive (looked like
# a hang/crash, not a bad-config error). Checked here, once, before any
# hardware motion or detector staging happens, so a bad config fails
# instantly and clearly instead of freezing the whole server partway
# through. Generous enough for legitimate large 1D/2D scans; well under
# what a naive multi-axis point-count typo produces.
_MAX_GRID_POINTS = 200_000


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    n = max(1, int(n))
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


class ScanCapability:
    """Generalized N-D actuator grid scan: iterates every combination of
    one or more actuator axes' declared ranges, reading a detector at each
    point. Deliberately only knows how to move+read+report — it has no
    opinion on how to interpret what the detector returns (a full N-D
    scan keeps every detector-internal axis via `detector_axes()`;
    `OptimizerCapability` reduces each reading to one scalar for fitting)
    — that separation is what lets both consumers share this one class
    instead of each reimplementing move-and-settle.
    """

    def __init__(
        self, actuator, detector, settle_tolerance: float = 0.02, max_settle_polls: int = 5000,
    ) -> None:
        self.actuator = actuator
        self.detector = detector
        self.settle_tolerance = settle_tolerance
        self.max_settle_polls = max_settle_polls

    async def run_grid(
        self,
        axes: list[str],
        axis_ranges: dict[str, tuple[float, float, int]],
        hold_positions: Optional[dict[str, float]] = None,
        on_progress: ProgressCallback = None,
    ) -> dict:
        """Runs one grid scan over `axes` (any length >= 1, ordered —
        first axis varies slowest, matching `itertools.product`'s own
        convention and every existing template's). `hold_positions`, if
        given, is moved to and settled once before the grid starts (axes
        not being scanned this run, parked at a fixed position — same
        semantics as omniscan.py's own HOLD_POSITIONS).

        Returns `{"axes": axes, "positions": [[...], ...] (one list per
        axis, its own linspace), "shape": [...], "readings": [dict, ...]}`
        — `readings` is one full, unprocessed `detector.read()` result per
        point, flat and row-major. Callers reduce/reshape as needed."""
        if hold_positions:
            await move_and_settle(self.actuator, hold_positions, self.settle_tolerance, self.max_settle_polls)

        axis_position_lists = [_linspace(*axis_ranges[name]) for name in axes]
        shape = [len(p) for p in axis_position_lists]
        total = 1
        for n in shape:
            total *= n
        if total > _MAX_GRID_POINTS:
            raise RuntimeError(
                f"This scan's actuator grid would need {total:,} points "
                f"({' x '.join(str(n) for n in shape)} over axes {axes}) — over the "
                f"{_MAX_GRID_POINTS:,}-point safety limit. Reduce AXIS_RANGES' point counts."
            )

        readings: list[dict] = []
        await self.detector.stage()
        try:
            completed = 0
            for combo in itertools.product(*axis_position_lists):
                targets = dict(zip(axes, combo))
                await move_and_settle(self.actuator, targets, self.settle_tolerance, self.max_settle_polls)
                reading = await self.detector.read()
                readings.append(reading)
                completed += 1
                if on_progress is not None:
                    await on_progress({
                        "axes": axes, "positions": axis_position_lists, "shape": shape,
                        "readings": readings, "completed": completed, "total": total,
                    })
        finally:
            await self.detector.unstage()

        return {"axes": axes, "positions": axis_position_lists, "shape": shape, "readings": readings}


class HardwareTimedScanCapability:
    """A whole scan frame driven by one `HardwareScanMixin`-implementing
    device (`instruments/hardware_scan_mixin.py`) instead of
    `ScanCapability`'s per-point actuator-write + detector-read loop — no
    per-pixel software round-trip, since the device itself clocks its
    own position waveform and detector readback together (a real NI DAQ
    card doing this: `instruments/NI/generic.py`'s `NIDAQScannerAdapter`;
    a physically-meaningful mock: `instruments/mock/hardware_scan.py`'s
    `MockNIScanner`). Modeled on Qudi's own
    `ScanningProbeInterface.configure_scan`/`start_scan`/`get_scan_data`
    non-blocking-then-poll pattern (`scanning_probe_logic.py`'s
    `start_scan`), not on anything in `ScanCapability` above — this is a
    different device category, not an optimization of the same one.

    Reports progress in the same shape `ScanCapability`/omniscan's own
    `on_progress` produces (`shape`/`axis_names` not included here —
    the calling template already knows its own axis names; see
    `hardware_timed_scan.py`) specifically so the existing
    `Image2DResultView`/`NDScanResultView` render it with no frontend
    changes at all — a not-yet-acquired cell is `None`, same convention
    `ScanCapability`'s own callers already produce.
    """

    #: How often to poll get_scan_data() while a frame is running.
    POLL_INTERVAL_S = 0.1

    def __init__(self, scanner) -> None:
        self.scanner = scanner

    async def run_scan(
        self,
        axes: list[str],
        ranges: dict[str, tuple[float, float]],
        resolution: dict[str, int],
        frequency: float,
        on_progress: ProgressCallback = None,
    ) -> dict:
        """Configures and runs one whole scan frame. Returns
        `{"axes": axes, "positions": [...], "shape": [...], "data": [...]}` —
        same field names as `ScanCapability.run_grid`'s return, `data`
        flat and row-major (fast axis varies fastest, matching
        `build_scan_waveform`'s acquisition order)."""
        from labpilot.instruments.hardware_scan_mixin import build_scan_waveform

        _flat_waveforms, axis_positions, frame_size = build_scan_waveform(axes, ranges, resolution)
        shape = [len(p) for p in axis_positions]

        await self.scanner.configure_scan(axes, ranges, resolution, frequency)
        await self.scanner.start_scan()
        try:
            while True:
                chunk = await self.scanner.get_scan_data()
                if on_progress is not None:
                    await on_progress({
                        "axes": axes, "positions": axis_positions, "shape": shape,
                        "data": chunk["data"], "completed": chunk["completed"], "total": chunk["total"],
                    })
                if chunk["done"]:
                    break
                await asyncio.sleep(self.POLL_INTERVAL_S)
        finally:
            await self.scanner.stop_scan()

        return {"axes": axes, "positions": axis_positions, "shape": shape, "data": chunk["data"]}
