"""Workflows saved before an instance became a row still point at a copy.

Loading a template used to write a timestamped copy of its `.py` into the
installed package (`core/workflow_library/omniscan_1788705781.py`) and
point the stored workflow at that copy; changing a parameter rewrote the
assignment inside it through an AST span edit. Phase 3 replaced that with a
row — a script path, a parameters dict, a bindings dict — but rows created
before it still reference those copies, and the copies are the only
importers of `workflow/capabilities.py`.

This is what lets both go: the copies are deleted, and any row still naming
one is repointed at the template it was made from, keeping the bindings
that would actually hurt to redo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.core.workflow.graph import WorkflowGraph
from labpilot.core.workflow.migrate import (
    migrate_library_workflows,
    template_of_copy,
)
from labpilot.core.workflow.store import WorkflowStore

TEMPLATES = (
    Path(__file__).resolve().parents[1]
    / "src" / "labpilot" / "core" / "workflow_templates"
)


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(tmp_path / "workflows.db")


def _copy(tmp_path, template: str, stamp: str = "1788705781", body: str = "") -> Path:
    """A stand-in for one of the timestamped copies, in a directory named
    the way the real ones were."""
    library = tmp_path / "workflow_library"
    library.mkdir(exist_ok=True)
    path = library / f"{template}_{stamp}.py"
    path.write_text(body or (TEMPLATES / f"{template}.py").read_text())
    return path


def _save(store, path: Path, **metadata) -> str:
    graph = WorkflowGraph(name="Saved before the rewrite")
    graph.metadata["script_path"] = str(path)
    graph.metadata.update(metadata)
    store.save(graph, "test")
    return graph.id


# --- Recognising a copy ----------------------------------------------------


def test_a_timestamped_copy_names_the_template_it_came_from():
    assert template_of_copy("/x/workflow_library/omniscan_1788705781.py") == "omniscan"


def test_an_ordinary_template_is_not_a_copy():
    assert template_of_copy("/x/workflow_templates/omniscan.py") is None


def test_a_script_the_user_wrote_is_not_a_copy():
    """The migration must not touch a workflow loaded from someone's own
    directory, whatever it is called."""
    assert template_of_copy("/home/me/scans/omniscan_1788705781.py") is None


def test_a_template_whose_name_ends_in_a_small_number_is_not_a_copy():
    assert template_of_copy("/x/workflow_library/scan_2d.py") is None


# --- Migrating -------------------------------------------------------------


def test_a_workflow_is_repointed_at_the_real_template(store, tmp_path):
    workflow_id = _save(store, _copy(tmp_path, "omniscan"))

    assert migrate_library_workflows(store, TEMPLATES) == [workflow_id]

    graph = store.load(workflow_id)
    assert graph.metadata["script_path"] == str(TEMPLATES / "omniscan.py")
    assert graph.metadata["template_name"] == "omniscan"


def test_the_copy_s_parameters_are_lifted_into_the_row(store, tmp_path):
    """They were only ever in its source — that is the thing being undone."""
    source = (TEMPLATES / "omniscan.py").read_text().replace(
        'SCAN_AXES: list = ["x", "y", "z"]', "SCAN_AXES: list = ['x', 'y']"
    ).replace(
        'AXIS_RANGES = {\n    "x": (-4.0, 4.0, 5),',
        "AXIS_RANGES = {'x': (0.0, 50.0, 200),",
    )
    workflow_id = _save(store, _copy(tmp_path, "omniscan", body=source))

    migrate_library_workflows(store, TEMPLATES)

    params = store.load(workflow_id).metadata["params"]
    assert params["SCAN_AXES"] == ["x", "y"]
    assert params["AXIS_RANGES"]["x"] == [0.0, 50.0, 200]


def test_the_row_s_own_parameters_win_over_the_copy_s(store, tmp_path):
    """A row is the newer of the two — it is where a parameter has been
    written since the source rewrite stopped."""
    workflow_id = _save(
        store, _copy(tmp_path, "omniscan"), params={"SCAN_AXES": ["z"]}
    )

    migrate_library_workflows(store, TEMPLATES)

    assert store.load(workflow_id).metadata["params"]["SCAN_AXES"] == ["z"]


def test_bindings_survive(store, tmp_path):
    """The part that would actually hurt to redo."""
    bindings = {"actuator": "mock_basic_actuator_nd", "detector": "fake_apd_2"}
    workflow_id = _save(
        store, _copy(tmp_path, "omniscan"), instrument_bindings=bindings
    )

    migrate_library_workflows(store, TEMPLATES)

    assert store.load(workflow_id).metadata["instrument_bindings"] == bindings


def test_a_copy_already_deleted_still_gets_repointed(store, tmp_path):
    """An upgrade removes the copies, so most rows will be migrated with
    the file already gone. The workflow comes back at the template's
    defaults rather than staying broken."""
    missing = tmp_path / "workflow_library" / "omniscan_1788705781.py"
    workflow_id = _save(store, missing)

    assert migrate_library_workflows(store, TEMPLATES) == [workflow_id]
    assert store.load(workflow_id).metadata["script_path"] == str(
        TEMPLATES / "omniscan.py"
    )


def test_a_copy_of_something_that_became_a_preset_follows_it(store, tmp_path):
    """`confocal_scanner` is now a preset of omniscan, so a copy of it
    should run omniscan with the preset's parameters."""
    workflow_id = _save(store, tmp_path / "workflow_library" / "confocal_scanner_1788705781.py")

    migrate_library_workflows(store, TEMPLATES)

    graph = store.load(workflow_id)
    assert graph.metadata["script_path"] == str(TEMPLATES / "omniscan.py")
    assert graph.metadata["params"]["SCAN_AXES"] == ["x", "y"]


def test_a_copy_of_a_template_that_is_gone_is_left_alone(store, tmp_path):
    """Reported, not rewritten to run something else."""
    path = tmp_path / "workflow_library" / "long_deleted_thing_1788705781.py"
    workflow_id = _save(store, path)

    assert migrate_library_workflows(store, TEMPLATES) == []
    assert store.load(workflow_id).metadata["script_path"] == str(path)


def test_an_ordinary_workflow_is_untouched(store, tmp_path):
    workflow_id = _save(store, TEMPLATES / "omniscan.py")
    assert migrate_library_workflows(store, TEMPLATES) == []
    assert store.load(workflow_id).metadata["script_path"] == str(
        TEMPLATES / "omniscan.py"
    )


def test_running_it_twice_changes_nothing_the_second_time(store, tmp_path):
    """It runs on every server start."""
    _save(store, _copy(tmp_path, "omniscan"))
    assert len(migrate_library_workflows(store, TEMPLATES)) == 1
    assert migrate_library_workflows(store, TEMPLATES) == []
