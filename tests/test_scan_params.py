"""One rule for "which axes does this workflow sweep", not two copies.

The intersection of `SCAN_AXES`, `AXIS_RANGES` and what the bound actuator
can actually move was computed in two places: `server.py`, to decide what
the optimizer sweeps and which step each progress update belongs to, and
`workflow_window.py`, to lay out one optimizer pane per step. Both
docstrings said the two "need to agree"; one of them recorded, as a known
limitation, a case where they do not.

Two copies of a rule cannot be made to agree by saying they must. These
tests cover the rule itself — and, at the end, the two disagreements the
copies actually had.
"""

from __future__ import annotations

from labpilot.core.run.plans import decompose
from labpilot.core.workflow.scan_params import resolve_scan_axes, settable_names

OMNISCAN = {
    "SCAN_AXES": ["x", "y", "z"],
    "AXIS_RANGES": {"x": [-4.0, 4.0, 20], "y": [-4.0, 4.0, 20], "z": [-1.0, 1.0, 10]},
}


class _Schema:
    """A `DeviceSchema`-shaped object, as the server holds one."""

    def __init__(self, settable):
        self.settable = settable


def test_a_grid_workflow_sweeps_what_it_declares():
    axes, ranges = resolve_scan_axes(OMNISCAN, _Schema({"x": "f8", "y": "f8", "z": "f8"}))
    assert axes == ["x", "y", "z"]
    assert ranges["z"] == (-1.0, 1.0, 10)


def test_an_axis_the_bound_actuator_lacks_is_dropped():
    """`AXIS_RANGES` is authored generically; the instrument bound to the
    role may have fewer axes."""
    axes, ranges = resolve_scan_axes(OMNISCAN, _Schema({"x": "f8", "y": "f8"}))
    assert axes == ["x", "y"]
    assert "z" not in ranges


def test_the_rest_api_s_schema_dict_works_as_well_as_the_object():
    """The desktop app has the JSON the REST API served, the server has a
    `DeviceSchema`. The rule does not care which."""
    from_object = resolve_scan_axes(OMNISCAN, _Schema({"x": "f8", "y": "f8"}))
    from_dict = resolve_scan_axes(OMNISCAN, {"settable": {"x": "f8", "y": "f8"}})
    assert from_object == from_dict


def test_a_workflow_with_no_grid_falls_back_to_the_crosshair_pair():
    """confocal_scanner.py declares neither SCAN_AXES nor AXIS_RANGES."""
    params = {"X_POSITIONS": [0.0, 1.0, 2.0], "Y_POSITIONS": [0.0, 0.5]}
    axes, ranges = resolve_scan_axes(params, None, x_axis="x", y_axis="y")
    assert axes == ["x", "y"]
    assert ranges["x"] == (0.0, 2.0, 3)


def test_a_workflow_declaring_no_positions_still_gets_a_span():
    """Only ever used to seed a default search range, so a placeholder is
    better than refusing to optimize."""
    _axes, ranges = resolve_scan_axes({}, None, x_axis="x", y_axis="y")
    assert ranges["x"] == (-0.5, 0.5, 5)


def test_requesting_a_subset_narrows_it():
    axes, _ = resolve_scan_axes(
        OMNISCAN, _Schema({"x": "f8", "y": "f8", "z": "f8"}), requested_axes=["x", "z"]
    )
    assert axes == ["x", "z"]


def test_requesting_an_axis_this_workflow_lacks_drops_it():
    """Rather than raising — the same treatment an unavailable SCAN_AXES
    entry already gets."""
    axes, _ = resolve_scan_axes(
        OMNISCAN, _Schema({"x": "f8", "y": "f8"}), requested_axes=["x", "z"]
    )
    assert axes == ["x"]


def test_settable_names_of_nothing_is_empty():
    assert settable_names(None) == set()
    assert settable_names({}) == set()


# --- The two disagreements the copies actually had -------------------------


def test_the_sweep_order_is_the_declared_order_not_the_range_dict_s():
    """The desktop copy read its axis list off `AXIS_RANGES.keys()` while
    the server swept in `SCAN_AXES` order. A template that lists them
    differently paired the axes differently in each process, so an
    optimizer step's results were drawn in the pane for another step.
    """
    params = {
        "SCAN_AXES": ["z", "x", "y"],
        "AXIS_RANGES": {"x": [-1, 1, 5], "y": [-1, 1, 5], "z": [-1, 1, 5]},
    }
    axes, _ = resolve_scan_axes(params, _Schema({"x": "f8", "y": "f8", "z": "f8"}))

    assert axes == ["z", "x", "y"], "swept in the order the template declares"
    assert decompose(axes) == [("z", "x"), ("y",)]


def test_narrowing_the_axes_repairs_them_the_same_way_in_both_processes():
    """The limitation the desktop copy documented: excluding an axis can
    change how the *remaining* ones pair up, and the panes were built from
    a decomposition computed before the exclusion. One rule plus one
    `decompose` means both sides now derive the same steps from the same
    axis list.
    """
    schema = _Schema({"x": "f8", "y": "f8", "z": "f8"})
    full, _ = resolve_scan_axes(OMNISCAN, schema)
    narrowed, _ = resolve_scan_axes(OMNISCAN, schema, requested_axes=["x", "z"])

    assert decompose(full) == [("x", "y"), ("z",)]
    assert decompose(narrowed) == [("x", "z")], "dropping y re-pairs x with z"
