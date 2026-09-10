"""Choosing a result view from the data instead of from a string map.

Every workflow template declares a `RESULT_UI` — a dict mapping ad-hoc
result keys to a renderer:

    RESULT_UI = {"type": "image2d", "value_key": "image",
                 "x_key": "x_positions_mm", "y_key": "y_positions_mm"}

Fifteen of these exist, one per template, and nothing validates them: a
key that does not match what the script actually returns renders a blank
panel, silently. They also had to exist, because a result dict could not
describe itself — `{"image": [[...]], "x_positions_mm": [...]}` gives a
renderer no way to know which array is the picture and which is a
coordinate.

`Dataset` does describe itself, so that question can be *asked*:

- the rank of the primary array says whether this is a curve or an image;
- each axis knows whether something can be driven along it
  (`Axis.movable`), which is precisely the condition for a draggable
  crosshair — `RESULT_UI` says this as the string
  `"actuator_axis_count_key"`, a positional convention a typo breaks;
- axis names and units come from the devices themselves.

`pick_view` returns a spec in exactly the `RESULT_UI` shape, so the four
existing view adapters render it unchanged. `RESULT_UI` is not deleted: a
template that wants a specific presentation — an ODMR sweep's
accumulation matrix, a fit overlay, a particular label — still declares
one, and an explicit declaration always wins. What changes is that
declaring one stops being *mandatory*, so a new template gets a working
live view for free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from labpilot.core.data.dataset import Dataset

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["pick_view"]


def pick_view(
    result: Mapping[str, Any], result_ui: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """A `RESULT_UI`-shaped spec inferred from a workflow result, or None.

    None means "nothing to plot" — a result with no arrays at all, or one
    whose shape this cannot render. A caller should then show no result
    view, exactly as it does today for a template that declares no
    `RESULT_UI`.

    ## Where inference is complete, and where it is not

    A scan emitting the N-D convention (`data` + `shape` + `axis_names` +
    `axis_positions`) is fully determined: which array is the measurement,
    what its coordinates are, and which of them can be driven. Nothing is
    guessed.

    A result that is just two bare equal-length lists —
    `{"positions": [...], "values": [...]}` — is genuinely ambiguous, and
    saying otherwise would reintroduce exactly the name-guessing this work
    removed. Without a hint the primary array is plotted against its own
    index, which is a real view where there used to be none, and becomes
    correct the moment the data carries an axis. `result_ui`, when the
    template declares one, supplies that hint.
    """
    # A timing diagram is not an array of measurements, so it is decided
    # before the dataset inference runs — `segments` is a list of records,
    # and asking `Dataset` to read it as a data array would either find
    # nothing or find the wrong thing.
    if _is_timing_diagram(result):
        return {
            "type": "pulse_sequence",
            "segments_key": "segments",
            "channels_key": "channels",
            "duration_key": "point_duration",
        }

    # Likewise a pulsed measurement: its `data` is the 2-D accumulation
    # history, which `NDScanResultView` would render as an image of
    # nothing much. What a person wants is the curve and the readout
    # window the curve was extracted from, and both are in the result.
    if _is_pulsed(result):
        return {"type": "pulsed"}

    dataset = Dataset.from_result(result, result_ui=result_ui)
    if not dataset.arrays:
        return None

    primary = dataset.primary()
    axes = dataset.axes()

    # The N-D scan convention: one array plus its shape and coordinates,
    # which `NDScanResultView` already renders as coupled 2-D projections
    # for any rank. Detected by the keys the result actually carries, so
    # the spec's *_key values are guaranteed to resolve.
    if primary.name == "data" and {"shape", "axis_names", "axis_positions"} <= set(result):
        spec: dict[str, Any] = {
            "type": "ndscan",
            "value_key": "data",
            "shape_key": "shape",
            "axis_names_key": "axis_names",
            "axis_positions_key": "axis_positions",
            "value_label": _label(primary.name, primary.unit),
        }
        if "actuator_axis_count" in result:
            spec["actuator_axis_count_key"] = "actuator_axis_count"
        movable = next((axis for axis in axes if axis.movable), None)
        if movable is not None and movable.device:
            # A crosshair is drawable exactly when an axis names something
            # that can be driven along it.
            spec["crosshair"] = {"role": movable.device}
        return spec

    if primary.ndim == 1:
        axis = axes[0] if axes else None
        x_key = axis.name if axis is not None and axis.name in result else None
        return {
            "type": "spectrum",
            "x_key": x_key,
            "y_key": primary.name,
            "x_label": _label(axis.name, axis.unit) if axis is not None else "",
            "y_label": _label(primary.name, primary.unit),
        }

    if primary.ndim == 2:
        rows, columns = axes[0], axes[1]
        spec = {
            "type": "image2d",
            "value_key": primary.name,
            # Only name a coordinate key the result actually carries;
            # `Image2DResultView` falls back to pixel indices for a None.
            "x_key": columns.name if columns.name in result else None,
            "y_key": rows.name if rows.name in result else None,
            "value_label": _label(primary.name, primary.unit),
        }
        if rows.movable and columns.movable and rows.device == columns.device:
            spec["crosshair"] = {
                "role": rows.device, "x_axis": columns.name, "y_axis": rows.name,
            }
        return spec

    return None


def _is_timing_diagram(result: Mapping[str, Any]) -> bool:
    """Whether this result is a pulse sequence's timing diagram.

    Decided by structure, not by a key name: the first segment must
    actually look like one. A workflow that happens to emit something
    called `segments` meaning line segments would otherwise be rendered as
    a pulse sequence, which is the kind of name-guessing the inference
    work removed everywhere else.
    """
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        return False
    first = segments[0]
    return isinstance(first, dict) and {"channel", "start", "stop"} <= set(first)


def _is_pulsed(result: Mapping[str, Any]) -> bool:
    """Whether this result is a pulsed measurement.

    Structural, like `_is_timing_diagram`: it must carry the analysed
    curve *and* the extraction that produced it. A run with only one of
    the two is something else that happens to share a key name, and the
    view would show half a picture.
    """
    curve = result.get("curve")
    extraction = result.get("extraction")
    if not isinstance(curve, list) or not isinstance(extraction, dict):
        return False
    return {"window", "bin_width_s"} <= set(extraction)


def _label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit else name
