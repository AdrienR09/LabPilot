"""`Dataset` — a measurement that describes itself.

`read()` used to return `dict[str, Any]`. A spectrometer handed back
`{"wavelengths": [...], "intensities": [...]}` with nothing structurally
linking the axis to the values it indexes, no units, no dtypes, no device
identity. Every layer downstream paid for that:

- `RESULT_UI`, fifteen per-template maps from ad-hoc result keys to a
  renderer, unvalidated, where a typo renders a blank panel;
- functions that *guessed*, from a substring hint list plus a live read,
  which key was the axis of which other key;
- an HDF5 writer and a provenance catalogue that were written and then
  wired to nothing, because there was no self-describing thing to write;
- 15-70 MB WebSocket frames, because the only way to publish "one more
  point" was to resend the whole accumulated array.

A `Dataset` carries the arrays, their axes, their units and the run they
belong to, so those questions are answered by asking rather than
inferring.

## It is still a dict

`Dataset` subclasses `dict` and maps each name to exactly the value
`read()` always returned. Every existing caller — `data["intensities"]`,
`.items()`, `json.dumps(...)`, `isinstance(x, dict)` — is unaffected, and
the 301 adapters keep implementing `_read_sync()` as a plain dict. The
structure is *added alongside*, on `.arrays` and `.meta`, the same way
`DeviceSchema` kept its four flat dicts as computed views over
`Parameter`. That is what makes this changeable at all: the keystone can
land without a flag day.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from labpilot.core.device.parameter import Parameter, ParamRole

if TYPE_CHECKING:
    from labpilot.core.device.schema import DeviceSchema

__all__ = [
    "Axis",
    "DataArray",
    "Dataset",
    "DatasetPatch",
    "RunMeta",
]

AxisKind = Literal["actuator", "detector", "time", "repeat", "index"]


@dataclass(frozen=True, slots=True, eq=False)
class Axis:
    """One dimension's coordinates.

    `kind` and `device` are what a view needs in order to decide whether a
    given pair of axes can carry an interactive crosshair: it can iff both
    are `kind="actuator"` and name a device to move. That is currently
    encoded as the *string* `"actuator_axis_count_key"` in a template's
    `RESULT_UI`, i.e. a positional convention a typo breaks silently.

    `eq=False` because `values` is a numpy array and the generated
    `__eq__` would return an array rather than a bool.
    """

    name: str
    values: np.ndarray
    unit: str = ""
    kind: AxisKind = "index"
    device: str | None = None
    """Registered instrument this axis is a coordinate of — set for an
    `actuator` axis, so a view knows what to command when the user drags."""
    param: str | None = None
    """Parameter name on `device`, when the axis is a device parameter."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", np.asarray(self.values))

    def __len__(self) -> int:
        return int(self.values.shape[0]) if self.values.ndim else 0

    @property
    def movable(self) -> bool:
        """Whether something can actually be driven along this axis."""
        return self.kind == "actuator" and self.device is not None

    @property
    def label(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name

    @classmethod
    def index(cls, name: str, length: int) -> Axis:
        """A bare sample-index axis, for an array with no real coordinates."""
        return cls(name=name, values=np.arange(length), kind="index")


@dataclass(frozen=True, slots=True, eq=False)
class DataArray:
    """One named array, with the axes that index it.

    `len(axes) == values.ndim` whenever the axes are known; a shorter tuple
    means the leading dimensions are described and the rest are not, which
    is what a scan in progress looks like.
    """

    name: str
    values: np.ndarray
    unit: str = ""
    axes: tuple[Axis, ...] = ()
    param: Parameter | None = None
    """The declaring `Parameter`, when this array came from a device read —
    carries dtype, limits, tags and description."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", np.asarray(self.values))
        object.__setattr__(self, "axes", tuple(self.axes))

    @property
    def ndim(self) -> int:
        return int(self.values.ndim)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(self.values.shape)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name

    def axis(self, index: int) -> Axis:
        """The axis for dimension `index`, falling back to a sample index
        when the array carries no coordinates for it."""
        if index < len(self.axes):
            return self.axes[index]
        length = self.shape[index] if index < self.ndim else 0
        return Axis.index(f"dim{index}", length)


@dataclass(frozen=True, slots=True)
class RunMeta:
    """Everything about a reading or a run other than the numbers."""

    run_uid: str = ""
    plan_name: str = ""
    timestamp: float = field(default_factory=time.time)
    device: str | None = None
    """Instrument this reading came from, for a single-device read."""
    devices: Mapping[str, Any] = field(default_factory=dict)
    """Serialised `DeviceSchema` per participating device, for a run."""
    params: Mapping[str, Any] = field(default_factory=dict)
    """The plan/template parameters this run was launched with."""

    @classmethod
    def new_run(cls, plan_name: str, **kwargs: Any) -> RunMeta:
        return cls(run_uid=str(uuid.uuid4()), plan_name=plan_name, **kwargs)


class Dataset(dict):
    """A self-describing measurement that is also the dict it replaces.

    Keys and values are exactly what `read()` returned before — see the
    module docstring. `arrays` and `meta` carry the structure.

    Example:
        >>> data = await spectrometer.read()
        >>> data["intensities"]              # unchanged, a plain list/array
        >>> data.primary().unit              # 'counts'
        >>> data.primary().axis(0).name      # 'wavelengths'
    """

    __slots__ = ("arrays", "meta")

    def __init__(
        self,
        arrays: Mapping[str, DataArray] | tuple[DataArray, ...] = (),
        meta: RunMeta | None = None,
        *,
        raw: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Args:
            arrays: The structured arrays, by name or in order.
            meta: Run/device metadata.
            raw: The literal values to expose through the dict interface.
                Defaults to each array's `values`. Passed explicitly when
                lifting an adapter's reading, so the dict keeps handing
                back exactly the objects the driver produced (a list stays
                a list) rather than the numpy view built alongside it.
        """
        if isinstance(arrays, Mapping):
            ordered = dict(arrays)
        else:
            ordered = {array.name: array for array in arrays}
        object.__setattr__(self, "arrays", ordered)
        object.__setattr__(self, "meta", meta or RunMeta())
        super().__init__(
            raw if raw is not None
            else {name: array.values for name, array in ordered.items()}
        )

    # `dict` has no __dict__ and Dataset uses __slots__, so the two
    # attributes need setting through object.__setattr__ above; expose a
    # normal repr rather than dict's, which would hide them.
    def __repr__(self) -> str:
        return (
            f"Dataset({list(self.arrays)!r}"
            f"{f', run={self.meta.run_uid[:8]}' if self.meta.run_uid else ''})"
        )

    # --- Structure --------------------------------------------------------

    def primary(self) -> DataArray:
        """The array this dataset is *about*.

        The highest-rank array that is not itself an axis, earliest
        declaration winning a tie. This one method replaces
        `spectrum_key()` (which excluded any key containing "wavelength"
        and took what was left) and the value-key half of
        `detector_axes()`.

        Raises:
            ValueError: if the dataset carries no arrays at all.
        """
        candidates = [a for a in self.arrays.values() if not self._is_axis(a)]
        if not candidates:
            candidates = list(self.arrays.values())
        if not candidates:
            raise ValueError("dataset carries no arrays")
        return max(candidates, key=lambda a: a.ndim)

    def axes(self) -> tuple[Axis, ...]:
        """The primary array's axes — replaces `detector_axes()`."""
        primary = self.primary()
        return tuple(primary.axis(i) for i in range(primary.ndim))

    def _is_axis(self, array: DataArray) -> bool:
        if array.param is not None:
            return array.param.role is ParamRole.AXIS
        # No declaring parameter (a dataset assembled by a scan rather than
        # lifted from a read): an array named by one of the primary's axes
        # is a coordinate, not a measurement.
        return any(
            array.name == axis.name
            for other in self.arrays.values() if other is not array
            for axis in other.axes
        )

    def as_dict(self) -> dict[str, Any]:
        """A plain `dict` copy — for a caller that must not receive a
        subclass (a strict `type(x) is dict` check, a pickling boundary)."""
        return dict(self)

    # --- Construction from a device reading -------------------------------

    @classmethod
    def from_reading(
        cls,
        schema: DeviceSchema,
        reading: Mapping[str, Any],
        meta: RunMeta | None = None,
    ) -> Dataset:
        """Lift one adapter `read()` result into a `Dataset`.

        This is the single point where a plain reading becomes
        self-describing, which is why `AdapterBase.read()` is the only
        caller that matters: 301 adapters keep returning dicts from
        `_read_sync()` and every one of them gains axes and units.

        Which array is an axis and which is the measurement comes from the
        device's own `Parameter` declarations (`role=AXIS`, `axes=(...)`).
        An adapter that declares neither still gets a `Dataset` — its
        arrays simply carry index axes, which is honest about not knowing
        rather than guessing from key names.
        """
        meta = meta or RunMeta(device=schema.name)

        axes_by_name: dict[str, Axis] = {}
        for parameter in schema.find(role=ParamRole.AXIS):
            if parameter.name in reading:
                axes_by_name[parameter.name] = Axis(
                    name=parameter.name,
                    values=np.asarray(reading[parameter.name]),
                    unit=parameter.unit,
                    kind="detector",
                    device=schema.name,
                    param=parameter.name,
                )

        arrays: dict[str, DataArray] = {}
        for name, value in reading.items():
            parameter = schema.get(name)
            values = np.asarray(value)
            if name in axes_by_name:
                axis = axes_by_name[name]
                arrays[name] = DataArray(
                    name=name, values=axis.values, unit=axis.unit,
                    axes=(axis,), param=parameter,
                )
                continue
            arrays[name] = DataArray(
                name=name, values=values,
                unit=parameter.unit if parameter is not None else "",
                axes=_axes_for(parameter, values, axes_by_name),
                param=parameter,
            )

        return cls(arrays, meta, raw=reading)

    # --- Construction from a workflow result ------------------------------

    @classmethod
    def from_result(
        cls,
        result: Mapping[str, Any],
        meta: RunMeta | None = None,
        result_ui: Mapping[str, Any] | None = None,
    ) -> Dataset:
        """Lift a workflow template's returned dict into a `Dataset`.

        Templates return plain dicts and will keep doing so — a workflow is
        a `.py` file with `async def run(session) -> dict`, and that is the
        best thing in this codebase for scripting. This is the seam that
        lets those dicts be *stored* without every template having to learn
        a new return type.

        Two shapes are recognised, both of which the existing templates
        already produce:

        - the N-D scan convention (`data` flat + `shape` + `axis_names` +
          `axis_positions`, optionally `actuator_axis_count`,
          `value_unit` and `axis_units`), which
          `omniscan` and the scanners emit — reshaped into one array with
          real coordinates, and the leading `actuator_axis_count` axes
          marked movable;
        - anything else: each array-valued key becomes its own array. When
          the template declares a `RESULT_UI`, its `x_key`/`value_key`
          pairing says which of those is a coordinate; without one, arrays
          simply carry index axes.

        Scalars never become arrays — they go to `meta.params`, which is
        where a fit centre or a repeat count belongs.
        """
        meta = meta or RunMeta()
        scalars = {
            key: value for key, value in result.items()
            if not isinstance(value, (list, tuple, np.ndarray))
        }
        if scalars:
            meta = RunMeta(
                run_uid=meta.run_uid, plan_name=meta.plan_name,
                timestamp=meta.timestamp, device=meta.device,
                devices=meta.devices, params={**dict(meta.params), **scalars},
            )

        arrays = _scan_arrays(result) or _loose_arrays(result, result_ui)
        return cls(arrays, meta)

    # --- Storage ----------------------------------------------------------

    def to_hdf5(self, group: Any) -> None:
        """Write this dataset into an open `h5py` group.

        Each array becomes a dataset carrying its unit; each axis becomes
        an HDF5 *dimension scale* attached to the dimension it indexes, so
        the file is self-describing to any reader that understands the
        convention — h5py, xarray, MATLAB — and not only to LabPilot.

        The previous writer stored bare arrays with no coordinates and no
        units at all, which is one reason nothing ever subscribed it.
        """
        coordinates = group.require_group("axes")
        written: dict[str, Any] = {}
        for array in self.arrays.values():
            for axis in array.axes:
                if axis.name in written or not len(axis):
                    continue
                scale = coordinates.create_dataset(axis.name, data=axis.values)
                scale.attrs["units"] = axis.unit
                scale.attrs["kind"] = axis.kind
                if axis.device:
                    scale.attrs["device"] = axis.device
                scale.make_scale(axis.name)
                written[axis.name] = scale

        for array in self.arrays.values():
            if array.name in written:
                continue  # already stored as a coordinate
            stored = group.create_dataset(
                array.name, data=array.values,
                compression="gzip" if array.values.size > 1024 else None,
            )
            stored.attrs["units"] = array.unit
            if array.param is not None:
                stored.attrs["role"] = str(array.param.role)
                if array.param.description:
                    stored.attrs["description"] = array.param.description
            for dimension, axis in enumerate(array.axes[: stored.ndim]):
                scale = written.get(axis.name)
                if scale is not None:
                    stored.dims[dimension].attach_scale(scale)
                    stored.dims[dimension].label = axis.name

        for key, value in (("run_uid", self.meta.run_uid),
                           ("plan_name", self.meta.plan_name),
                           ("timestamp", self.meta.timestamp),
                           ("device", self.meta.device)):
            if value:
                group.attrs[key] = value


def _axes_for(
    parameter: Parameter | None,
    values: np.ndarray,
    axes_by_name: Mapping[str, Axis],
) -> tuple[Axis, ...]:
    """Axes for one measured array: the ones its parameter names, then
    index axes for any remaining dimensions."""
    declared = []
    if parameter is not None:
        declared = [axes_by_name[name] for name in parameter.axes if name in axes_by_name]

    axes = list(declared[: values.ndim])
    for dimension in range(len(axes), values.ndim):
        axes.append(Axis.index(_INDEX_NAMES.get((values.ndim, dimension), f"dim{dimension}"),
                               values.shape[dimension]))
    return tuple(axes)


# Conventional names for index axes, matching what the existing result
# views already expect for a 1-D trace and a 2-D image.
_INDEX_NAMES = {(1, 0): "sample", (2, 0): "row", (2, 1): "col"}

# Keys the N-D scan convention uses. Every scanning template emits these
# (see core/workflow_templates/omniscan.py); `actuator_axis_count` says how
# many of the LEADING axes belong to the actuator and can therefore be
# driven, which is exactly `Axis.movable`.
_SCAN_KEYS = ("data", "shape", "axis_names", "axis_positions")


def _scan_arrays(result: Mapping[str, Any]) -> dict[str, DataArray]:
    """The N-D scan convention, as one array with real coordinates."""
    if not all(key in result for key in _SCAN_KEYS):
        return {}
    shape = tuple(int(n) for n in result["shape"])
    names = list(result["axis_names"])
    positions = list(result["axis_positions"])
    if len(names) != len(shape) or len(positions) != len(shape):
        return {}

    # An unfinished or aborted scan leaves `None` where a point was never
    # taken; NaN is what that means to every reader of the file.
    flat = np.array(
        [np.nan if v is None else v for v in result["data"]], dtype=float
    )
    if flat.size != int(np.prod(shape)):
        return {}

    movable = int(result.get("actuator_axis_count") or 0)
    device = result.get("actuator") or result.get("scanner")
    units = dict(result.get("axis_units") or {})
    axes = tuple(
        Axis(
            name=name,
            values=np.asarray(coordinates, dtype=float),
            unit=units.get(name, ""),
            kind="actuator" if index < movable else "detector",
            device=device if index < movable else None,
            param=name if index < movable else None,
        )
        for index, (name, coordinates) in enumerate(zip(names, positions, strict=False))
    )
    return {
        "data": DataArray(
            name="data", values=flat.reshape(shape),
            unit=str(result.get("value_unit") or ""), axes=axes,
        )
    }


def _loose_arrays(
    result: Mapping[str, Any], result_ui: Mapping[str, Any] | None
) -> dict[str, DataArray]:
    """Every array-valued key as its own array.

    A `RESULT_UI` naming an `x_key` tells us that array is a coordinate of
    the value it is paired with — the one useful thing that map knows that
    a bare dict does not, borrowed here while it still exists.
    """
    ui = dict(result_ui or {})
    axis_names = {ui.get(key) for key in ("x_key", "fit_x_key")} - {None}
    value_names = {ui.get(key) for key in ("y_key", "value_key", "matrix_key")} - {None}

    coordinates: dict[str, Axis] = {}
    for name in axis_names:
        value = result.get(name)
        if isinstance(value, (list, tuple, np.ndarray)) and len(value):
            coordinates[name] = Axis(name=name, values=np.asarray(value, dtype=float))

    arrays: dict[str, DataArray] = {}
    for name, value in result.items():
        if not isinstance(value, (list, tuple, np.ndarray)):
            continue
        values = np.asarray(
            [np.nan if v is None else v for v in value]
            if isinstance(value, (list, tuple)) else value
        )
        if name in coordinates:
            axis = coordinates[name]
            arrays[name] = DataArray(name, axis.values, axes=(axis,))
            continue
        axes: tuple[Axis, ...] = ()
        if name in value_names and values.ndim >= 1:
            paired = next(
                (a for a in coordinates.values() if len(a) == values.shape[-1]), None
            )
            if paired is not None:
                axes = (paired,) if values.ndim == 1 else (
                    Axis.index("row", values.shape[0]), paired
                )
        arrays[name] = DataArray(
            name, values,
            axes=axes or tuple(
                Axis.index(_INDEX_NAMES.get((values.ndim, i), f"dim{i}"), values.shape[i])
                for i in range(values.ndim)
            ),
        )
    return arrays


@dataclass(frozen=True, slots=True, eq=False)
class DatasetPatch:
    """One incremental update to an array in a running dataset.

    The reason the wire stops carrying whole arrays. Publishing "one more
    point" previously meant re-sending the entire accumulated result, so a
    30-point scan over a (32, 32, 64) detector produced ~31 MB per frame
    and `server.py::_strip_oversized_fields` exists purely to stop that
    breaking the WebSocket outright. A patch is the size of the new data.

    `index` addresses where the values go in the destination array, in the
    flat, row-major layout the result views already use: an int for one
    point, a slice for a contiguous run.
    """

    array: str
    index: int | slice
    values: np.ndarray
    run_uid: str = ""
    seq: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", np.asarray(self.values))

    @property
    def size(self) -> int:
        return int(self.values.size)

    def apply(self, target: np.ndarray | list) -> None:
        """Write these values into `target` in place.

        Accepts a list as well as an array because a scan in progress
        accumulates into a flat list with `None` for the points not yet
        taken, which is what the REST layer serialises.
        """
        flat = self.values.ravel()
        if isinstance(target, np.ndarray):
            view = target.reshape(-1)
            if isinstance(self.index, slice):
                view[self.index] = flat
            else:
                view[self.index : self.index + flat.size] = flat
            return
        start = self.index.start if isinstance(self.index, slice) else self.index
        target[start : start + flat.size] = flat.tolist()

    def to_wire(self) -> dict[str, Any]:
        """JSON-safe form for the event bus."""
        start = self.index.start if isinstance(self.index, slice) else self.index
        return {
            "array": self.array,
            "index": int(start),
            "values": self.values.ravel().tolist(),
            "run_uid": self.run_uid,
            "seq": self.seq,
        }
