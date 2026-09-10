"""One Ocean Optics adapter: the model table, and what follows from it.

The same claim as `test_ni_card.py`, for a different family of hardware:
choosing the model is a *setting*, and everything up to `connect()` works
with no driver and no spectrometer — which is where acquisition settings
actually get chosen.

The numbers in `models.toml` are transcribed from python-seabreeze's own
per-model classes (MIT), so what is pinned here is the transcription and
the behaviour that follows: a QE Pro's 8 ms exposure floor, a USB2000's
12-bit full scale, and the fact that the connected device outranks the
table.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import numpy as np
import pytest

from labpilot.core.device.parameter import INTEGRATION_TIME, ParamRole
from labpilot.core.errors import LimitError
from labpilot.instruments import adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG
from labpilot.instruments.connections import CONNECTION_METHODS
from labpilot.instruments.mock.ocean_optics import MockOceanOptics
from labpilot.instruments.OceanOptics.models import (
    find_model,
    load_models,
    model_names,
    normalise_name,
)
from labpilot.instruments.OceanOptics.spectrometer import OceanOpticsAdapter, boxcar

pytestmark = pytest.mark.anyio

PACKAGED = Path("src/labpilot/instruments/OceanOptics/models.toml")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- The model table ---------------------------------------------------------


def test_the_table_covers_the_models_a_lab_is_likely_to_own():
    models = load_models()
    for name in ("USB2000+", "Flame-S", "QE Pro", "HR4000", "Maya2000 Pro", "Ocean HDX"):
        assert find_model(name).label == name
    assert len(models) > 25


def test_a_model_answers_to_the_name_people_type_and_the_one_it_reports():
    """seabreeze reports `QEPRO`; nobody says that out loud."""
    for spelling in ("QEPRO", "QE Pro", "qe-pro", "QEPro"):
        assert find_model(spelling).model == "QEPRO"


def test_a_plus_is_not_punctuation():
    """`USB2000` and `USB2000+` are genuinely different instruments with
    different ADCs, so the normaliser must not fold them together."""
    assert normalise_name("USB2000+") != normalise_name("USB2000")
    assert find_model("USB2000").max_counts == 4095
    assert find_model("USB2000+").max_counts == 65535


def test_the_seabreeze_numbers_are_transcribed_exactly():
    """Spot-checks against `seabreeze/pyseabreeze/devices.py`. If one of
    these ever fails, the table was edited from memory."""
    qepro = find_model("QE Pro")
    assert (qepro.pixels, qepro.max_counts) == (1044, 2**18 - 1)
    assert (qepro.integration_min_us, qepro.integration_max_us) == (8000, 1600000000)

    hr4000 = find_model("HR4000")
    assert (hr4000.pixels, hr4000.max_counts) == (3840, 16383)
    assert hr4000.integration_min_us == 10

    assert find_model("Ocean ST").pixels == 1516
    assert find_model("NIRQuest256").pixels == 256


def test_exposure_limits_are_in_the_unit_the_schema_uses():
    """Ocean's API is microseconds; every other detector here is
    `integration_time_ms`, and one of the two has to give."""
    assert find_model("QE Pro").integration_ms == (8.0, 1_600_000.0)
    assert find_model("USB2000+").integration_ms == (1.0, 655_350.0)


def test_only_the_cooled_models_are_marked_cooled():
    assert find_model("QE Pro").cooled is True
    assert find_model("NIRQuest512").cooled is True
    assert find_model("USB2000+").cooled is False


def test_dark_pixels_expand_to_indices():
    assert find_model("USB2000+").dark_indices()[:3] == (6, 7, 8)
    assert len(find_model("QE Pro").dark_indices()) == 8


def test_an_unknown_model_says_where_to_add_it():
    with pytest.raises(KeyError, match=re.escape("ocean_models.toml")):
        find_model("Nonesuch 9000")


def test_a_user_file_adds_a_model_without_losing_the_packaged_ones(tmp_path):
    user = tmp_path / "ocean_models.toml"
    user.write_text(
        '[[spectrometer]]\nmodel = "SR8"\nlabel = "Ocean SR8"\npixels = 4096\n'
        "max_counts = 65535\nintegration_min_us = 10\nintegration_max_us = 1000000\n"
    )
    models = load_models(user=user, refresh=True)
    assert any(m.label == "Ocean SR8" for m in models.values())
    assert any(m.label == "QE Pro" for m in models.values())


def test_a_user_file_can_correct_one_field(tmp_path):
    user = tmp_path / "ocean_models.toml"
    user.write_text('[[spectrometer]]\nmodel = "QEPRO"\nintegration_min_us = 6000\n')

    corrected = find_model("QE Pro", load_models(user=user, refresh=True))
    assert corrected.integration_min_us == 6000
    assert corrected.pixels == 1044  # everything else survives
    load_models(refresh=True)  # don't leak the override into later tests


def test_the_packaged_file_names_every_entry_once():
    with open(PACKAGED, "rb") as f:
        table = tomllib.load(f)
    names = [entry["model"] for entry in table["spectrometer"]]
    assert len(names) == len(set(names))
    assert all(entry.get("pixels") for entry in table["spectrometer"])


def test_every_model_offers_a_usable_exposure_window():
    for model in load_models().values():
        low, high = model.integration_ms
        assert 0 < low < high, model.label


# --- What a configured spectrometer presents ---------------------------------


def test_the_spectrum_carries_its_own_wavelength_axis():
    """The fact that makes a plot, an HDF5 file and a workflow all know the
    x-scale without being told."""
    schema = MockOceanOptics(model="USB2000+").schema
    wavelengths = schema.require("wavelengths")
    intensities = schema.require("intensities")

    assert wavelengths.role is ParamRole.AXIS
    assert wavelengths.unit == "nm"
    assert intensities.axes == ("wavelengths",)
    assert intensities.shape == (2048,)


def test_the_exposure_is_tagged_so_a_caller_can_find_it_by_meaning():
    schema = MockOceanOptics(model="Flame-S").schema
    assert schema.integration_time.name == "integration_time_ms"
    assert INTEGRATION_TIME in schema.integration_time.tags


def test_the_models_limits_reach_the_parameter():
    assert MockOceanOptics(model="QE Pro").schema.limits["integration_time_ms"] == (
        8.0, 1_600_000.0
    )
    assert MockOceanOptics(model="USB2000+").schema.limits["integration_time_ms"] == (
        1.0, 655_350.0
    )


def test_a_cooler_appears_only_on_a_cooled_model():
    assert "tec_setpoint_c" in MockOceanOptics(model="QE Pro").schema.settable
    assert "tec_setpoint_c" not in MockOceanOptics(model="USB2000+").schema.settable


def test_an_exposure_the_model_cannot_hold_is_refused_by_name(anyio_backend):
    """A QE Pro cannot integrate for 1 ms. Being told that on a laptop is
    the whole point of naming the model in the settings."""
    spectrometer = MockOceanOptics(model="QE Pro")
    with pytest.raises(LimitError, match=re.escape("8.0")):
        spectrometer.validate_write({"integration_time_ms": 1.0})


def test_asking_what_it_would_really_do_is_a_separate_question():
    """`validate` raises; `quantise` reports — the split
    `core/device/constraints.py` exists for. A caller that wants "as fast
    as this goes" asks the second one."""
    fastest, why = MockOceanOptics(model="QE Pro").quantise_exposure(1.0)
    assert fastest == 8.0
    assert "clipped to minimum" in why


def test_the_real_adapter_describes_itself_with_no_driver_installed():
    schema = OceanOpticsAdapter.describe()
    assert schema is not None
    assert "spectrometer" in schema.tags
    assert "wavelengths" in schema.readable


def test_an_unnamed_model_still_gives_a_usable_schema():
    """"Ask the device" is a legitimate configuration, and it must not
    produce an instrument with no parameters."""
    schema = OceanOpticsAdapter(model="").schema
    assert schema.require("intensities").shape == (None,)
    assert schema.limits.get("integration_time_ms") in (None, (None, None))


# --- Processing --------------------------------------------------------------


def test_boxcar_smooths_the_middle_and_leaves_the_edges_alone():
    """Averaging the ends against pixels that do not exist bends every
    spectrum inward, which looks like a real feature at the edge of a
    detector's range."""
    spikes = np.zeros(21)
    spikes[10] = 10.0
    smoothed = boxcar(spikes, 2)

    assert smoothed[10] == pytest.approx(2.0)
    assert smoothed[0] == spikes[0]
    assert smoothed[-1] == spikes[-1]


def test_boxcar_zero_is_off():
    values = np.array([1.0, 5.0, 1.0])
    assert boxcar(values, 0) is values


# --- The simulated spectrometer ----------------------------------------------


async def test_the_mock_has_the_models_real_detector():
    spectrometer = MockOceanOptics(model="QE Pro")
    await spectrometer.connect()
    reading = (await spectrometer.read()).as_dict()

    assert len(reading["intensities"]) == 1044
    assert len(reading["wavelengths"]) == 1044
    assert reading["wavelengths"][0] < reading["wavelengths"][-1]


async def test_a_long_exposure_saturates_and_says_so():
    """A pixel at full scale carries no information, and a fit through a
    flat-topped peak is confidently wrong."""
    spectrometer = MockOceanOptics(model="USB2000+", integration_time_ms=10.0)
    await spectrometer.connect()
    assert (await spectrometer.read()).as_dict()["saturated"] is False

    await spectrometer.write({"integration_time_ms": 5000.0})
    reading = (await spectrometer.read()).as_dict()
    assert reading["saturated"] is True
    assert max(reading["intensities"]) == pytest.approx(65535, rel=1e-6)


async def test_averaging_reduces_the_noise_it_costs_time_to_reduce():
    single = MockOceanOptics(model="USB2000+", scans_to_average=1)
    many = MockOceanOptics(model="USB2000+", scans_to_average=16)
    await single.connect()
    await many.connect()

    def baseline(reading):
        # Past the last simulated line, where the spectrum is flat and its
        # spread is noise rather than structure.
        return float(np.asarray(reading["intensities"])[1900:2040].std())

    noisy = baseline((await single.read()).as_dict())
    quiet = baseline((await many.read()).as_dict())
    assert quiet < noisy


async def test_the_reading_says_which_instrument_produced_it():
    spectrometer = MockOceanOptics(model="Flame-S", serial_number="FLMS12345")
    await spectrometer.connect()
    reading = (await spectrometer.read()).as_dict()

    assert reading["model"] == "Flame-S"
    assert reading["serial_number"] == "FLMS12345"


async def test_a_cooled_model_reports_its_detector_temperature():
    spectrometer = MockOceanOptics(model="QE Pro")
    await spectrometer.connect()
    await spectrometer.write({"tec_setpoint_c": -20.0})
    reading = (await spectrometer.read()).as_dict()

    assert reading["tec_setpoint_c"] == -20.0
    assert reading["tec_temperature_c"] == pytest.approx(-20.0, abs=1.0)


async def test_the_mock_and_the_real_adapter_present_the_same_instrument():
    real = OceanOpticsAdapter(model="QE Pro", name="s")
    mock = MockOceanOptics(model="QE Pro", name="s")
    assert real.schema.settable == mock.schema.settable
    assert real.schema.limits == mock.schema.limits


# --- Registration ------------------------------------------------------------


def test_both_are_registered_and_catalogued():
    for key in ("ocean_optics", "mock_ocean_optics"):
        assert key in adapter_registry.list()
        assert any(e.adapter_key == key for e in INSTRUMENT_CATALOG), key


def test_the_connect_form_asks_for_the_unit_and_the_model():
    fields = {f.name for f in CONNECTION_METHODS["ocean_optics"].fields}
    assert fields == {"serial_number", "model"}

    entry = next(e for e in INSTRUMENT_CATALOG if e.adapter_key == "ocean_optics")
    assert entry.connection_types == ["ocean_optics"]


def test_the_dropdown_lists_the_names_people_recognise():
    names = model_names()
    assert "QE Pro" in names
    assert "USB2000+" in names
    assert "QEPRO" not in names  # the reported name, not the catalogue one
