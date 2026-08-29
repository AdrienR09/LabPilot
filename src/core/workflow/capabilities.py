"""Tier-2 capabilities — reusable, object-oriented acquisition behavior
independent of any specific workflow template, per `WORKFLOW_COMPOSITION.md`
(Phase 3's design). `ScanCapability` is the shared move+read engine; both a
full N-D scan (`core/workflow_templates/omniscan.py`) and an optimizer's own
sub-scans (`OptimizerCapability`) are built on it, rather than each
reimplementing actuator movement/settling — the "optimizer requires scan"
relationship expressed as actual shared code, not just documentation.

Generalizes qudi's real confocal optimizer (`scanning_optimize_logic.py`,
`LOGIC_LIBRARY_NOTES.md` §2.1) past its own two ceilings: any number of
actuator axes (not qudi's hardware-native 1D/2D-only scanning-probe
interface) and any detector dimensionality (not qudi's implicit 0D-only
detector — reduced to one scalar per point via `_reduce_to_scalar` before
fitting, the piece pyMoDAQ's ask/tell `model_class.convert_input`,
`LOGIC_LIBRARY_NOTES.md` §2.2, is the closer reference for). Qudi is
LGPLv3; nothing below is copied from it, only the sequence-of-sub-scans
*idea* (a genuine N-D Gaussian fit doesn't exist any more here than it
does in qudi, so N axes are optimized via a sequence of 1D/2D sub-scans,
each fit and centered before the next one runs) is re-derived independently.
"""

from __future__ import annotations

import itertools
from typing import Any, Awaitable, Callable, Optional

import numpy as np

from core.analysis.fits import fit_peak, fit_peak_2d
from core.workflow_templates._common import detector_axes, move_and_settle

__all__ = ["ScanCapability", "OptimizerSequence", "OptimizerCapability"]

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


class OptimizerSequence:
    """Decomposes an arbitrary-length list of actuator axes into a
    sequence of <=2D sub-scan steps — generalizes qudi's own
    `OptimizerScanSequence` (`scanning_optimize_logic.py`,
    `LOGIC_LIBRARY_NOTES.md` §2.1) decomposition *idea* to any axis count.

    Deterministic pairing (declared order, two at a time) rather than
    qudi's full combinatorial search over every valid decomposition —
    qudi's search exists to let a user interactively CHOOSE among several
    equivalent decompositions (its own `available_opt_sequences`); nothing
    here surfaces that choice yet, so this picks the one sensible default
    (e.g. `['x','y','z']` -> `[('x','y'), ('z',)]`, exactly qudi's own
    confocal 3-axis case) instead of enumerating every alternative.
    """

    @staticmethod
    def decompose(axes: list[str]) -> list[tuple[str, ...]]:
        sequence: list[tuple[str, ...]] = []
        remaining = list(axes)
        while remaining:
            sequence.append(tuple(remaining[:2]))
            remaining = remaining[2:]
        return sequence


class OptimizerCapability:
    """Refines/centers an actuator's position around a local maximum of a
    detector reading — built ON `ScanCapability` (see module docstring),
    generalized from qudi's real confocal optimizer past its 1D/2D-actuator/
    0D-detector ceiling.

    `axes` may be any length; `search_range`/`points` are per-axis dicts
    (an axis missing from either falls back to `default_range_fraction` of
    that axis's own declared span in `axis_ranges`, and to 5 points).
    Detector data of any dimensionality is reduced to one scalar per point
    via `_reduce_to_scalar` (sum for a non-scalar reading — a reasonable
    generic "how much signal is here" default; a specific workflow wanting
    a different reduction, e.g. a spectral line's amplitude rather than
    total counts, can pass `reduce_to_scalar` to override it) before
    fitting — qudi's own optimizer has no equivalent step since it never
    handles a non-scalar detector at all.
    """

    def __init__(
        self, actuator, detector, settle_tolerance: float = 0.02, max_settle_polls: int = 5000,
        reduce_to_scalar: Optional[Callable[[dict, str], float]] = None,
    ) -> None:
        self.actuator = actuator
        self.detector = detector
        self.scan = ScanCapability(actuator, detector, settle_tolerance, max_settle_polls)
        self._reduce = reduce_to_scalar or self._default_reduce

    @staticmethod
    def _default_reduce(reading: dict, value_key: str) -> float:
        array = np.asarray(reading[value_key], dtype=float)
        return float(array) if array.ndim == 0 else float(np.sum(array))

    async def run(
        self,
        axes: list[str],
        axis_ranges: dict[str, tuple[float, float, int]],
        search_range: Optional[dict[str, float]] = None,
        points: Optional[dict[str, int]] = None,
        default_range_fraction: float = 0.1,
        on_progress: ProgressCallback = None,
    ) -> dict:
        """Runs the whole optimize sequence (every step in
        `OptimizerSequence.decompose(axes)`), moving to each step's fit
        center before the next one starts. `on_progress`, if given, is
        called with `{"step_index", "step_axes", "sequence", ...grid
        progress...}` for every point of every step, and again with
        `{"step_index", "step_axes", "sequence", "done": True, "fit":
        ..., "values": ..., "positions": ...}` once each step's fit
        completes — enough for a caller to build one live-updating pane
        per sequence step (qudi's own `OptimizerDockWidget`,
        `UI_FRAMEWORK_DESIGN.md` §2.6).

        Returns `{"sequence": [...], "steps": [...], "best_position":
        {axis: value}}`. Stops early (matching qudi's own "abort on a
        failed fit" behavior) if any step's fit doesn't converge.
        """
        search_range = search_range or {}
        points = points or {}
        current = await self.actuator.read()
        sequence = OptimizerSequence.decompose(axes)

        sample = await self.detector.read()
        value_key, _det_names, _det_positions = detector_axes(self.detector.schema.readable, sample)

        best_position = {ax: float(current[ax]) for ax in axes}
        steps_result: list[dict] = []

        for step_index, step_axes in enumerate(sequence):
            ranges: dict[str, tuple[float, float, int]] = {}
            for ax in step_axes:
                lo0, hi0, _n0 = axis_ranges[ax]
                span = search_range.get(ax, abs(hi0 - lo0) * default_range_fraction)
                n = points.get(ax, 5)
                ranges[ax] = (best_position[ax] - span / 2, best_position[ax] + span / 2, n)

            async def _step_progress(grid_progress: dict, step_index=step_index, step_axes=step_axes) -> None:
                if on_progress is not None:
                    # Reduce each raw reading to its scalar now, same as
                    # the step's own final values below — never forward
                    # `grid_progress["readings"]` itself: a detector's raw
                    # reading can hold a live numpy array (any ND
                    # detector), not JSON-serializable once this reaches
                    # server.py's HTTP response. Pre-allocated to the
                    # step's full point count (None for not-yet-reached
                    # points, same pattern omniscan.py's own progress
                    # array uses) rather than just what's completed so
                    # far — a caller reshaping this into the step's known
                    # (2D) shape needs the full length even mid-step.
                    values: list[Optional[float]] = [None] * grid_progress["total"]
                    for i, reading in enumerate(grid_progress["readings"]):
                        values[i] = self._reduce(reading, value_key)
                    await on_progress({
                        "step_index": step_index, "step_axes": step_axes, "sequence": sequence,
                        "done": False, "positions": grid_progress["positions"], "shape": grid_progress["shape"],
                        "values": values, "completed": grid_progress["completed"], "total": grid_progress["total"],
                    })

            grid = await self.scan.run_grid(list(step_axes), ranges, on_progress=_step_progress)
            values = [self._reduce(reading, value_key) for reading in grid["readings"]]

            fit: Optional[dict]
            if len(step_axes) == 1:
                x = grid["positions"][0]
                fit = fit_peak(x, values)
                if fit is not None:
                    best_position[step_axes[0]] = fit["center"]
            else:
                x, y = grid["positions"]
                z = np.array(values, dtype=float).reshape(len(x), len(y))
                fit = fit_peak_2d(x, y, z)
                if fit is not None:
                    best_position[step_axes[0]] = fit["center_x"]
                    best_position[step_axes[1]] = fit["center_y"]

            step_record = {
                "step_index": step_index, "step_axes": step_axes, "positions": grid["positions"],
                "values": values, "shape": grid["shape"], "fit": fit,
            }
            steps_result.append(step_record)
            if on_progress is not None:
                await on_progress({
                    "step_index": step_index, "step_axes": step_axes, "sequence": sequence,
                    "done": True, **step_record,
                })

            if fit is None:
                break  # matches qudi's own "stop the whole optimize on a failed fit"

            move_targets = {ax: best_position[ax] for ax in step_axes}
            await move_and_settle(self.actuator, move_targets, self.scan.settle_tolerance, self.scan.max_settle_polls)

        return {"sequence": sequence, "steps": steps_result, "best_position": best_position}
