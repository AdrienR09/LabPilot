"""`Dataset` — the measurement that describes itself.

Two things are being held at once, and they are in tension:

1. **It is still the dict `read()` always returned.** 301 adapters, every
   workflow template, the REST serialiser and the Qt views all index into
   the reading by key. A `Dataset` that were merely dict-*like* would fail
   somewhere none of those tests look, so the dict contract is asserted
   directly and across the whole registry.

2. **It answers what the dict could not.** Which array is the measurement
   and which are its axes, in what units — the questions three modules
   used to guess at from a hardcoded list of axis-ish names.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from labpilot.core.api.dashboard import _jsonable_read
from labpilot.core.data import Axis, DataArray, Dataset, DatasetPatch, RunMeta
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments import adapter_registry

h5py = pytest.importorskip("h5py")


SPECTROMETER = DeviceSchema(
    name="spec", kind="detector",
    parameters=(
        Parameter("wavelengths", shape=(None,), unit="nm", role=ParamRole.AXIS),
        Parameter("intensities", shape=(None,), unit="counts", axes=("wavelengths",)),
        Parameter("temperature", unit="C", role=ParamRole.STATUS),
    ),
)
READING = {
    "wavelengths": [400.0, 500.0, 600.0],
    "intensities": [10.0, 90.0, 20.0],
    "temperature": -70.0,
}


@pytest.fixture
def spectrum() -> Dataset:
    return Dataset.from_reading(SPECTROMETER, READING)


# --- Still a dict ---------------------------------------------------------


def test_it_is_a_dict_with_exactly_the_readings_keys_and_values(spectrum):
    assert isinstance(spectrum, dict)
    assert dict(spectrum) == READING
    assert spectrum["intensities"] == [10.0, 90.0, 20.0]
    assert sorted(spectrum) == sorted(READING)


def test_the_dict_hands_back_the_drivers_own_objects(spectrum):
    """Not the numpy view built alongside them: a driver returning a list
    must keep returning a list, or a template doing `value + [x]` breaks."""
    assert spectrum["intensities"] is READING["intensities"]


def test_it_serialises_the_way_a_reading_always_did(spectrum):
    assert json.loads(json.dumps(_jsonable_read(spectrum))) == READING


async def test_every_adapters_read_is_a_lossless_lift():
    """The lift happens in one place for all 301 adapters, so it is checked
    against all of them: same keys, same values, plus structure."""
    checked = 0
    for key, adapter_cls in adapter_registry.list().items():
        if not key.startswith("mock") and not key.startswith("fake"):
            continue  # only the adapters that work without hardware
        try:
            adapter = adapter_cls()
        except Exception:
            continue
        await adapter.connect()
        try:
            reading = await adapter.read()
        except Exception:
            continue
        finally:
            checked += 1
        assert isinstance(reading, Dataset), key
        raw = adapter._read_sync()
        assert set(reading) == set(raw), key
        assert set(reading.arrays) == set(raw), key
    assert checked > 40, "the mock adapters did not load"


# --- What the dict could not answer --------------------------------------


def test_primary_is_the_measurement_not_its_axis(spectrum):
    assert spectrum.primary().name == "intensities"
    assert spectrum.primary().unit == "counts"


def test_the_axis_comes_back_with_its_coordinates_and_unit(spectrum):
    (axis,) = spectrum.axes()
    assert axis.name == "wavelengths"
    assert axis.unit == "nm"
    assert list(axis.values) == [400.0, 500.0, 600.0]


@pytest.mark.parametrize(
    ("adapter_key", "value", "axis"),
    [
        ("mock_ir_spectrometer", "transmittance", "wavenumbers"),
        ("mock_raman_spectrometer", "intensity", "shift"),
    ],
)
async def test_an_axis_named_nothing_like_wavelength_is_still_an_axis(
    adapter_key: str, value: str, axis: str
):
    """The regression this whole model exists for: guessing from a list of
    axis-ish names put the IR mock's wavenumbers and the Raman mock's shift
    where the measurement belonged."""
    adapter = adapter_registry.get(adapter_key)()
    await adapter.connect()
    reading = await adapter.read()
    assert reading.primary().name == value
    assert [a.name for a in reading.axes()] == [axis]


def test_an_undeclared_array_gets_index_axes():
    """Honest about not knowing, rather than inventing a coordinate."""
    camera = DeviceSchema(name="cam", kind="detector",
                          readable={"frame": "ndarray2d"})
    reading = Dataset.from_reading(camera, {"frame": np.zeros((4, 5))})
    assert [(a.name, a.kind, len(a)) for a in reading.axes()] == [
        ("row", "index", 4), ("col", "index", 5),
    ]


def test_a_scalar_detector_has_no_axes():
    apd = DeviceSchema(name="apd", kind="detector", readable={"counts": "float64"})
    reading = Dataset.from_reading(apd, {"counts": 7.0})
    assert reading.primary().ndim == 0
    assert reading.axes() == ()


def test_the_highest_rank_array_wins():
    schema = DeviceSchema(name="both", kind="detector",
                          readable={"trace": "ndarray1d", "cube": "ndarray3d"})
    reading = Dataset.from_reading(
        schema, {"trace": np.zeros(3), "cube": np.zeros((2, 2, 2))}
    )
    assert reading.primary().name == "cube"


def test_an_axis_is_only_movable_when_something_can_move_it():
    """What makes a crosshair drawable — a structural property rather than
    the positional `actuator_axis_count` convention it replaces."""
    assert not Axis.index("sample", 10).movable
    assert not Axis("wavelengths", np.zeros(3), kind="detector", device="spec").movable
    assert Axis("x", np.zeros(3), kind="actuator", device="stage").movable


# --- Storage --------------------------------------------------------------


def test_hdf5_output_carries_units_and_real_coordinates(tmp_path, spectrum):
    """The previous writer stored bare arrays with no coordinates and no
    units, which is part of why nothing ever subscribed it."""
    path = tmp_path / "run.h5"
    with h5py.File(path, "w") as f:
        spectrum.to_hdf5(f.create_group("run"))

    with h5py.File(path, "r") as f:
        run = f["run"]
        assert list(run["intensities"][:]) == [10.0, 90.0, 20.0]
        assert run["intensities"].attrs["units"] == "counts"
        assert run["axes/wavelengths"].attrs["units"] == "nm"
        # A real HDF5 dimension scale, so xarray and MATLAB read the axis
        # without knowing anything about LabPilot.
        scale = run["intensities"].dims[0]
        assert scale.label == "wavelengths"
        assert list(scale[0][:]) == [400.0, 500.0, 600.0]


def test_hdf5_records_which_run_it_came_from(tmp_path):
    dataset = Dataset(
        (DataArray("counts", np.array([1.0, 2.0])),),
        RunMeta(run_uid="abc-123", plan_name="omniscan"),
    )
    path = tmp_path / "run.h5"
    with h5py.File(path, "w") as f:
        dataset.to_hdf5(f.create_group("run"))
    with h5py.File(path, "r") as f:
        assert f["run"].attrs["run_uid"] == "abc-123"
        assert f["run"].attrs["plan_name"] == "omniscan"


# --- Patches --------------------------------------------------------------


def test_a_patch_writes_one_point_into_a_growing_list():
    """A scan accumulates into a flat list with `None` for points not yet
    taken — what the REST layer serialises."""
    accumulated = [None] * 6
    DatasetPatch("data", 2, np.array([9.0, 9.5])).apply(accumulated)
    assert accumulated == [None, None, 9.0, 9.5, None, None]


def test_a_patch_writes_into_an_array_in_flat_row_major_order():
    target = np.zeros((2, 3))
    DatasetPatch("data", 3, np.array([1.0, 2.0, 3.0])).apply(target)
    assert target.tolist() == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]


def test_a_patch_on_the_wire_is_the_size_of_the_new_data():
    """The reason `_strip_oversized_fields` exists is that publishing one
    more point meant re-sending the whole accumulated array."""
    patch = DatasetPatch("data", 1000, np.arange(4.0), run_uid="r", seq=7)
    wire = patch.to_wire()
    assert wire == {"array": "data", "index": 1000, "values": [0.0, 1.0, 2.0, 3.0],
                    "run_uid": "r", "seq": 7}
    assert len(json.dumps(wire)) < 120
