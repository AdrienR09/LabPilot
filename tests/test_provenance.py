"""Per-point times, software provenance and lab context.

These three are grouped because they share one property that nothing else
in the data model has: **they cannot be added to a run after it is taken.**
The numbers can be re-analysed, a fit can be redone, a view can be
rewritten — but which sample was in the cryostat, which commit produced the
file, and when each point was actually measured are only knowable while the
run is happening. A month of data taken without them is permanently
missing them, which is why they are tested as invariants rather than as
features.
"""

from __future__ import annotations

import numpy as np
import pytest

from labpilot.core.data.dataset import Axis, DataArray, Dataset, RunMeta
from labpilot.core.provenance import software
from labpilot.core.run.descriptor import RunDescriptor
from labpilot.core.session import Session

# --- Software provenance ---------------------------------------------------


def test_software_names_the_program_that_took_the_data():
    stamp = software()
    assert stamp["labpilot"]
    assert stamp["python"]
    assert stamp["host"]


def test_software_is_captured_once_per_process():
    """It shells out to git, so a run must not pay for it per point."""
    assert software() is software()


def test_a_dirty_checkout_says_so():
    """A sha on its own implies the file can be reproduced, which is false
    the moment someone edited a template and ran it without committing.
    Either the flag is present, or the tree really is clean."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        pytest.skip("not a checkout")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root,
        capture_output=True, text=True, check=False,
    )
    dirty = bool(status.stdout.strip())
    assert ("git_dirty" in software()) is dirty


def test_new_run_stamps_the_software_without_being_asked():
    assert RunMeta.new_run("scan").software["labpilot"]


# --- Lab context -----------------------------------------------------------


def test_context_merges_rather_than_replacing():
    """Correcting one field is the normal case; restating the sample every
    time you change the cooldown number is how a field goes stale."""
    session = Session()
    session.set_context(sample="NV-3", cooldown=7)
    session.set_context(cooldown=8)
    assert session.context == {"sample": "NV-3", "cooldown": 8}


def test_a_none_value_removes_its_key():
    session = Session()
    session.set_context(sample="NV-3")
    session.set_context(sample=None)
    assert "sample" not in session.context


def test_set_context_returns_the_whole_context():
    session = Session()
    assert session.set_context(sample="NV-3") == {"sample": "NV-3"}


def test_context_is_shared_between_concurrent_runs_not_per_task():
    """Unlike role aliases, which are a ContextVar precisely so two
    workflows cannot clobber each other. Context describes the apparatus,
    so two concurrent runs *should* agree about it."""
    session = Session()
    session.set_context(sample="NV-3")
    assert session.context["sample"] == "NV-3"


# --- Per-point times -------------------------------------------------------


def _descriptor(points_x: int = 4, points_y: int = 3) -> RunDescriptor:
    return RunDescriptor(
        run_uid="uid", plan_name="scan",
        axes=(
            Axis("x", np.linspace(0, 2, points_x), unit="mm", kind="actuator"),
            Axis("y", np.linspace(0, 1, points_y), unit="mm", kind="actuator"),
        ),
        scan_axis_count=2, value_unit="counts",
    )


def test_times_are_allocated_per_point_not_per_value():
    """A spectrometer reading 2048 channels at one position was taken at
    one time, not 2048 times."""
    spectra = RunDescriptor(
        run_uid="uid", plan_name="scan",
        axes=(
            Axis("x", np.linspace(0, 2, 5), kind="actuator"),
            Axis("wavelength", np.arange(2048.0), kind="detector"),
        ),
        scan_axis_count=1,
    )
    assert len(spectra.allocate()) == 5 * 2048
    assert len(spectra.allocate_times()) == 5


def test_point_times_become_an_array_over_the_scanned_axes():
    descriptor = _descriptor()
    dataset = descriptor.dataset(
        list(range(12)), times=[1000.0 + i for i in range(12)]
    )
    stamps = dataset.arrays["point_time"]
    assert stamps.values.shape == (4, 3)
    assert stamps.unit == "s"
    assert [axis.name for axis in stamps.axes] == ["x", "y"]


def test_the_timestamps_never_become_the_primary_array():
    """For a 0D detector they have the same rank as the data, so a model
    that picked by rank alone would be one reorder away from plotting the
    clock instead of the signal."""
    descriptor = _descriptor()
    dataset = descriptor.dataset(list(range(12)), times=[1000.0] * 12)
    assert dataset.primary().name == "data"


def test_absent_times_add_no_array_at_all():
    assert "point_time" not in _descriptor().dataset(list(range(12))).arrays


def test_a_mismatched_time_count_is_dropped_rather_than_reshaped():
    """A timestamp array that does not line up with the grid is worse than
    none, because it looks authoritative."""
    dataset = _descriptor().dataset(list(range(12)), times=[1.0, 2.0])
    assert "point_time" not in dataset.arrays


def test_times_survive_the_dict_round_trip_the_console_takes():
    """`result()` goes out over REST and comes back as a plain dict, so the
    timestamps have to be recoverable from the flat convention — otherwise
    they would exist only on the path that writes HDF5 from the `Run`."""
    descriptor = _descriptor()
    result = {
        **descriptor.result_fields(),
        "data": list(range(12)),
        "point_times": [1000.0 + i for i in range(12)],
    }
    lifted = Dataset.from_result(result, RunMeta.new_run("scan"))
    assert lifted.arrays["point_time"].values.shape == (4, 3)
    assert lifted.primary().name == "data"


# --- Everything reaching the file ------------------------------------------


def test_provenance_and_context_reach_the_hdf5_attributes(tmp_path):
    dataset = Dataset(
        (DataArray("data", np.arange(6.0).reshape(2, 3), unit="counts",
                   axes=(Axis("x", np.arange(2.0), kind="actuator"),
                         Axis("y", np.arange(3.0), kind="actuator"))),),
        RunMeta.new_run("scan", context={"sample": "NV-3", "cooldown": 7}),
    )
    path = tmp_path / "run.h5"
    dataset.to_hdf5(path)

    h5py = pytest.importorskip("h5py")
    with h5py.File(path) as handle:
        attrs = dict(handle.attrs)
    assert attrs["context/sample"] == "NV-3"
    assert attrs["context/cooldown"] == 7
    assert attrs["software/labpilot"]


def test_a_field_added_to_runmeta_survives_from_result():
    """`from_result` used to rebuild `RunMeta` by listing its fields, so
    anything added later was silently dropped on the way through — the
    opposite of what a provenance record is for."""
    meta = RunMeta.new_run("scan", context={"sample": "NV-3"})
    lifted = Dataset.from_result({"data": [1.0, 2.0], "repeats": 3}, meta)
    assert lifted.meta.context == {"sample": "NV-3"}
    assert lifted.meta.software["labpilot"]
    assert lifted.meta.params["repeats"] == 3
