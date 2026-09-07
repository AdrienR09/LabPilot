"""A workflow's settings are a row, not a rewritten source file.

Loading a template used to copy its `.py` into the *installed package*
directory under a timestamped name, and changing one parameter rewrote that
copy's assignment in place through an AST span edit. Three consequences,
all of them visible in the repository: 27 committed scripts under
`core/workflow_library/`, 22 of which are the same template across three
generations; a workflow that cannot be reconfigured at all on a
non-editable install, because its source is not writable; and parameters
that can only be read by parsing Python.

What actually distinguishes two instances of one template is their
parameters and their bindings. Both are rows now, and the template file is
shared and read-only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from labpilot.core.config.paths import user_workflow_dir
from labpilot.core.server import create_app

TEMPLATE = "omniscan"
TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1] / "src/labpilot/core/workflow_templates"
)
LIBRARY_DIR = (
    Path(__file__).resolve().parents[1] / "src/labpilot/core/workflow_library"
)


@pytest.fixture
def client():
    with TestClient(create_app()) as http:
        yield http


def _load(client: TestClient, template: str = TEMPLATE) -> str:
    response = client.post(f"/api/workflows/templates/{template}/load")
    assert response.status_code == 200, response.text
    return response.json()["data"]["workflow_id"]


def _params(client: TestClient, workflow_id: str) -> dict:
    response = client.get(f"/api/workflows/{workflow_id}/params")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_loading_a_template_writes_no_source_file(client):
    """It used to write one per load, into the installed package."""
    def scripts_in(directory: Path) -> list[str]:
        return sorted(p.name for p in directory.glob("*.py")) if directory.exists() else []

    before_package = scripts_in(LIBRARY_DIR)
    before_user = scripts_in(user_workflow_dir())

    workflow_id = _load(client)

    assert scripts_in(LIBRARY_DIR) == before_package
    assert scripts_in(user_workflow_dir()) == before_user

    graph = client.get(f"/api/workflows/{workflow_id}").json()["data"]
    assert graph["metadata"]["script_path"] == str(TEMPLATE_DIR / f"{TEMPLATE}.py")


def test_a_parameter_change_is_stored_without_touching_the_template(client):
    original = (TEMPLATE_DIR / f"{TEMPLATE}.py").read_text()
    workflow_id = _load(client)

    response = client.put(
        f"/api/workflows/{workflow_id}/params/SCAN_AXES", json={"value": ["x", "y"]}
    )

    assert response.status_code == 200, response.text
    assert _params(client, workflow_id)["SCAN_AXES"] == ["x", "y"]
    assert (TEMPLATE_DIR / f"{TEMPLATE}.py").read_text() == original


def test_the_declared_defaults_still_show_through(client):
    """The script says which parameters exist and what they default to; the
    row says only where this instance differs."""
    workflow_id = _load(client)
    client.put(f"/api/workflows/{workflow_id}/params/SCAN_AXES", json={"value": ["x"]})

    params = _params(client, workflow_id)

    assert params["SCAN_AXES"] == ["x"]
    assert params["SETTLE_TOLERANCE"] == 0.02  # untouched, from the template
    assert "AXIS_RANGES" in params


def test_two_instances_of_one_template_configure_independently(client):
    """The reason each instance needed its own copy of the source. They
    share the template file now, and differ by their rows."""
    first, second = _load(client), _load(client)

    client.put(f"/api/workflows/{first}/params/SCAN_AXES", json={"value": ["x"]})
    client.put(f"/api/workflows/{second}/params/SCAN_AXES", json={"value": ["y", "z"]})

    assert _params(client, first)["SCAN_AXES"] == ["x"]
    assert _params(client, second)["SCAN_AXES"] == ["y", "z"]


def test_both_instances_are_listed_although_they_share_a_script(client):
    """Loaded-ness used to be membership by script path, so two instances
    of one template were indistinguishable unless each had its own file."""
    first, second = _load(client), _load(client)

    listed = {wf["id"] for wf in client.get("/api/workflows").json()["data"]}

    assert {first, second} <= listed


def test_unloading_one_instance_leaves_the_other_loaded(client):
    first, second = _load(client), _load(client)

    client.delete(f"/api/workflows/{first}")

    listed = {wf["id"] for wf in client.get("/api/workflows").json()["data"]}
    assert first not in listed
    assert second in listed


def test_a_rejected_value_never_reaches_the_stored_settings(client):
    workflow_id = _load(client)
    client.put(f"/api/workflows/{workflow_id}/params/SCAN_AXES", json={"value": ["x"]})

    # A bare string where the parameter is declared as a list.
    response = client.put(
        f"/api/workflows/{workflow_id}/params/SCAN_AXES", json={"value": "x"}
    )

    assert response.status_code == 422
    assert _params(client, workflow_id)["SCAN_AXES"] == ["x"]


def test_an_unknown_parameter_is_refused(client):
    workflow_id = _load(client)
    response = client.put(
        f"/api/workflows/{workflow_id}/params/NOT_A_PARAM", json={"value": 1}
    )
    assert response.status_code == 404


def test_editing_a_template_instances_script_copies_it_out_of_the_package(client):
    """Instances share the shipped template, so an edit has to become a
    private copy — and it goes to the user's own directory, never back into
    the installed package."""
    original = (TEMPLATE_DIR / f"{TEMPLATE}.py").read_text()
    workflow_id = _load(client)

    response = client.put(
        f"/api/workflows/{workflow_id}/script",
        json={"content": original + "\n# edited\n"},
    )

    assert response.status_code == 200, response.text
    path = Path(response.json()["data"]["path"])
    assert path.parent == user_workflow_dir()
    assert path.read_text().endswith("# edited\n")
    # The template every other instance runs is untouched.
    assert (TEMPLATE_DIR / f"{TEMPLATE}.py").read_text() == original


def test_the_optimizer_reads_this_workflows_settings_not_the_templates(client):
    """Anything that consults a workflow's parameters has to consult the
    row, not the script — the optimizer derives which axes to scan and how
    far from `SCAN_AXES`/`AXIS_RANGES`, and would otherwise optimize over
    the template's defaults on a workflow configured to something else."""
    import time

    instruments = {i["adapter_type"]: i["id"] for i in client.get("/api/dashboard/instruments").json()["data"]}
    actuator, detector = instruments["mock_basic_actuator_nd"], instruments["mock_basic_detector_0d"]
    for instrument in (actuator, detector):
        client.post(f"/api/dashboard/instruments/{instrument}/connect")

    workflow_id = _load(client)
    client.put(f"/api/workflows/{workflow_id}/params/SCAN_AXES", json={"value": ["z"]})
    for role, instrument in (("actuator", actuator), ("detector", detector)):
        client.put(f"/api/workflows/{workflow_id}/bindings/{role}", json={"instrument_id": instrument})

    started = client.post(f"/api/workflows/{workflow_id}/optimize/start", json={"points": 3})
    assert started.status_code == 200, started.text
    for _ in range(400):
        state = client.get(f"/api/workflows/{workflow_id}/optimize/state").json()["data"]
        if not state["running"]:
            break
        time.sleep(0.05)

    assert state["error"] is None, state["error"]
    assert [list(step) for step in state["last_result"]["sequence"]] == [["z"]]


async def test_a_stored_parameter_is_what_the_run_actually_uses(tmp_path):
    """The end of the chain: a row on the workflow becomes a module
    attribute on the freshly imported template, which is where the template
    reads it. This is what the source rewrite used to achieve by editing
    the assignment itself."""
    from labpilot.core.session import Session
    from labpilot.core.workflow.engine import WorkflowEngine
    from labpilot.core.workflow.store import WorkflowStore

    script = tmp_path / "reports_its_own_settings.py"
    script.write_text(
        "POINTS = 5\n"
        "LABEL = 'default'\n"
        "async def run(session):\n"
        "    return {'points': POINTS, 'label': LABEL}\n"
    )
    engine = WorkflowEngine(Session(), WorkflowStore(tmp_path / "workflows.db"))
    try:
        result = await engine._execute_script(str(script), {"POINTS": 21})
        untouched = await engine._execute_script(str(script), None)
    finally:
        engine._runner.shutdown()

    assert result == {"points": 21, "label": "default"}
    # Each run imports the module afresh, so one workflow's settings do not
    # leak into another built on the same template.
    assert untouched == {"points": 5, "label": "default"}
