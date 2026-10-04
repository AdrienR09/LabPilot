"""Reading a saved run back, and handing it to xarray.

`to_hdf5` has existed since persistence was wired and `from_hdf5` has
not, which made every saved run a file you could write and not open:
`lp.runs` listed data that could only be looked at in another program.

Two things these tests are really about.

**A round trip has to be lossless**, because the parts most easily lost
are the parts that cannot be reconstructed — a plan's sweep bounds, the
sample the data is of, whether the working tree was dirty. The writer was
also split in two until now: `RunStore` added the parameters and the
device schemas *after* `to_hdf5` had written everything else, so an
auto-saved run carried them and `dataset.to_hdf5("rabi.h5")` from a
console did not. The file someone emails is exactly the one that has to
say what the sweep bounds were.

**Axes have to come back attached to the right dimension.** They are
stored as HDF5 dimension scales with labels, and matching them by length
instead would pair the wrong coordinate onto a square scan — a bug that
produces a plausible picture rather than an error.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta
from labpilot.core.storage.runs import RunStore

h5py = pytest.importorskip("h5py")


def _scan(width: int = 4, height: int = 3) -> Dataset:
    axes = (
        Axis("x", np.linspace(0.0, 1.0, width), unit="mm",
             kind="actuator", device="stage"),
        Axis("y", np.linspace(0.0, 2.0, height), unit="mm",
             kind="actuator", device="stage"),
    )
    data = DataArray(
        "counts",
        np.arange(float(width * height)).reshape(width, height),
        unit="counts",
        axes=axes,
    )
    return Dataset(
        (data,),
        RunMeta(
            run_uid="abc123", plan_name="scan", timestamp=1_700_000_000.0,
            params={"SWEEP_START": 2.82e9, "POINTS": 21},
            software={"labpilot": "0.1.0", "git_dirty": "yes"},
            context={"sample": "NV-3", "cooldown": 7},
            devices={"stage": {"name": "stage", "kind": "motor"}},
        ),
    )


# --- The round trip ---------------------------------------------------------


def test_the_numbers_come_back(tmp_path):
    ds = _scan()
    ds.to_hdf5(tmp_path / "scan.h5")
    back = Dataset.from_hdf5(tmp_path / "scan.h5")

    assert back.arrays["counts"].values.shape == (4, 3)
    assert np.allclose(back.arrays["counts"].values, ds.arrays["counts"].values)
    assert back.arrays["counts"].unit == "counts"


def test_the_axes_come_back_on_the_right_dimensions(tmp_path):
    """Matching by length instead of by the stored dimension labels would
    pair the wrong coordinate onto a square scan, which looks like data."""
    ds = _scan(width=5, height=5)
    ds.to_hdf5(tmp_path / "square.h5")
    back = Dataset.from_hdf5(tmp_path / "square.h5")

    names = [axis.name for axis in back.arrays["counts"].axes]
    assert names == ["x", "y"]
    assert np.allclose(back.arrays["counts"].axes[1].values, np.linspace(0, 2, 5))


def test_an_axis_keeps_what_makes_a_crosshair_possible(tmp_path):
    """`kind` and `device` are what let a view decide an axis is draggable.
    Losing them turns an interactive scan into a picture."""
    _scan().to_hdf5(tmp_path / "scan.h5")
    axis = Dataset.from_hdf5(tmp_path / "scan.h5").arrays["counts"].axes[0]

    assert axis.kind == "actuator"
    assert axis.device == "stage"
    assert axis.movable


def test_the_run_identity_comes_back(tmp_path):
    _scan().to_hdf5(tmp_path / "scan.h5")
    meta = Dataset.from_hdf5(tmp_path / "scan.h5").meta

    assert meta.run_uid == "abc123"
    assert meta.plan_name == "scan"
    assert meta.timestamp == pytest.approx(1_700_000_000.0)


def test_the_plan_parameters_come_back(tmp_path):
    """The sweep bounds. Not recoverable from the numbers, and the thing
    someone asks first about a file from a year ago."""
    _scan().to_hdf5(tmp_path / "scan.h5")
    params = dict(Dataset.from_hdf5(tmp_path / "scan.h5").meta.params)

    assert params["SWEEP_START"] == pytest.approx(2.82e9)
    assert params["POINTS"] == 21


def test_the_provenance_and_the_sample_come_back(tmp_path):
    _scan().to_hdf5(tmp_path / "scan.h5")
    meta = Dataset.from_hdf5(tmp_path / "scan.h5").meta

    assert dict(meta.software)["labpilot"] == "0.1.0"
    assert dict(meta.software)["git_dirty"] == "yes"
    assert dict(meta.context)["sample"] == "NV-3"
    assert dict(meta.context)["cooldown"] == 7


def test_the_device_schemas_come_back(tmp_path):
    _scan().to_hdf5(tmp_path / "scan.h5")
    devices = dict(Dataset.from_hdf5(tmp_path / "scan.h5").meta.devices)

    assert devices["stage"]["kind"] == "motor"


def test_a_console_written_file_is_as_complete_as_a_saved_run(tmp_path):
    """The split writer, which is the actual bug this closes: `RunStore`
    added the parameters and the schemas after `to_hdf5`, so only the
    automatic path had them."""
    _scan().to_hdf5(tmp_path / "by_hand.h5")
    with h5py.File(tmp_path / "by_hand.h5", "r") as f:
        assert "params" in f
        assert "devices" in f
        assert dict(f["params"].attrs)["POINTS"] == 21


def test_strings_come_back_as_strings_not_bytes(tmp_path):
    """h5py hands back `bytes`, which compares unequal to what was written
    and fails a round trip for reasons that are not about the data."""
    _scan().to_hdf5(tmp_path / "scan.h5")
    meta = Dataset.from_hdf5(tmp_path / "scan.h5").meta

    assert isinstance(meta.run_uid, str)
    assert isinstance(dict(meta.context)["sample"], str)


def test_a_zero_dimensional_reading_round_trips(tmp_path):
    """A single detector read is a `Dataset` too, and the one with no axes
    at all is where an `axes` group that is always created pays off."""
    ds = Dataset(
        (DataArray("value", np.asarray(1.5), unit="V"),),
        RunMeta(run_uid="single", device="apd"),
    )
    ds.to_hdf5(tmp_path / "read.h5")
    back = Dataset.from_hdf5(tmp_path / "read.h5")

    assert back.arrays["value"].values.item() == pytest.approx(1.5)
    assert back.meta.device == "apd"


def test_an_axis_no_array_indexes_is_kept(tmp_path):
    """A per-point time base on a 1-D scan: part of the measurement, and
    dropping it would lose the only record of when each point was taken."""
    axis = Axis("point_time", np.array([1.0, 2.0, 3.0]), unit="s", kind="time")
    ds = Dataset(
        (
            DataArray("trace", np.array([4.0, 5.0, 6.0]), unit="counts"),
            DataArray("point_time", axis.values, unit="s", axes=(axis,)),
        ),
        RunMeta(run_uid="t"),
    )
    ds.to_hdf5(tmp_path / "timed.h5")
    back = Dataset.from_hdf5(tmp_path / "timed.h5")

    assert "point_time" in back.arrays
    assert np.allclose(back.arrays["point_time"].values, [1.0, 2.0, 3.0])


def test_an_open_group_can_be_read_directly(tmp_path):
    _scan().to_hdf5(tmp_path / "scan.h5")
    with h5py.File(tmp_path / "scan.h5", "r") as f:
        back = Dataset.from_hdf5(f)
    assert "counts" in back.arrays


# --- Both file layouts ------------------------------------------------------


@pytest.mark.anyio
async def test_a_run_saved_by_the_store_reads_back(tmp_path):
    """`RunStore` nests the dataset under a `run` group with the format
    version at the root; `to_hdf5(path)` writes at the root. Both are
    files this project produces, so both have to open."""
    store = RunStore(root=tmp_path / "data")
    path = await store.save(_scan())
    assert path is not None

    back = Dataset.from_hdf5(path)
    assert back.meta.run_uid == "abc123"
    assert dict(back.meta.params)["POINTS"] == 21
    assert [axis.name for axis in back.arrays["counts"].axes] == ["x", "y"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- xarray -----------------------------------------------------------------


def test_coordinates_become_real_xarray_coordinates(tmp_path):
    """The whole point: selection by value rather than by index."""
    pytest.importorskip("xarray")
    ds = Dataset.from_hdf5(_written(tmp_path))
    array = ds.to_xarray()

    assert set(array.coords) == {"x", "y"}
    assert float(array.counts.sel(x=0.5, y=0.0, method="nearest")) == pytest.approx(6.0)


def test_a_reduction_is_labelled(tmp_path):
    pytest.importorskip("xarray")
    averaged = Dataset.from_hdf5(_written(tmp_path)).to_xarray().counts.mean(dim="y")

    assert averaged.dims == ("x",)
    assert np.allclose(averaged.values, [1.0, 4.0, 7.0, 10.0, 13.0])


def test_units_travel_with_the_arrays(tmp_path):
    pytest.importorskip("xarray")
    array = Dataset.from_hdf5(_written(tmp_path)).to_xarray()

    assert array.counts.attrs["units"] == "counts"
    assert array.x.attrs["units"] == "mm"
    assert array.x.attrs["device"] == "stage"


def test_the_provenance_travels_too(tmp_path):
    """So a plot made from it can say which sample it is of."""
    pytest.importorskip("xarray")
    attrs = Dataset.from_hdf5(_written(tmp_path)).to_xarray().attrs

    assert attrs["run_uid"] == "abc123"
    assert attrs["context/sample"] == "NV-3"
    assert attrs["params/POINTS"] == 21


def test_an_array_whose_trailing_shape_is_undeclared_still_converts():
    """A detector returning more dimensions than its schema named should
    cost that array its coordinates, not the whole conversion."""
    pytest.importorskip("xarray")
    axis = Axis("x", np.arange(3.0), unit="mm")
    ds = Dataset(
        (DataArray("frames", np.zeros((3, 4, 5)), unit="counts", axes=(axis,)),),
        RunMeta(run_uid="u"),
    )
    array = ds.to_xarray()

    assert array.frames.dims == ("x", "frames_dim1", "frames_dim2")
    assert "x" in array.coords


def test_a_coordinate_is_not_also_a_variable(tmp_path):
    pytest.importorskip("xarray")
    array = Dataset.from_hdf5(_written(tmp_path)).to_xarray()

    assert set(array.data_vars) == {"counts"}


def _written(tmp_path):
    path = tmp_path / "scan.h5"
    _scan(width=5, height=3).to_hdf5(path)
    return path


# --- Through the console, against a real server -----------------------------
#
# The point of these: a run is only useful if the path from "it finished"
# to "here are its numbers" works end to end. Until `from_hdf5` existed
# the last step was missing, so `lp.runs` listed files nothing could open.


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A console session against a real in-process server, with its data
    directory inside the test's own tmp_path."""
    from fastapi.testclient import TestClient

    from labpilot.core.notebook_api import LabPilotSession
    from labpilot.core.server import create_app

    monkeypatch.setenv("LABPILOT_HOME", str(tmp_path))
    with TestClient(create_app()) as http:
        session = LabPilotSession(base_url="http://testserver")
        session.client._client = http
        yield session


def _save_one(lab, dataset: Dataset) -> str:
    """Put a run on disk the way a finished run gets there.

    `RunStore()` with no root reads `LABPILOT_HOME`, which the `lab`
    fixture has pointed at the test's own directory — so this writes
    where the server will look for it.
    """
    import anyio

    anyio.run(RunStore().save, dataset)
    return dataset.meta.run_uid


def test_a_saved_run_is_listed_and_openable_by_id(lab, tmp_path):
    """The whole path: it finished, it is indexed, and its numbers come
    back. The middle step existed and the last one did not."""
    uid = _save_one(lab, _scan())

    listed = lab.runs
    assert any(row["run_uid"] == uid for row in listed)

    ds = lab.open(uid)
    assert ds.arrays["counts"].values.shape == (4, 3)
    assert dict(ds.meta.context)["sample"] == "NV-3"


def test_a_run_can_be_opened_by_path_too(lab, tmp_path):
    """A file someone sent you is the other half of the same job."""
    _scan().to_hdf5(tmp_path / "from_a_colleague.h5")
    ds = lab.open(str(tmp_path / "from_a_colleague.h5"))
    assert ds.meta.plan_name == "scan"


def test_a_run_id_is_never_mistaken_for_a_path(lab):
    """Ids are opaque strings and some of them would be plausible
    filenames; the file has to exist, or carry a known extension."""
    _save_one(lab, _scan())
    with pytest.raises(Exception, match=r"No saved run|404"):
        lab.open("not-a-real-run-id")


def test_the_handle_and_the_session_agree(lab):
    uid = _save_one(lab, _scan())
    assert lab.run(uid).dataset().meta.run_uid == lab.open(uid).meta.run_uid


def test_a_run_record_says_where_its_file_is(lab):
    """`/state` and `/result` describe a run in flight; this is the
    finished one on disk, and the only thing that says where it went."""
    uid = _save_one(lab, _scan())
    record = lab.client.get_run_record(uid)

    assert record["run_uid"] == uid
    assert record["data_path"].endswith(".h5")
    assert record["plan_name"] == "scan"


def test_an_unknown_run_is_a_404_not_an_empty_dataset(lab):
    with pytest.raises(Exception, match=r"No saved run|404"):
        lab.client.get_run_record("00000000-0000-0000-0000-000000000000")
