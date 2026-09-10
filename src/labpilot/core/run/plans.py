"""Plans — what to acquire, as an object rather than a hand-written loop.

A plan answers two questions and nothing else:

    describe(session) -> RunDescriptor     what this will produce
    points(session, descriptor)            one DatasetPatch per point

`Run` owns everything around them: the buffer, the counters, the progress
event, the patch stream, pause and abort. So a plan is a short async
generator, and the acquisition behaviour that today lives in fifteen
template files lives once.

## What the generalisation is

`ScanCapability` — the one real logic library here — takes exactly **one**
actuator and **one** detector. That single constraint is why most templates
cannot use it and hand-roll their loop instead. `odmr_sweep.py` is the clean
example: it steps a *source's* frequency, not a motor's position, so it
reimplements move-settle-read even though the pattern is identical.

Here an axis names a device and a parameter on it:

    ScanAxis("frequency", device="source", start=2.82e9, stop=2.86e9, points=21)
    ScanAxis("x", device="stage", start=-4.0, stop=4.0, points=51)

so one grid can span several devices — an XY stage plus a separate piezo, a
stage plus a swept source — which nothing in the codebase can express today.
Whether an axis is *drivable* stops being the template-maintained integer
`actuator_axis_count` and becomes `Axis.movable`, a property of the axis.

## Where the shape comes from

`describe()` reads the detector once. A schema declares that a spectrometer
returns a 1-D array but not that it is 2048 long, so the length has to be
asked for. Templates discover it on their first point and allocate
mid-flight; asking once, up front, is what lets the run be allocated,
counted and streamed by something other than the template.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np

from labpilot.core.data.dataset import Axis, DatasetPatch
from labpilot.core.device.motion import (
    DEFAULT_MAX_POLLS,
    DEFAULT_TOLERANCE,
    move_and_settle,
)
from labpilot.core.run.descriptor import RunDescriptor
from labpilot.core.run.requests import _register_all as _register_transports

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence

    from labpilot.core.session import Session

__all__ = [
    "HardwareTimedScanPlan",
    "OptimizePlan",
    "Plan",
    "PulsedMeasurementPlan",
    "ScanAxis",
    "ScanPlan",
    "ScriptPlan",
    "TimeSeriesPlan",
    "decompose",
]

# A run whose grid is this large is a misconfiguration, not an experiment:
# `AXIS_RANGES` typed as 50x50x30 where 5x5x3 was meant used to allocate a
# multi-billion-element array and thrash memory with nothing said about why.
# Checked in describe(), before any hardware moves.
MAX_POINTS = 200_000
MAX_ELEMENTS = 50_000_000


@runtime_checkable
class Plan(Protocol):
    """What `Run` needs from anything acquirable."""

    name: str

    async def describe(self, session: Session) -> RunDescriptor:
        """Everything knowable before the first point."""
        ...

    def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        """One patch per acquired point, in flat row-major order."""
        ...


@dataclass(frozen=True, slots=True)
class ScanAxis:
    """One swept dimension: a device, a parameter on it, and a range.

    `device` is a role name (`"actuator"`, `"source"`) or a registered
    instrument id — whatever `session.get()` resolves.
    """

    name: str
    device: str
    start: float
    stop: float
    points: int
    unit: str = ""

    @property
    def values(self) -> np.ndarray:
        if self.points <= 1:
            return np.asarray([self.start], dtype=float)
        return np.linspace(self.start, self.stop, int(self.points))


def scan_axes(
    over: Mapping[str, tuple[float, float, int]], using: str | None = None
) -> list[ScanAxis]:
    """`{"stage.x": (0, 10, 51)}` as `ScanAxis` objects.

    The sugar `lp.scan()` and `labpilot.script.scan()` both take, kept in
    one place so the console and a script cannot disagree about what
    `"stage.x"` means or which errors it gives.
    """
    if not over:
        raise ValueError("A scan needs at least one axis in `over`")

    axes: list[ScanAxis] = []
    for key, span in over.items():
        device, _, parameter = key.rpartition(".")
        device = device or using
        if not device:
            raise ValueError(
                f"{key!r} does not say which instrument to move — write it as "
                f"'instrument.{parameter}', or pass using='instrument'."
            )
        try:
            start, stop, points = span
        except (TypeError, ValueError):
            raise ValueError(
                f"Axis {key!r} needs (start, stop, points), got {span!r}"
            ) from None
        axes.append(
            ScanAxis(parameter, device, float(start), float(stop), int(points))
        )
    return axes


@dataclass
class ScanPlan:
    """Move over a grid, read a detector at every point.

    Axes vary in declared order with the **first varying slowest**, which
    is `itertools.product`'s own convention and the one every existing
    template and result view already assumes.
    """

    axes: list[ScanAxis]
    detector: str = "detector"
    name: str = "scan"
    hold: dict[str, float] = field(default_factory=dict)
    """Parameters to park once, before the grid starts — the axes a device
    has that this run is not sweeping (omniscan's `HOLD_POSITIONS`)."""
    hold_device: str | None = None
    """Which device `hold` names parameters of. Defaults to the first
    axis's device, which is the ordinary case: the other axes of the same
    stage."""
    settle_tolerance: float = DEFAULT_TOLERANCE
    max_settle_polls: int = DEFAULT_MAX_POLLS
    params: dict[str, Any] = field(default_factory=dict)

    async def describe(self, session: Session) -> RunDescriptor:
        detector = session.get(self.detector)
        scan_axes = tuple(
            Axis(
                name=axis.name,
                values=axis.values,
                unit=axis.unit or _unit_of(session, axis.device, axis.name),
                kind="actuator",
                device=axis.device,
                param=axis.name,
            )
            for axis in self.axes
        )
        points = int(np.prod([len(a) for a in scan_axes], dtype=int)) if scan_axes else 0
        if points > MAX_POINTS:
            raise ValueError(
                f"This scan's grid would need {points:,} points "
                f"({' x '.join(str(len(a)) for a in scan_axes)}) — over the "
                f"{MAX_POINTS:,}-point safety limit. Reduce the point counts."
            )

        # One reading, to learn what a point actually contains: a schema
        # declares a spectrometer returns a 1-D array, not that it is 2048
        # long. This is the single hardware touch in describe().
        sample = await detector.read()
        primary = sample.primary()
        detector_axes = tuple(sample.axes()) if primary.ndim else ()

        descriptor = RunDescriptor(
            run_uid=str(uuid.uuid4()),
            plan_name=self.name,
            axes=scan_axes + detector_axes,
            scan_axis_count=len(scan_axes),
            value_name=primary.name or "data",
            value_unit=primary.unit,
            devices={
                role: session.get(role).schema.model_dump(mode="json")
                for role in {*(a.device for a in self.axes), self.detector}
                if session.has(role)
            },
            params=dict(self.params),
        )
        if descriptor.size > MAX_ELEMENTS:
            raise ValueError(
                f"This scan's result would need {descriptor.size:,} elements "
                f"({descriptor.points:,} points x {descriptor.per_point:,} values "
                f"per point) — over the {MAX_ELEMENTS:,}-element safety limit. "
                f"Reduce the point counts or the detector's resolution."
            )
        return descriptor

    async def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        detector = session.get(self.detector)
        per_point = descriptor.per_point

        if self.hold:
            device = self.hold_device or (self.axes[0].device if self.axes else None)
            if device is not None:
                await self._command(session.get(device), dict(self.hold))

        await detector.stage()
        try:
            grid = itertools.product(*(axis.values for axis in self.axes))
            for index, combination in enumerate(grid):
                position = dict(zip((a.name for a in self.axes), combination, strict=True))
                for device, targets in _by_device(position, self.axes).items():
                    await self._command(session.get(device), targets)
                reading = await detector.read()
                values = np.asarray(
                    reading[descriptor.value_name], dtype=float
                ).ravel()
                yield DatasetPatch(
                    array=descriptor.value_name,
                    index=index * per_point,
                    values=values,
                    run_uid=descriptor.run_uid,
                    seq=index + 1,
                )
        finally:
            # Runs on an abort too: the detector is never left staged.
            await detector.unstage()

    async def _command(self, device: Any, targets: dict[str, float]) -> None:
        """Set this point's coordinates on one device, and wait if waiting
        means anything.

        A stage reads its position back, so the move is complete only once
        the read-back agrees — that is `move_and_settle`. A source often
        does not: `mock_microwave_source` is set through `cw_frequency` and
        reports through `frequency`, so polling for a read-back of the name
        that was written waits forever on a key that will never exist.
        Settling therefore applies exactly when the device reads back the
        parameter that was written, which is a fact its schema already
        states.
        """
        readable = getattr(device.schema, "readable", {}) or {}
        if all(name in readable for name in targets):
            await move_and_settle(
                device, targets, self.settle_tolerance, self.max_settle_polls
            )
            return
        await device.write(targets)


def decompose(axes: Sequence[str]) -> list[tuple[str, ...]]:
    """An axis list as a sequence of at-most-2D optimize steps.

    `['x', 'y', 'z']` -> `[('x', 'y'), ('z',)]`, which is qudi's own
    confocal three-axis case. Generalizes its `OptimizerScanSequence`
    decomposition idea to any axis count; a genuine N-D peak fit exists
    here no more than it does there, so N axes are optimized as a sequence
    of 1-D and 2-D sub-scans, each fit and centred before the next.

    Deterministic pairing in declared order rather than qudi's
    combinatorial search over every valid decomposition: that search exists
    to let a user interactively choose among equivalent decompositions, and
    nothing here surfaces that choice yet.
    """
    steps: list[tuple[str, ...]] = []
    remaining = list(axes)
    while remaining:
        steps.append(tuple(remaining[:2]))
        remaining = remaining[2:]
    return steps


@dataclass
class OptimizePlan:
    """Re-centre an actuator on a local maximum of a detector's reading.

    A sequence of small sub-scans, each fit and centred before the next —
    and each of them *is* a `ScanPlan`, which is the "an optimizer is built
    on a scan" relationship expressed as shared code rather than
    documentation.

    ## Why its coordinates are a point index

    Every other plan knows its axes' coordinates before it starts. This one
    cannot: each step scans around the position the *previous* step's fit
    produced, so where step 2 will look is not knowable until step 1 has
    run. The descriptor is honest about that — one index axis over the
    probe points — and each step's real positions are reported with the
    step, where they are known. Inventing coordinates up front would be the
    kind of convention that is right until a fit moves.

    Detector data of any dimensionality is reduced to one scalar per point
    (`sum` by default — a reasonable "how much signal is here"; pass
    `reduce` for something else, e.g. a spectral line's amplitude rather
    than total counts). Qudi's optimizer has no equivalent step because it
    never handles a non-scalar detector at all.
    """

    axes: list[str]
    axis_ranges: dict[str, tuple[float, float, int]]
    actuator: str = "actuator"
    detector: str = "detector"
    search_range: dict[str, float] | None = None
    points_per_axis: dict[str, int] | None = None
    """Probe points per axis. Named for the axis rather than as `points`,
    which on this class would shadow the `points()` every plan defines."""
    default_range_fraction: float = 0.1
    settle_tolerance: float = DEFAULT_TOLERANCE
    max_settle_polls: int = DEFAULT_MAX_POLLS
    name: str = "optimize"
    on_step: Callable[[dict], Awaitable[None]] | None = None
    """Called with each step's live progress and again when it is fit —
    the payload the optimizer panel renders, one pane per step."""
    reduce: Callable[[np.ndarray], float] | None = None

    #: Filled in as the sequence runs.
    sequence: list[tuple[str, ...]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    best_position: dict[str, float] = field(default_factory=dict)

    async def describe(self, session: Session) -> RunDescriptor:
        detector = session.get(self.detector)
        self.sequence = decompose(self.axes)
        per_axis = self.points_per_axis or {}
        total = sum(
            int(np.prod([max(2, per_axis.get(axis, 5)) for axis in step], dtype=int))
            for step in self.sequence
        )
        sample = await detector.read()
        return RunDescriptor(
            run_uid=str(uuid.uuid4()),
            plan_name=self.name,
            axes=(Axis("point", np.arange(total), kind="index"),),
            scan_axis_count=1,
            value_name="data",
            value_unit=sample.primary().unit,
            # The index axis cannot say what this drives, so it is named.
            driven=(self.actuator,),
            devices={
                role: session.get(role).schema.model_dump(mode="json")
                for role in (self.actuator, self.detector) if session.has(role)
            },
            params={
                "optimize_axes": list(self.axes),
                "sequence": [list(step) for step in self.sequence],
            },
        )

    async def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        from labpilot.core.analysis.fits import fit_peak, fit_peak_2d

        reduce = self.reduce or (lambda values: float(np.sum(values)))
        actuator = session.get(self.actuator)
        current = await actuator.read()
        self.best_position = {axis: float(current[axis]) for axis in self.axes}
        self.steps = []
        emitted = 0

        for step_index, step_axes in enumerate(self.sequence):
            sub = ScanPlan(
                axes=[self._sub_axis(axis) for axis in step_axes],
                detector=self.detector,
                name=f"{self.name}[{step_index}]",
                settle_tolerance=self.settle_tolerance,
                max_settle_polls=self.max_settle_polls,
            )
            sub_descriptor = await sub.describe(session)
            positions = [axis.values.tolist() for axis in sub_descriptor.scan_axes]
            shape = [len(axis) for axis in sub_descriptor.scan_axes]
            total = sub_descriptor.points
            values: list[float | None] = [None] * total

            index = 0
            async for patch in sub.points(session, sub_descriptor):
                values[index] = reduce(patch.values)
                index += 1
                yield DatasetPatch(
                    array=descriptor.value_name,
                    index=emitted,
                    values=np.asarray([values[index - 1]], dtype=float),
                    run_uid=descriptor.run_uid,
                    seq=emitted + 1,
                )
                emitted += 1
                await self._report({
                    "step_index": step_index, "step_axes": step_axes,
                    "sequence": self.sequence, "done": False,
                    "positions": positions, "shape": shape, "values": values,
                    "completed": index, "total": total,
                })

            fit = self._fit(step_axes, positions, values, fit_peak, fit_peak_2d)
            record = {
                "step_index": step_index, "step_axes": step_axes,
                "positions": positions, "values": values, "shape": shape, "fit": fit,
            }
            self.steps.append(record)
            await self._report({
                "step_index": step_index, "step_axes": step_axes,
                "sequence": self.sequence, "done": True, **record,
            })

            if fit is None:
                break  # qudi's own "stop the whole optimize on a failed fit"
            await self._command(
                actuator, {axis: self.best_position[axis] for axis in step_axes}
            )

    # --- Internals --------------------------------------------------------

    def _sub_axis(self, axis: str) -> ScanAxis:
        """This step's search window around the best position so far."""
        low, high, _ = self.axis_ranges[axis]
        span = (self.search_range or {}).get(
            axis, abs(high - low) * self.default_range_fraction
        )
        centre = self.best_position[axis]
        return ScanAxis(
            name=axis, device=self.actuator,
            start=centre - span / 2, stop=centre + span / 2,
            points=max(2, (self.points_per_axis or {}).get(axis, 5)),
        )

    def _fit(self, step_axes, positions, values, fit_peak, fit_peak_2d) -> dict | None:
        """Fit this step's peak, and refuse a centre it did not measure.

        A least-squares peak fit is unconstrained: given a monotonic slope
        rather than a peak — which is exactly what a step that started far
        off-target measures — it happily reports a centre far outside the
        window that was scanned. Observed on the simulated sample: a sweep
        of x over [-4, 4] returning a centre of 21.65, which the optimizer
        then drove to, ending with less signal than it started with and
        the stage parked well outside its own declared range.

        A centre outside the scanned span is not a measurement, so it is
        treated as a failed fit — which stops the sequence, the same as
        qudi's "abort the whole optimize on a failed fit".
        """
        measured = [0.0 if v is None else v for v in values]
        centres: dict[str, float] = {}
        if len(step_axes) == 1:
            fit = fit_peak(positions[0], measured)
            if fit is not None:
                centres[step_axes[0]] = fit["center"]
        else:
            rows, columns = positions
            grid = np.asarray(measured, dtype=float).reshape(len(rows), len(columns))
            fit = fit_peak_2d(rows, columns, grid)
            if fit is not None:
                centres[step_axes[0]] = fit["center_x"]
                centres[step_axes[1]] = fit["center_y"]

        if fit is None:
            return None
        for index, axis in enumerate(step_axes):
            swept = positions[index]
            if not min(swept) <= centres[axis] <= max(swept):
                return None
        self.best_position.update(centres)
        return fit

    async def _report(self, payload: dict[str, Any]) -> None:
        if self.on_step is not None:
            await self.on_step(payload)

    async def _command(self, device: Any, targets: dict[str, float]) -> None:
        await move_and_settle(
            device, targets, self.settle_tolerance, self.max_settle_polls
        )

    @property
    def result(self) -> dict[str, Any]:
        """What the optimize concluded."""
        return {
            "sequence": self.sequence,
            "steps": self.steps,
            "best_position": self.best_position,
        }


@dataclass
class HardwareTimedScanPlan:
    """A whole frame clocked by one device, rather than a software loop.

    A scanner that drives its own position waveform and detector readback
    off one hardware clock (`instruments/hardware_scan_mixin.py`) returns
    samples in bursts, not per point. It is polled, and each poll yields a
    patch covering only the samples that arrived since the last one — so
    the wire carries the new samples rather than the whole accumulated
    frame, which is what the capability class this replaces re-sent on
    every poll.

    Axes are declared first-slowest, like every other plan here.
    `build_scan_waveform` uses the opposite convention (fast axis first),
    so the reversal lives here — one place, rather than in each template
    that drives a scanner.
    """

    axes: list[ScanAxis]
    scanner: str = "scanner"
    frequency: float = 5000.0
    poll_interval: float = 0.1
    name: str = "hardware_timed_scan"
    params: dict[str, Any] = field(default_factory=dict)

    async def describe(self, session: Session) -> RunDescriptor:
        if not 1 <= len(self.axes) <= 2:
            raise ValueError(
                f"A hardware-timed scan drives 1 or 2 axes (only the fast axis is "
                f"genuinely hardware-clocked on this class of device), but "
                f"{len(self.axes)} were given: {[a.name for a in self.axes]}. "
                f"Use a per-point ScanPlan for a 3+ axis scan."
            )
        scanner = session.get(self.scanner)
        axes = tuple(
            Axis(
                name=axis.name, values=axis.values,
                unit=axis.unit or _unit_of(session, self.scanner, axis.name),
                kind="actuator", device=self.scanner, param=axis.name,
            )
            for axis in self.axes
        )
        return RunDescriptor(
            run_uid=str(uuid.uuid4()),
            plan_name=self.name,
            axes=axes,
            scan_axis_count=len(axes),
            value_name="data",
            value_unit=_unit_of(session, self.scanner, "data"),
            devices={self.scanner: scanner.schema.model_dump(mode="json")},
            params=dict(self.params),
        )

    async def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        import asyncio

        scanner = session.get(self.scanner)
        names = [axis.name for axis in self.axes]
        ranges = {axis.name: (axis.start, axis.stop) for axis in self.axes}
        resolution = {axis.name: int(axis.points) for axis in self.axes}

        await scanner.configure_scan(list(reversed(names)), ranges, resolution, self.frequency)
        await scanner.start_scan()
        delivered = 0
        try:
            while True:
                chunk = await scanner.get_scan_data()
                arrived = int(chunk["completed"])
                if arrived > delivered:
                    yield DatasetPatch(
                        array=descriptor.value_name,
                        index=delivered,
                        values=np.asarray(chunk["data"][delivered:arrived], dtype=float),
                        run_uid=descriptor.run_uid,
                        seq=arrived,
                    )
                    delivered = arrived
                if chunk["done"]:
                    break
                await asyncio.sleep(self.poll_interval)
        finally:
            await scanner.stop_scan()


@dataclass
class TimeSeriesPlan:
    """Read one detector repeatedly, on a fixed interval.

    The same object as a scan with the loop axis being time rather than a
    position — which is exactly how it is expressed: a `time` axis, not
    movable, so no view offers a crosshair on it.
    """

    detector: str = "detector"
    samples: int = 100
    interval: float = 0.1
    name: str = "time_series"
    params: dict[str, Any] = field(default_factory=dict)

    async def describe(self, session: Session) -> RunDescriptor:
        detector = session.get(self.detector)
        sample = await detector.read()
        primary = sample.primary()
        time_axis = Axis(
            name="time",
            values=np.arange(int(self.samples), dtype=float) * self.interval,
            unit="s",
            kind="time",
        )
        return RunDescriptor(
            run_uid=str(uuid.uuid4()),
            plan_name=self.name,
            axes=(time_axis, *(sample.axes() if primary.ndim else ())),
            scan_axis_count=1,
            value_name=primary.name or "data",
            value_unit=primary.unit,
            devices={self.detector: detector.schema.model_dump(mode="json")},
            params=dict(self.params),
        )

    async def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        import asyncio

        detector = session.get(self.detector)
        per_point = descriptor.per_point
        await detector.stage()
        try:
            for index in range(descriptor.points):
                if index:
                    await asyncio.sleep(self.interval)
                reading = await detector.read()
                yield DatasetPatch(
                    array=descriptor.value_name,
                    index=index * per_point,
                    values=np.asarray(reading[descriptor.value_name], dtype=float).ravel(),
                    run_uid=descriptor.run_uid,
                    seq=index + 1,
                )
        finally:
            await detector.unstage()


@dataclass
class PulsedMeasurementPlan:
    """Play a pulse sequence over and over, and watch a curve emerge.

    A pulsed measurement is not a scan and pretending otherwise is where
    every framework that has tried this goes wrong. Nothing moves between
    points: the pulser plays the *whole* sweep in a few hundred
    microseconds, the counter accumulates one readout per point per pass,
    and every point of the curve improves together. There is no
    "measure point 7" to pause in the middle of.

    So the axis this plan iterates is **accumulation**, not position. Row
    `k` of the result is the analysed curve after `checkpoint_sweeps[k]`
    complete passes over the sequence, which makes the result a genuine
    2-D `(sweeps, tau)` array rather than a 1-D curve overwritten twenty
    times. That costs one float per point per checkpoint and buys three
    things: a run that streams and pauses and aborts through the ordinary
    `Run` machinery with no special case, a live plot that is just the
    last row, and a saved file that shows whether the measurement had
    converged or was still drifting when it stopped.

    ## Why describe() knows everything already

    The sequence carries its own sweep (`core/pulse/sequence.py`), so the
    tau axis, its unit and its length are known before the pulser is
    touched; the analysis method declares its own label and unit
    (`core/pulse/analyse.py`), so the value axis is known too. That is
    the whole reason this is a plan and not a fifth hand-rolled loop:
    pause, abort, `DatasetPatch` streaming, HDF5 with real coordinates
    and a `Catalogue` row are all inherited rather than rewritten. Qudi's
    `pulsed_measurement_logic` is its own engine with its own state and
    its own signals precisely because its sequence cannot answer these
    questions.

    ## What it does not compile

    Nothing. `upload_sequence` takes the abstract sequence and the
    pulser decides what to do with it — instructions for a sequencer,
    samples for an AWG. This plan never sees a waveform.
    """

    sequence: Any
    """The `PulseSequence` to play. Typed loosely so `core/run/` does not
    import `core/pulse/` at module scope for one annotation."""
    pulser: str = "pulser"
    counter: str = "counter"
    microwave: str | None = None
    microwave_on: str = "cw_on"
    microwave_off: str = "off"
    """Actions, named rather than guessed. `Source` deliberately has no
    generic `enable()`/`disable()` — real sources vary between a settable
    on/off key, a zero-argument `cw_on()` action and no on/off concept at
    all — so which action to call is the rig's fact and belongs in its
    workflow's parameters, not in a list of names to try."""
    laser: str | None = None
    """Recorded for provenance, not driven. On a pulsed rig the laser
    runs continuously and the *pulser* gates it through an AOM, which is
    the whole reason the sequence has a laser channel."""
    channels: dict[str, str] = field(default_factory=dict)
    """Symbolic channel -> this rig's physical channel. Empty means the
    sequence's own names are the physical ones, which is what the mock
    rig and most simple digital sequencers actually are."""

    sweeps: int = 1000
    """Complete passes over the sequence to accumulate. This is the
    measurement's signal-to-noise knob: counts, and so the error bars,
    improve as its square root."""
    checkpoints: int = 20
    """How many times the curve is recorded on the way. Rows of the
    result, and the run's progress steps."""

    bin_width: float = 1e-9
    record_length: float = 0.0
    """Length of each recorded readout window. 0 derives it from the
    sequence — half again the readout window itself, so the record holds
    the laser pulse plus dark bins either side for extraction to find its
    edges in."""

    extract: str = "conv_deriv"
    extract_params: dict[str, Any] = field(default_factory=dict)
    analyse: str = "auto"
    """`"auto"` picks from the sequence: signal/reference when it
    alternates, per-readout normalisation when it does not. A fixed
    default would be wrong for half the experiments."""
    analyse_params: dict[str, Any] = field(default_factory=dict)

    poll_interval: float = 0.1
    stall_timeout: float = 30.0
    """Give up if the counter's sweep count has not moved for this long.
    A pulser that failed to start otherwise leaves the run polling
    forever, which looks exactly like a slow measurement."""
    name: str = "pulsed"
    params: dict[str, Any] = field(default_factory=dict)

    #: Filled in as the run proceeds — the pulser's own account of what it
    #: loaded, the counter's actual configuration, and the most recent
    #: extraction and analysis. The same convention `OptimizePlan` uses to
    #: report what it concluded.
    report: Any = None
    config: Any = None
    extraction: Any = None
    analysis: Any = None

    # --- What the sequence and the methods already know -------------------

    @property
    def method(self) -> str:
        """The analysis actually used, with `"auto"` resolved."""
        from labpilot.core.pulse.analyse import default_analysis

        if self.analyse and self.analyse != "auto":
            return self.analyse
        return default_analysis(bool(self.sequence.alternating))

    @property
    def checkpoint_sweeps(self) -> tuple[int, ...]:
        """Accumulated sweep count at each recorded row.

        Evenly spaced, ending exactly on `sweeps`. Deduplicated, so
        asking for more checkpoints than sweeps records each sweep once
        rather than recording the same trace twice under two labels.
        """
        total = max(int(self.sweeps), 1)
        count = max(min(int(self.checkpoints), total), 1)
        return tuple(sorted({
            max(round((step + 1) * total / count), 1) for step in range(count)
        }))

    @property
    def record_length_s(self) -> float:
        window = float(self.sequence.readout_window() or 0.0)
        return float(self.record_length) or (window * 1.5 or 3e-6)

    async def describe(self, session: Session) -> RunDescriptor:
        from labpilot.core.pulse.analyse import analysis_units

        sequence = self.sequence
        sequence.validate()
        label, unit = analysis_units(self.method)

        rows = self.checkpoint_sweeps
        sweep = sequence.sweep
        if sweep is not None:
            swept = Axis(
                name=sweep.name, values=sweep.array, unit=sweep.unit,
                kind="time" if sweep.unit == "s" else "index",
            )
        else:
            # A hand-written sequence need not declare a sweep. Then the
            # x-axis is the readout index, which is honest rather than
            # invented, and every experiment shipped in the library does
            # declare one.
            swept = Axis(
                name="readout", values=np.arange(sequence.points, dtype=float),
                kind="index",
            )

        descriptor = RunDescriptor(
            run_uid=str(uuid.uuid4()),
            plan_name=self.name,
            axes=(
                Axis("sweeps", np.asarray(rows, dtype=float), kind="index"),
                swept,
            ),
            scan_axis_count=1,
            value_name=label,
            value_unit=unit,
            devices={
                role: session.get(role).schema.model_dump(mode="json")
                for role in (self.pulser, self.counter, self.microwave, self.laser)
                if role and session.has(role)
            },
            params={
                "sequence": sequence.name,
                "sequence_points": sequence.points,
                "readouts": sequence.readouts(),
                "sequence_duration": sequence.duration,
                "alternating": sequence.alternating,
                "sweeps": int(self.sweeps),
                "extract": self.extract,
                "analyse": self.method,
                **dict(self.params),
            },
        )
        if descriptor.size > MAX_ELEMENTS:
            raise ValueError(
                f"This measurement's result would need {descriptor.size:,} "
                f"elements ({len(rows):,} checkpoints x {sequence.points:,} "
                f"points) — over the {MAX_ELEMENTS:,}-element safety limit. "
                f"Reduce `checkpoints`."
            )
        return descriptor

    async def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        from labpilot.core.pulse.sequence import ChannelMap

        pulser = session.get(self.pulser)
        counter = session.get(self.counter)
        sequence = self.sequence

        mapping = self.channels or {name: name for name in sequence.channels}
        self.report = await pulser.upload_sequence(sequence, ChannelMap(mapping))
        self.config = await counter.configure_gates(
            self.bin_width, self.record_length_s, sequence.readouts()
        )

        await self._switch(session, on=True)
        await counter.start_counting()
        await pulser.pulser_on()
        per_point = max(1, descriptor.per_point)
        try:
            for index, target in enumerate(self.checkpoint_sweeps):
                await self._accumulate(counter, target)
                values = await self._measure(counter)
                yield DatasetPatch(
                    array=descriptor.value_name,
                    index=index * per_point,
                    values=_fit_to(values, per_point),
                    run_uid=descriptor.run_uid,
                    seq=index + 1,
                )
        finally:
            # Ordered deliberately: the pulser stops first, so the laser
            # gate closes before anything else is touched. An aborted run
            # must not leave a sample under continuous illumination.
            await pulser.pulser_off()
            await counter.stop_counting()
            await self._switch(session, on=False)

    # --- Internals --------------------------------------------------------

    async def _accumulate(self, counter: Any, target: int) -> None:
        """Wait until the counter has accumulated `target` full sweeps.

        Polls rather than sleeping for a computed duration: how long a
        sweep takes is the pulser's business, and a sequence whose
        duration was quantised on upload no longer takes exactly what it
        says on paper.
        """
        import asyncio
        import time

        last, changed = -1, time.monotonic()
        while True:
            status = await counter.counter_status()
            sweeps = int(status.get("sweeps", 0))
            if sweeps >= target:
                return
            if sweeps != last:
                last, changed = sweeps, time.monotonic()
            elif time.monotonic() - changed > self.stall_timeout:
                raise RuntimeError(
                    f"{self.counter} has counted {sweeps} sweeps and has not "
                    f"advanced for {self.stall_timeout:.0f} s, waiting for "
                    f"{target}. The pulser may not be playing, or its gate "
                    f"channel may not be wired to the counter's trigger."
                )
            await asyncio.sleep(self.poll_interval)

    async def _measure(self, counter: Any) -> np.ndarray:
        """One accumulated trace, extracted and analysed into a curve."""
        from labpilot.core.pulse.analyse import analyse as analyse_pulses
        from labpilot.core.pulse.extract import extract as extract_pulses

        trace = await counter.get_trace()
        bin_width = self.config.bin_width_s
        self.extraction = extract_pulses(
            trace, bin_width, self.extract, **self.extract_params
        )
        self.analysis = analyse_pulses(
            self.extraction, bin_width, self.method,
            alternating=bool(self.sequence.alternating), **self.analyse_params,
        )
        return np.asarray(self.analysis.values, dtype=float)

    async def _switch(self, session: Session, *, on: bool) -> None:
        """Call the microwave source's on or off action around the run.

        A pulsed experiment measures nothing at all if the source is not
        emitting, so failing to turn it on is an error. Failing to turn
        it off is reported and swallowed, for the same reason `Run` does
        it when stopping actuators: a run that has already finished must
        still be reported as finished.

        Nothing happens for a source that declares **no** actions: it has
        no on/off concept, which is the ordinary digital-rig case where
        the pulser gates a source left running. A source that declares
        actions but not *this* one is a different thing — a name that is
        wrong — and saying so beats a run that measures nothing and
        reports success.
        """
        action = self.microwave_on if on else self.microwave_off
        if not self.microwave or not action or not session.has(self.microwave):
            return

        device = session.get(self.microwave)
        declared = device.schema.action_names
        if not declared:
            return
        if action not in declared:
            if not on:
                return
            raise ValueError(
                f"{self.microwave} declares no action {action!r} — it offers "
                f"{', '.join(declared) or 'none'}. Set `microwave_on` and "
                f"`microwave_off` to this source's own action names, or to "
                f"'' if it has no on/off concept."
            )
        try:
            await getattr(device, action)()
        except Exception as e:
            if on:
                raise
            print(f"⚠️  Could not switch {self.microwave} off after the run: {e}")

    @property
    def result(self) -> dict[str, Any]:
        """What the measurement produced, beyond the numbers themselves.

        The raw record profile and the windows found in it, so a result
        view can draw where the extraction decided the laser pulse was —
        the one thing a pulsed measurement gets wrong silently.
        """
        return {
            "sequence": self.sequence.name,
            "pulser": self.report.to_dict() if self.report is not None else None,
            "counter": self.config.to_dict() if self.config is not None else None,
            "extraction": (
                self.extraction.to_dict() if self.extraction is not None else None
            ),
            "analysis": self.analysis.to_dict() if self.analysis is not None else None,
        }


def _fit_to(values: np.ndarray, width: int) -> np.ndarray:
    """`values` as exactly `width` numbers — padded with NaN, never wrapped.

    A trace polled mid-sweep can hold fewer readouts than the sequence
    declares. Yielding a short patch would silently shift every later row
    of the result by the shortfall, so the gap is made visible instead.
    """
    if values.size == width:
        return values
    padded = np.full(width, np.nan, dtype=float)
    kept = min(values.size, width)
    padded[:kept] = values[:kept]
    return padded


@dataclass
class ScriptPlan:
    """A workflow script — `async def run(session) -> dict` in a `.py`.

    The escape hatch, and deliberately kept: "a workflow is a Python file
    with a `run` function" is the best thing here for scripting. It is
    human-readable, editable in the UI, runnable from the console and
    diffable, and a plan object should not take that away from anyone who
    wants to write the loop themselves.

    So this is a Plan by *composition* rather than by decomposition: it
    yields no points, because the script owns its own loop. What that
    costs is exactly what the API already says — pausing a workflow that
    is not running a plan answers 409, because a script has no point
    boundary to hold at. What it gains is one entry point: `execute(...)`
    takes any plan, and a script is one of them.

    A script that wants pause, abort and streaming for free runs a plan of
    its own inside `run()`, which is what the shipped templates do.
    """

    path: str
    params: dict[str, Any] = field(default_factory=dict)
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = Path(self.path).stem

    async def describe(self, session: Session) -> RunDescriptor:
        """What can be known without running it: its declared parameters
        and the roles it needs. Not its shape — only the script knows
        that, and only once it has run."""
        from labpilot.core.workflow.instrument_roles import (
            read_required_instruments_from_file,
            read_workflow_params,
        )

        text = Path(self.path).read_text()
        roles = read_required_instruments_from_file(self.path)
        return RunDescriptor(
            run_uid=str(uuid.uuid4()),
            plan_name=self.name,
            devices={
                role: session.get(role).schema.model_dump(mode="json")
                for role in roles if session.has(role)
            },
            params={**read_workflow_params(text), **self.params},
        )

    async def points(
        self, session: Session, descriptor: RunDescriptor
    ) -> AsyncIterator[DatasetPatch]:
        """No points: `run()` owns the loop. See the class docstring."""
        return
        yield  # pragma: no cover - makes this an async generator

    async def run(self, session: Session, descriptor: RunDescriptor) -> dict[str, Any]:
        """Execute the file, with this workflow's parameters applied.

        Either shape — plain top-level Python or `async def run(session)`.
        See `core/run/script.py`, which is also what the run manager
        calls, so the two entry points cannot diverge.
        """
        from labpilot.core.run.script import run_script

        return await run_script(session, self.path, self.params)


def _by_device(
    targets: dict[str, float], axes: list[ScanAxis]
) -> dict[str, dict[str, float]]:
    """Group `{param: value}` by the device that owns each parameter.

    One `write()` per device per point rather than one per axis: an XY
    stage moves both axes in a single command, which is what makes a
    multi-device grid no slower than the single-device loop it replaces.
    """
    owner = {axis.name: axis.device for axis in axes}
    grouped: dict[str, dict[str, float]] = {}
    for name, value in targets.items():
        device = owner.get(name)
        if device is None:
            continue
        grouped.setdefault(device, {})[name] = float(value)
    return grouped


def _unit_of(session: Session, device: str, parameter: str) -> str:
    try:
        return session.get(device).schema.units.get(parameter, "")
    except KeyError:
        return ""


# Declared at the bottom, where every plan type above exists: how each of
# them crosses the process boundary when a console starts one. See
# `core/run/requests.py` for why that is a registry rather than a route
# per plan.
_register_transports()
