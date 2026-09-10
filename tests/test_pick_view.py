"""Choosing a result view from the data instead of a hand-written map.

Fifteen templates each declare a `RESULT_UI` mapping ad-hoc result keys to
a renderer, and nothing validates them — a key that does not match what
the script returns renders a blank panel, silently. They had to exist
because a result dict could not describe itself.

These tests assert `pick_view` reaches the same answer the templates
declare by hand, from the data alone. Where it does, `RESULT_UI` stops
being mandatory; where a template wants something the data does not imply
(an ODMR accumulation matrix, a fit overlay), it still declares one and
that always wins.
"""

from __future__ import annotations

from labpilot.core.workflow.view import pick_view

SCAN_2D = {
    "actuator": "actuator",
    "axis_names": ["x", "y"],
    "axis_positions": [[0.0, 1.0], [0.0, 1.0, 2.0]],
    "axis_units": {"x": "mm", "y": "mm"},
    "actuator_axis_count": 2,
    "value_unit": "counts",
    "shape": [2, 3],
    "data": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
}


def test_a_scan_gets_the_nd_view_with_keys_that_resolve():
    """Every `*_key` must name something the result actually carries —
    the failure mode a hand-written map has and this cannot."""
    spec = pick_view(SCAN_2D)
    assert spec["type"] == "ndscan"
    for field in ("value_key", "shape_key", "axis_names_key", "axis_positions_key"):
        assert spec[field] in SCAN_2D, field


def test_the_inferred_scan_spec_matches_what_omniscan_declares_by_hand():
    """omniscan's own `RESULT_UI`, minus the label wording."""
    spec = pick_view(SCAN_2D)
    declared = {
        "type": "ndscan", "value_key": "data", "shape_key": "shape",
        "axis_names_key": "axis_names", "axis_positions_key": "axis_positions",
        "actuator_axis_count_key": "actuator_axis_count",
        "crosshair": {"role": "actuator"},
    }
    assert {k: spec[k] for k in declared} == declared


def test_a_crosshair_appears_only_where_something_can_be_driven():
    """`Axis.movable` is the condition. `RESULT_UI` said this positionally,
    as the string `actuator_axis_count_key`."""
    detector_only = {**SCAN_2D, "actuator_axis_count": 0, "actuator": None}
    assert "crosshair" not in pick_view(detector_only)
    assert pick_view(SCAN_2D)["crosshair"] == {"role": "actuator"}


def test_a_one_dimensional_result_becomes_a_spectrum():
    """A 1-D sweep whose axis is declared plots the measurement against
    it. The declaration can come from the template's `RESULT_UI` (below)
    or, for a detector reading, from the device's own parameters."""
    spec = pick_view(
        {"positions": [0.0, 1.0, 2.0], "values": [9.0, 8.0, 7.0]},
        result_ui={"x_key": "positions", "y_key": "values"},
    )
    assert spec["type"] == "spectrum"
    assert spec["y_key"] == "values"
    assert spec["x_key"] == "positions"


def test_two_bare_arrays_are_ambiguous_and_are_not_guessed_at():
    """`{"positions": [...], "values": [...]}` with nothing declared does
    not say which is the axis, and picking by name is exactly the failure
    this work removed — the IR spectrometer's wavenumbers ending up where
    the measurement belonged. What comes back is the primary against its
    own index: a real view where there used to be none, and correct as
    soon as the data carries an axis."""
    spec = pick_view({"positions": [0.0, 1.0, 2.0], "values": [9.0, 8.0, 7.0]})
    assert spec["type"] == "spectrum"
    assert spec["x_key"] is None


def test_labels_carry_the_units_the_devices_declared():
    spec = pick_view(SCAN_2D)
    assert spec["value_label"] == "data (counts)"


def test_a_result_with_nothing_to_plot_picks_no_view():
    assert pick_view({"best_value": 42.0}) is None
    assert pick_view({}) is None


def test_an_image_result_names_its_coordinate_arrays():
    spec = pick_view({
        "image": [[1.0, 2.0], [3.0, 4.0]],
        "x_positions": [0.0, 1.0],
        "y_positions": [0.0, 1.0],
    })
    assert spec["type"] == "image2d"
    assert spec["value_key"] == "image"


def test_every_template_that_declares_a_scan_view_would_get_one_anyway():
    """The claim that `RESULT_UI` is no longer *required*: for the
    templates whose result the data can describe, the inferred spec picks
    the same renderer the template names."""
    from pathlib import Path

    from labpilot.core.workflow.instrument_roles import read_result_ui_from_file

    templates = Path("src/labpilot/core/workflow_templates")
    scanning = {}
    for path in sorted(templates.glob("*.py")):
        declared = read_result_ui_from_file(path)
        if declared.get("type") == "ndscan":
            scanning[path.stem] = declared
    assert scanning, "no N-D scan template found"
    for name, declared in scanning.items():
        inferred = pick_view(SCAN_2D)
        assert inferred["type"] == declared["type"], name


# --- A pulse sequence's timing diagram --------------------------------------


def test_a_timing_diagram_is_inferred_from_its_segments():
    """So the sequence editor's result renders whether or not the template
    declares a RESULT_UI — the same inference every other view gets."""
    spec = pick_view(
        {
            "segments": [
                {"channel": "laser", "start": 0.0, "stop": 3e-6, "level": 1.0},
                {"channel": "mw", "start": 0.0, "stop": 2e-8, "level": 0.25},
            ],
            "channels": ["gate", "laser", "mw"],
            "point_duration": 4.7e-6,
        }
    )
    assert spec["type"] == "pulse_sequence"
    assert spec["segments_key"] == "segments"


def test_something_merely_called_segments_is_not_a_timing_diagram():
    """Decided by structure, not by a key name — otherwise a workflow
    emitting line segments would render as a pulse sequence, which is the
    name-guessing this inference work removed everywhere else."""
    spec = pick_view({"segments": [[0.0, 1.0], [1.0, 2.0]]})
    assert spec is None or spec["type"] != "pulse_sequence"


def test_an_empty_segment_list_is_not_a_timing_diagram():
    spec = pick_view({"segments": []})
    assert spec is None or spec["type"] != "pulse_sequence"


# --- A pulsed measurement ---------------------------------------------------


PULSED = {
    "data": [1.0, 0.9, 0.8, 1.0, 0.9, 0.8],
    "shape": [2, 3],
    "axis_names": ["sweeps", "tau"],
    "axis_positions": [[100.0, 200.0], [1e-8, 2e-8, 3e-8]],
    "curve": [1.0, 0.9, 0.8],
    "extraction": {"window": [37, 412], "bin_width_s": 8e-9, "profile": [1, 2, 3]},
}


def test_a_pulsed_measurement_is_inferred_from_its_curve_and_extraction():
    """Its `data` is the accumulation history, which the N-D scan view
    would render as an image of nothing much. What a person wants is the
    curve and the readout window it came from."""
    assert pick_view(PULSED)["type"] == "pulsed"


def test_a_pulsed_result_wins_over_the_n_d_scan_convention():
    """It carries `data`/`shape`/`axis_names` too, so the order of the
    two checks is what decides — and this one is more specific."""
    assert {"shape", "axis_names", "axis_positions"} <= set(PULSED)
    assert pick_view(PULSED)["type"] != "ndscan"


def test_a_curve_with_no_extraction_is_not_a_pulsed_measurement():
    """Half the picture is not the picture. A run with only one of the
    two is something else that shares a key name."""
    spec = pick_view({**PULSED, "extraction": None})
    assert spec is None or spec["type"] != "pulsed"


def test_an_extraction_with_no_curve_is_not_one_either():
    spec = pick_view({**PULSED, "curve": None})
    assert spec is None or spec["type"] != "pulsed"


def test_the_pulsed_template_declares_what_would_be_inferred_anyway():
    from pathlib import Path

    from labpilot.core.workflow.instrument_roles import read_result_ui_from_file

    declared = read_result_ui_from_file(
        Path("src/labpilot/core/workflow_templates/pulsed_measurement.py")
    )
    assert declared["type"] == pick_view(PULSED)["type"] == "pulsed"
