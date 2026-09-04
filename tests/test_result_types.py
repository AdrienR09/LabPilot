"""Tests for core.workflow.result_types (typed RESULT_UI dataclasses).

RESULT_VIEW_REGISTRY (components/workflow_result.py) is deliberately NOT
exercised here — it's a Qt/pyqtgraph/pymodaq_gui-heavy desktop module, and
`tests/` (this directory) has always been the headless, Qt-free server-side
suite; importing it here pulls in both PyQt5 (pymodaq_gui's own internal
default) and PyQt6 (this project's real binding) into the SAME process,
which is a known-fragile combination (see the SIGBUS/metaclass-conflict
findings from this project's own manual Qt testing) and, confirmed while
adding these tests, genuinely crashes the whole test collection with a
metaclass conflict when combined with the rest of this suite (works in
isolation, fails when collected alongside the other test files — a real,
reproducible interaction, not flakiness). RESULT_VIEW_REGISTRY is verified
instead via the same offscreen-Qt-harness scripts already used for every
other desktop-side check this project relies on."""

from __future__ import annotations

import ast

import pytest

from core.workflow.result_types import (
    ImageResult, NDScanResult, OdmrResult, ResultUIError, SpectrumResult, parse_result_ui_literal,
)


def _value_node(source: str) -> ast.expr:
    """The value-expression AST node of a `RESULT_UI = <source>` one-liner."""
    tree = ast.parse(f"RESULT_UI = {source}")
    return tree.body[0].value


class TestParseResultUiLiteral:
    def test_plain_dict_round_trips_unchanged(self):
        result = parse_result_ui_literal(_value_node("{'type': 'image2d', 'value_key': 'data'}"))
        assert result == {"type": "image2d", "value_key": "data"}

    def test_image_result_call(self):
        result = parse_result_ui_literal(_value_node("ImageResult(value='data', x='xs', y='ys')"))
        assert result == {
            "type": "image2d", "value_key": "data", "x_key": "xs", "y_key": "ys",
            "value_label": "Value",
        }

    def test_image_result_with_crosshair(self):
        result = parse_result_ui_literal(
            _value_node("ImageResult(value='data', x='xs', y='ys', crosshair_role='actuator')")
        )
        assert result["crosshair"] == {"role": "actuator", "x_axis": None, "y_axis": None}

    def test_spectrum_result_call(self):
        result = parse_result_ui_literal(_value_node("SpectrumResult(x='xs', y='ys')"))
        assert result["type"] == "spectrum"
        assert result["x_key"] == "xs"
        assert result["y_key"] == "ys"

    def test_odmr_result_call(self):
        result = parse_result_ui_literal(
            _value_node("OdmrResult(x='xs', y='ys', matrix='m', repeat='r')")
        )
        assert result["type"] == "odmr"
        assert result["matrix_key"] == "m"
        assert result["repeat_key"] == "r"

    def test_ndscan_result_call(self):
        result = parse_result_ui_literal(
            _value_node(
                "NDScanResult(value='data', shape='shape', axis_names='names', axis_positions='positions')"
            )
        )
        assert result["type"] == "ndscan"
        assert result["value_key"] == "data"

    def test_unknown_field_name_raises(self):
        with pytest.raises(ResultUIError):
            parse_result_ui_literal(_value_node("ImageResult(vlaue='data')"))

    def test_missing_required_field_raises(self):
        with pytest.raises(ResultUIError):
            parse_result_ui_literal(_value_node("ImageResult()"))

    def test_positional_args_rejected(self):
        with pytest.raises(ResultUIError):
            parse_result_ui_literal(_value_node("ImageResult('data')"))

    def test_non_literal_dict_raises_like_before(self):
        # Not a recognized dataclass call, and not a literal either — same
        # failure ast.literal_eval always raised for this, pre-dataclass-
        # support.
        with pytest.raises(ValueError):
            parse_result_ui_literal(_value_node("some_function_call()"))


class TestDataclassConstructionDirectly:
    def test_image_result_to_result_ui(self):
        assert ImageResult(value="d", x="x", y="y").to_result_ui() == {
            "type": "image2d", "value_key": "d", "x_key": "x", "y_key": "y", "value_label": "Value",
        }

    def test_spectrum_result_to_result_ui(self):
        r = SpectrumResult(x="x", y="y", fit_x="fx", fit_y="fy", fit_center="fc")
        d = r.to_result_ui()
        assert d["fit_x_key"] == "fx" and d["fit_y_key"] == "fy" and d["fit_center_key"] == "fc"

    def test_odmr_result_to_result_ui(self):
        r = OdmrResult(x="x", y="y", matrix="m", repeat="r")
        assert r.to_result_ui()["type"] == "odmr"

    def test_ndscan_result_to_result_ui(self):
        r = NDScanResult(value="v", shape="s", axis_names="n", axis_positions="p")
        assert r.to_result_ui()["type"] == "ndscan"
