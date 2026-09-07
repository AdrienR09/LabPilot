"""`RunDescriptor` — everything knowable about a run before its first point.

This is the piece that earns Phase 3 its keep. Twelve of fifteen templates
hand-allocate their result grid and hand-maintain `completed`/`total`
counters, and they do it *because nothing else knows the shape up front*.
`omniscan.py`'s `_run_per_point` is the clearest case: about a third of the
template is one `if "value_key" not in state:` block that runs on the first
progress callback and works out, from the first reading, how big the result
will be, what its axes are called, where they sit and what units they carry
— then allocates `[None] * total_elements` and starts counting.

None of that is scan-specific. It is the same arithmetic for a confocal
image, a spectrum series and a time series, and every template that
reimplements it is a place the conventions can drift: the flat row-major
layout, the "first axis varies slowest" order, `None` for a point not yet
taken, `actuator_axis_count` counting the *leading* movable axes.

A descriptor states those facts once, structurally:

- `axes` are `Axis` objects, so which of them can be driven is
  `axis.movable` — a property of the axis, not the integer
  `actuator_axis_count` maintained by hand in each template and matched
  positionally against `axis_names` in each view.
- `shape`, `points` and `per_point` are derived, so a counter cannot
  disagree with an allocation.
- `allocate()` hands back the flat buffer with the right length and the
  right "not measured yet" fill.

## Why describing can require touching hardware

A detector's schema declares dtype and rank but not length: a spectrometer
says `shape=(None,)`, and only a real reading says 2048. So a plan's
`describe()` is `async` and may take one reading to find out. That is the
honest shape of the problem — the alternative is what the templates do
today, which is to discover it on the first point and allocate mid-flight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["RunDescriptor"]


@dataclass(frozen=True, slots=True)
class RunDescriptor:
    """The shape of a run, its coordinates, and what produced it."""

    run_uid: str
    plan_name: str
    axes: tuple[Axis, ...] = ()
    """Every dimension of the result, outermost first.

    A scan's own axes come first (the ones the plan iterates over), then
    any the detector contributes at each point — a spectrometer's
    wavelength axis, a camera's row/col. That ordering is what makes
    `points`/`per_point` a split of `shape` rather than a separate fact.
    """
    scan_axis_count: int = 0
    """How many leading axes the plan iterates over."""
    value_name: str = "data"
    value_unit: str = ""
    driven: tuple[str, ...] = ()
    """Devices this run commands, when its axes cannot say so — see
    `actuators`."""
    devices: Mapping[str, Any] = field(default_factory=dict)
    """Serialised `DeviceSchema` per role, for provenance."""
    params: Mapping[str, Any] = field(default_factory=dict)
    """The parameters this run was launched with."""

    # --- Derived shape ----------------------------------------------------

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(len(axis) for axis in self.axes)

    @property
    def points(self) -> int:
        """Acquisition steps: one move-and-read per point."""
        return int(np.prod(self.shape[: self.scan_axis_count], dtype=int)) if self.axes else 0

    @property
    def per_point(self) -> int:
        """Values each point contributes — 1 for a scalar detector."""
        return int(np.prod(self.shape[self.scan_axis_count :], dtype=int)) if self.axes else 1

    @property
    def size(self) -> int:
        return self.points * self.per_point

    @property
    def scan_axes(self) -> tuple[Axis, ...]:
        return self.axes[: self.scan_axis_count]

    @property
    def actuator_axis_count(self) -> int:
        """Leading axes something can actually be driven along.

        Derived from the axes themselves, where every template and every
        result view currently carries it as a separate integer that has to
        stay in step with `axis_names` by position.
        """
        count = 0
        for axis in self.axes:
            if not axis.movable:
                break
            count += 1
        return count

    @property
    def actuators(self) -> tuple[str, ...]:
        """Devices this run drives — what `abort()` has to stop.

        Usually the movable axes say so themselves. A run whose axis is a
        point index still drives hardware, though — an optimize scans
        around wherever the previous fit landed, so its coordinates are
        not knowable up front — and it names those devices in `driven`.
        """
        if self.driven:
            return self.driven
        seen: list[str] = []
        for axis in self.axes:
            if axis.movable and axis.device and axis.device not in seen:
                seen.append(axis.device)
        return tuple(seen)

    # --- What a run is written into ---------------------------------------

    def allocate(self) -> list[Any]:
        """The flat, row-major result buffer, `None` where nothing is measured.

        `None` rather than NaN because this list is what the REST layer
        serialises and what the result views already read: `None` is
        JSON-native and renders as a gap, while NaN is not valid JSON.
        `Dataset.from_result` converts them to NaN on the way to storage,
        where NaN is what "not measured" means to every reader of an HDF5
        file.
        """
        return [None] * self.size

    def dataset(self, values: Any) -> Dataset:
        """`values` as a `Dataset` with these axes and units."""
        flat = np.asarray(
            [np.nan if v is None else v for v in values]
            if isinstance(values, list) else values,
            dtype=float,
        )
        array = DataArray(
            name=self.value_name,
            values=flat.reshape(self.shape) if flat.size == self.size else flat,
            unit=self.value_unit,
            axes=self.axes,
        )
        return Dataset(
            (array,),
            RunMeta(
                run_uid=self.run_uid, plan_name=self.plan_name,
                devices=dict(self.devices), params=dict(self.params),
            ),
        )

    def result_fields(self) -> dict[str, Any]:
        """This descriptor in the flat wire convention the views read.

        `axis_names` / `axis_positions` / `shape` / `actuator_axis_count` /
        `value_unit` / `axis_units` — the N-D scan convention every
        template emits by hand today, and which `Dataset.from_result`
        already knows how to lift back into axes. Emitting it from the
        descriptor is what lets a plan-based template return exactly what
        its hand-written predecessor did, so the Qt views, the React
        client, the HDF5 writer and `pick_view` all keep working with no
        changes at all.
        """
        return {
            "axis_names": [axis.name for axis in self.axes],
            "axis_positions": [axis.values.tolist() for axis in self.axes],
            "shape": list(self.shape),
            "actuator_axis_count": self.actuator_axis_count,
            "value_unit": self.value_unit,
            "axis_units": {axis.name: axis.unit for axis in self.axes},
        }
