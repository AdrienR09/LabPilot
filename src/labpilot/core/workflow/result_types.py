"""Typed alternatives to a hand-typed `RESULT_UI` dict.

A workflow template's `RESULT_UI` constant (see
`core/workflow/instrument_roles.py::read_result_ui`) has always been a plain
dict whose `*_key` string values must exactly match a key the script's own
`session.report_progress(...)`/return-value dict actually populates — pure
convention, never validated, so a typo'd key silently renders a blank panel
instead of erroring.

This module adds one dataclass per existing `RESULT_UI["type"]` shape
(`ImageResult`/`SpectrumResult`/`OdmrResult`/`NDScanResult`), each field named
after the concept it represents rather than the `*_key` convention, plus
`parse_result_ui_literal()` — the single reader both `instrument_roles.py`
(server side) and `workflow_window.py` (desktop side) use in place of a bare
`ast.literal_eval(stmt.value)`. The raw dict form keeps working completely
unchanged: `RESULT_UI = {"type": "image2d", "value_key": "data", ...}` is
still valid and requires no migration. `RESULT_UI = ImageResult(value="data",
...)` is the new, optional, typo-checked alternative.

Deliberately pure Python — no Qt, no `core.session`, no hardware import — so
it's safe to import from both the headless server process and the desktop
Qt process (the same property `core.api_client` already relies on).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "ResultUIError", "ImageResult", "SpectrumResult", "OdmrResult", "NDScanResult",
    "parse_result_ui_literal",
]


class ResultUIError(ValueError):
    """A `RESULT_UI = SomeResult(...)` construction is malformed (unknown
    field name, wrong type, missing required field) — raised instead of
    silently producing a blank/incomplete `RESULT_UI` dict, so the mistake
    surfaces at workflow-bind/execute time rather than as an empty panel."""


@dataclass(frozen=True)
class ImageResult:
    """`RESULT_UI["type"] == "image2d"` — a single 2D image, e.g. a
    confocal/generic 2D scan. `crosshair_role`/`crosshair_x_axis`/
    `crosshair_y_axis` are optional (see `RESULT_UI["crosshair"]`)."""

    value: str
    x: Optional[str] = None
    y: Optional[str] = None
    value_label: str = "Value"
    crosshair_role: Optional[str] = None
    crosshair_x_axis: Optional[str] = None
    crosshair_y_axis: Optional[str] = None

    def to_result_ui(self) -> dict:
        result_ui: dict = {
            "type": "image2d", "value_key": self.value, "x_key": self.x, "y_key": self.y,
            "value_label": self.value_label,
        }
        if self.crosshair_role is not None:
            result_ui["crosshair"] = {
                "role": self.crosshair_role,
                "x_axis": self.crosshair_x_axis,
                "y_axis": self.crosshair_y_axis,
            }
        return result_ui


@dataclass(frozen=True)
class SpectrumResult:
    """`RESULT_UI["type"] == "spectrum"` — a 1D x/y curve, with an optional
    fit overlay."""

    x: str
    y: str
    x_label: str = ""
    y_label: str = ""
    fit_x: Optional[str] = None
    fit_y: Optional[str] = None
    fit_center: Optional[str] = None

    def to_result_ui(self) -> dict:
        return {
            "type": "spectrum", "x_key": self.x, "y_key": self.y,
            "x_label": self.x_label, "y_label": self.y_label,
            "fit_x_key": self.fit_x, "fit_y_key": self.fit_y, "fit_center_key": self.fit_center,
        }


@dataclass(frozen=True)
class OdmrResult:
    """`RESULT_UI["type"] == "odmr"` — a spectrum plus a growing 2D
    accumulation matrix (one row per repeat), with an optional fit overlay."""

    x: str
    y: str
    matrix: str
    repeat: str
    x_label: str = ""
    y_label: str = ""
    fit_x: Optional[str] = None
    fit_y: Optional[str] = None
    fit_center: Optional[str] = None

    def to_result_ui(self) -> dict:
        return {
            "type": "odmr", "x_key": self.x, "y_key": self.y,
            "matrix_key": self.matrix, "repeat_key": self.repeat,
            "x_label": self.x_label, "y_label": self.y_label,
            "fit_x_key": self.fit_x, "fit_y_key": self.fit_y, "fit_center_key": self.fit_center,
        }


@dataclass(frozen=True)
class NDScanResult:
    """`RESULT_UI["type"] == "ndscan"` — an arbitrary-dimensionality scan
    (see omniscan.py)."""

    value: str
    shape: str
    axis_names: str
    axis_positions: str
    actuator_axis_count: Optional[str] = None
    value_label: str = "Value"
    crosshair_role: Optional[str] = None

    def to_result_ui(self) -> dict:
        result_ui: dict = {
            "type": "ndscan", "value_key": self.value, "shape_key": self.shape,
            "axis_names_key": self.axis_names, "axis_positions_key": self.axis_positions,
            "actuator_axis_count_key": self.actuator_axis_count, "value_label": self.value_label,
        }
        if self.crosshair_role is not None:
            result_ui["crosshair"] = {"role": self.crosshair_role}
        return result_ui


_CLASSES = {
    "ImageResult": ImageResult, "SpectrumResult": SpectrumResult,
    "OdmrResult": OdmrResult, "NDScanResult": NDScanResult,
}


def parse_result_ui_literal(node: ast.expr) -> dict:
    """Parses a `RESULT_UI = ...` assignment's value node into a plain
    dict — never imports/executes the script.

    Two forms: the historical raw dict/literal (`ast.literal_eval`,
    unchanged — every existing template's `RESULT_UI = {...}` keeps working
    exactly as before) or a call to one of this module's dataclasses
    (`RESULT_UI = ImageResult(value="data", x="xs", y="ys")`) — each keyword
    argument is individually `ast.literal_eval`'d, then passed to that
    class's constructor and `.to_result_ui()`.

    Raises `ResultUIError` if the node IS a call to a recognized class but
    the call itself is malformed (unknown field, wrong type, missing
    required field) — a mistake here should surface as a real error, not
    silently produce an empty/blank RESULT_UI. Any other node (a plain
    dict, or something that isn't a literal at all) is handled exactly as
    `ast.literal_eval` already handles it — including raising ValueError/
    TypeError for a genuinely non-literal expression, same as before this
    function existed.
    """
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CLASSES:
        cls = _CLASSES[node.func.id]
        if node.args:
            raise ResultUIError(f"RESULT_UI = {node.func.id}(...) must use keyword arguments only, not positional")
        kwargs = {}
        for kw in node.keywords:
            if kw.arg is None:
                raise ResultUIError(f"RESULT_UI = {node.func.id}(...) does not support **kwargs expansion")
            try:
                kwargs[kw.arg] = ast.literal_eval(kw.value)
            except (ValueError, SyntaxError) as e:
                raise ResultUIError(
                    f"RESULT_UI = {node.func.id}(...)'s {kw.arg!r} argument isn't a literal value: {e}"
                ) from e
        try:
            return cls(**kwargs).to_result_ui()
        except TypeError as e:
            raise ResultUIError(f"RESULT_UI = {node.func.id}(...) is malformed: {e}") from e
    return ast.literal_eval(node)
