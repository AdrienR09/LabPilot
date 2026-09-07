"""Every run lands on disk, indexed, without anyone clicking Save.

`ARCHITECTURE_NOTES.md` §4.5 called unwired persistence "the single most
concrete, closest-to-done gap". Two components had been written and wired
to nothing: `HDF5Writer`, which subscribed to the event stream of an
orphaned engine no REST route reaches (and whose `start()` never returned,
an un-exited task group), and `Catalogue`, the provenance index, which was
constructed nowhere. The only real persistence was a File->Save button
inside the Qt app, so a scan run from the web UI, the console or a
headless server left nothing behind.

What unblocked it is `Dataset`: there was previously no self-describing
object to write. These tests assert the *file* is worth having — units,
real coordinates, provenance — not merely that one was created.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.data import Dataset, RunMeta
from labpilot.core.storage.runs import RunStore

h5py = pytest.importorskip("h5py")


SCAN_RESULT = {
    "actuator": "stage",
    "detector": "spectrometer",
    "axis_names": ["x", "wavelengths"],
    "axis_positions": [[0.0, 1.0, 2.0], [500.0, 510.0]],
    "axis_units": {"x": "mm", "wavelengths": "nm"},
    "actuator_axis_count": 1,
    "value_unit": "counts",
    "shape": [3, 2],
    "data": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
}


@pytest.fixture
def store(tmp_path) -> RunStore:
    return RunStore(root=tmp_path / "data")


# --- Lifting a template's plain dict --------------------------------------


def test_a_scan_result_becomes_one_array_with_real_coordinates():
    """Templates return plain dicts and will keep doing so — a workflow is
    a `.py` file with `async def run(session) -> dict`. This is the seam
    that lets those dicts be stored without changing that."""
    dataset = Dataset.from_result(SCAN_RESULT, RunMeta.new_run("omniscan"))
    array = dataset.primary()
    assert array.shape == (3, 2)
    assert array.unit == "counts"
    assert array.values.tolist() == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
    assert [(a.name, a.unit) for a in dataset.axes()] == [("x", "mm"), ("wavelengths", "nm")]


def test_only_the_actuators_axes_are_movable():
    """What makes a crosshair drawable. `actuator_axis_count` said this
    positionally, as a string key in `RESULT_UI`."""
    dataset = Dataset.from_result(SCAN_RESULT)
    x_axis, wavelength_axis = dataset.axes()
    assert x_axis.movable and x_axis.device == "stage"
    assert not wavelength_axis.movable


def test_untaken_points_become_nan_not_none():
    """An aborted scan leaves `None` where a point was never measured; NaN
    is what that means to every reader of an HDF5 file."""
    partial = {**SCAN_RESULT, "data": [1.0, 2.0, None, None, None, None]}
    values = Dataset.from_result(partial).primary().values
    assert values[0].tolist() == [1.0, 2.0]
    assert np.isnan(values[1:]).all()


def test_scalars_are_metadata_not_one_element_arrays():
    dataset = Dataset.from_result(SCAN_RESULT, RunMeta.new_run("omniscan"))
    assert dataset.meta.params["actuator_axis_count"] == 1
    assert list(dataset.arrays) == ["data"]


def test_a_result_ui_says_which_loose_array_is_a_coordinate():
    """Not every template emits the N-D scan convention: a 1-D sweep
    returns two bare lists. While `RESULT_UI` still exists it knows which
    is the x — the one useful thing that map holds over a plain dict."""
    dataset = Dataset.from_result(
        {"positions": [0.0, 1.0, 2.0], "values": [9.0, 8.0, 7.0]},
        result_ui={"type": "spectrum", "x_key": "positions", "y_key": "values"},
    )
    assert dataset.primary().name == "values"
    assert [a.name for a in dataset.axes()] == ["positions"]


def test_a_result_with_no_arrays_at_all_produces_nothing_to_store():
    dataset = Dataset.from_result({"best_value": 42.0, "converged": True})
    assert dataset.arrays == {}


# --- What gets written ----------------------------------------------------


async def test_a_saved_run_is_readable_as_coordinates(store, tmp_path):
    dataset = Dataset.from_result(SCAN_RESULT, RunMeta.new_run("omniscan"))
    path = await store.save(dataset)
    assert path is not None and path.exists()

    with h5py.File(path, "r") as f:
        data = f["run/data"]
        assert data.attrs["units"] == "counts"
        assert data[:].tolist() == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
        # Real HDF5 dimension scales: xarray and MATLAB read these without
        # knowing anything about LabPilot.
        assert data.dims[0].label == "x"
        assert list(data.dims[0][0][:]) == [0.0, 1.0, 2.0]
        assert f["run/axes/x"].attrs["units"] == "mm"
        assert f["run/axes/x"].attrs["kind"] == "actuator"


async def test_a_saved_run_records_the_instruments_it_used(store):
    from labpilot.instruments import adapter_registry

    schema = adapter_registry.get("mock_ir_spectrometer").describe()
    dataset = Dataset.from_result(
        SCAN_RESULT,
        RunMeta(run_uid="u", plan_name="omniscan",
                devices={"detector": schema.model_dump(mode="json")}),
    )
    path = await store.save(dataset)
    with h5py.File(path, "r") as f:
        assert "detector" in f["run/devices"].attrs
        assert "wavenumbers" in f["run/devices"].attrs["detector"]


async def test_a_saved_run_is_indexed_and_findable(store):
    dataset = Dataset.from_result(SCAN_RESULT, RunMeta.new_run("omniscan"))
    path = await store.save(dataset)
    (row,) = await store.list_runs()
    assert row["run_uid"] == dataset.meta.run_uid
    assert row["plan_name"] == "omniscan"
    assert row["data_path"] == str(path)
    assert row["metadata"]["status"] == "completed"
    assert row["metadata"]["shape"] == [3, 2]


async def test_a_partial_run_is_saved_with_its_status(store):
    """Stopping a long scan must not throw away what it measured."""
    partial = {**SCAN_RESULT, "data": [1.0, 2.0, 3.0, None, None, None]}
    dataset = Dataset.from_result(partial, RunMeta.new_run("omniscan"))
    await store.save(dataset, status="cancelled")
    (row,) = await store.list_runs()
    assert row["metadata"]["status"] == "cancelled"


async def test_a_write_failure_is_reported_not_raised(tmp_path):
    """A scan that acquired real data must not be reported as failed
    because the disk was full."""
    store = RunStore(root=tmp_path / "unwritable")
    (tmp_path / "unwritable").mkdir()
    (tmp_path / "unwritable").chmod(0o500)
    try:
        result = await store.save(Dataset.from_result(SCAN_RESULT, RunMeta.new_run("s")))
        assert result is None
        assert store.last_error is not None
    finally:
        (tmp_path / "unwritable").chmod(0o700)


# --- Through the engine ---------------------------------------------------


async def test_running_a_workflow_leaves_a_file_behind(tmp_path, monkeypatch):
    """The end-to-end claim: no Save button, no manual export."""
    from labpilot.core.session import Session
    from labpilot.core.run.manager import RunManager
    from labpilot.core.workflow.store import WorkflowStore

    engine = RunManager(Session(), WorkflowStore(tmp_path / "workflows.db"))
    engine.runs = RunStore(root=tmp_path / "data")

    class _Graph:
        id = "wf-1"
        metadata = {"script_path": "", "instrument_bindings": {}}

    await engine._save_run(_Graph(), "exec-1", SCAN_RESULT, "completed")

    files = list((tmp_path / "data").rglob("*.h5"))
    assert len(files) == 1
    with h5py.File(files[0], "r") as f:
        assert f["run"].attrs["run_uid"] == "exec-1"
        assert f["run/data"].shape == (3, 2)
    engine._runner.shutdown()


def test_a_process_that_saves_a_run_still_exits(tmp_path):
    """`aiosqlite` runs each connection on a **non-daemon** thread, so a
    connection nobody closes finishes its work and then hangs the
    interpreter in `threading._shutdown`. Holding one open on the
    `RunStore` did exactly that: nothing failed, the process simply never
    exited — which is why this is asserted on a real subprocess rather
    than by counting threads, since that is the whole symptom."""
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(f"""
        import asyncio
        from labpilot.core.data import Dataset, RunMeta
        from labpilot.core.storage.runs import RunStore

        async def main():
            store = RunStore(root={str(tmp_path / "data")!r})
            await store.save(Dataset.from_result({SCAN_RESULT!r}, RunMeta.new_run("s")))
            await store.list_runs()

        asyncio.run(main())
    """)
    subprocess.run([sys.executable, "-c", script], check=True, timeout=60)
