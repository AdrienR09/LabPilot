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
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np

from labpilot.core.data.dataset import Axis, DatasetPatch
from labpilot.core.device.motion import (
    DEFAULT_MAX_POLLS,
    DEFAULT_TOLERANCE,
    move_and_settle,
)
from labpilot.core.run.descriptor import RunDescriptor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from labpilot.core.session import Session

__all__ = ["Plan", "ScanAxis", "ScanPlan", "TimeSeriesPlan"]

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
