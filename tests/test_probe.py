"""`labpilot probe` — the command that makes an adapter stop being theoretical.

308 adapters declare a `DeviceSchema` and almost none of those
declarations has ever met the hardware it describes; they were written
from manuals. So the probe's job is to disagree out loud, and these tests
are mostly about an adapter that *lies*: declares a parameter it never
returns, declares a scalar and returns an array, declares a travel range
narrower than the position it reports.

The other half of the contract is what the probe must not do. It is
pointed at stages with samples under an objective, so `test_a_probe_moves_
nothing` is the test that keeps it safe to run.
"""

from __future__ import annotations

import argparse
from typing import Any

import numpy as np
import pytest

from labpilot.core.data.dataset import Dataset
from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.probe import (
    CANNOT_TELL,
    DISAGREES,
    OK,
    compare_reading,
    compare_schemas,
    describe_schema,
    probe,
)
from labpilot.instruments._base import AdapterBase, adapter_registry

TRUTHFUL = DeviceSchema(
    name="truthful",
    kind="detector",
    parameters=(
        Parameter("wavelengths", shape=(None,), unit="nm", role=ParamRole.AXIS),
        Parameter("intensities", shape=(None,), unit="counts", axes=("wavelengths",)),
    ),
)


def _reading(schema: DeviceSchema, **values: Any) -> Dataset:
    return Dataset.from_reading(schema, values)


# --- Comparing a reading with the declaration ------------------------------


def test_a_schema_the_hardware_honours_produces_nothing():
    dataset = _reading(
        TRUTHFUL, wavelengths=np.arange(4.0), intensities=np.ones(4)
    )
    assert compare_reading(TRUTHFUL, dataset) == []


def test_a_declared_parameter_that_never_comes_back_is_fatal():
    """Every consumer that trusts the schema breaks on this one: the view
    picker, the HDF5 writer's axis attachment, a plan preallocating a grid."""
    dataset = _reading(TRUTHFUL, wavelengths=np.arange(4.0))
    (finding,) = compare_reading(TRUTHFUL, dataset)
    assert finding.fatal
    assert "intensities" in finding.text


def test_a_parameter_returned_but_not_declared_is_only_worth_knowing():
    dataset = _reading(
        TRUTHFUL,
        wavelengths=np.arange(4.0),
        intensities=np.ones(4),
        board_temperature=31.5,
    )
    (finding,) = compare_reading(TRUTHFUL, dataset)
    assert not finding.fatal
    assert "board_temperature" in finding.text


def test_a_scalar_that_reads_as_an_array_is_fatal():
    schema = DeviceSchema(
        name="liar", kind="detector", parameters=(Parameter("value", unit="V"),)
    )
    (finding,) = compare_reading(schema, _reading(schema, value=np.ones(8)))
    assert finding.fatal
    assert "declared a scalar, read a 1-D array (8,)" in finding.text


def test_an_array_that_reads_as_a_scalar_is_fatal():
    schema = DeviceSchema(
        name="liar",
        kind="detector",
        parameters=(Parameter("trace", shape=(None,), unit="V"),),
    )
    (finding,) = compare_reading(schema, _reading(schema, trace=1.0))
    assert "declared a 1-D array, read a scalar ()" in finding.text


def test_a_pinned_length_that_does_not_match_is_fatal():
    """`(2048,)` is a promise about the detector, not a hint — a camera
    delivering 1024 pixels means the shipped model table is wrong."""
    schema = DeviceSchema(
        name="camera",
        kind="detector",
        parameters=(Parameter("spectrum", shape=(2048,), unit="counts"),),
    )
    (finding,) = compare_reading(schema, _reading(schema, spectrum=np.ones(1024)))
    assert "axis 0: 2048 declared, 1024 read" in finding.text


def test_an_unknown_length_accepts_whatever_came_back():
    schema = DeviceSchema(
        name="camera",
        kind="detector",
        parameters=(Parameter("spectrum", shape=(None,), unit="counts"),),
    )
    assert compare_reading(schema, _reading(schema, spectrum=np.ones(37))) == []


def test_a_reading_outside_its_own_declared_limits_is_fatal():
    """`validate_write` enforces exactly these numbers, so a stage that
    reports 12.4 mm while its schema ends the travel at 10 will refuse a
    legal move."""
    schema = DeviceSchema(
        name="stage",
        kind="motor",
        parameters=(
            Parameter("x", unit="mm", role=ParamRole.POSITION, limits=(-10.0, 10.0)),
        ),
    )
    (finding,) = compare_reading(schema, _reading(schema, x=12.4))
    assert "above the declared 10" in finding.text


def test_a_one_sided_limit_only_checks_the_side_it_has():
    schema = DeviceSchema(
        name="counter",
        kind="counter",
        parameters=(Parameter("counts", unit="cps", limits=(0.0, None)),),
    )
    assert compare_reading(schema, _reading(schema, counts=1e9)) == []
    assert compare_reading(schema, _reading(schema, counts=-1.0))


def test_a_non_numeric_reading_is_not_forced_through_float():
    """`model` and `serial_number` are declared readable on half the real
    adapters here, and they are strings."""
    schema = DeviceSchema(
        name="spectrometer",
        kind="detector",
        parameters=(Parameter("model", dtype="str", role=ParamRole.STATUS),),
    )
    assert compare_reading(schema, _reading(schema, model="USB2000+")) == []


def test_an_axis_a_parameter_names_but_does_not_return_is_fatal():
    dataset = _reading(TRUTHFUL, intensities=np.ones(4))
    texts = [f.text for f in compare_reading(TRUTHFUL, dataset) if f.fatal]
    assert any("indexed by 'wavelengths'" in text for text in texts)


# --- Comparing the schema before and after connecting ----------------------


def test_an_unchanged_schema_produces_nothing():
    assert compare_schemas(TRUTHFUL, TRUTHFUL) == []


def test_a_parameter_that_vanishes_on_connect_is_fatal():
    """Anything built from the offline description — the catalogue, tag
    search, an auto-generated settings window — breaks on this."""
    thinner = DeviceSchema(
        name="truthful",
        kind="detector",
        parameters=(
            Parameter("wavelengths", shape=(None,), unit="nm", role=ParamRole.AXIS),
        ),
    )
    (finding,) = compare_schemas(TRUTHFUL, thinner)
    assert finding.fatal
    assert "gone once connected" in finding.text


def test_a_parameter_learned_on_connect_is_only_worth_knowing():
    """An adapter that fills in its real pixel count once the device
    answers is doing the right thing, not failing."""
    richer = DeviceSchema(
        name="truthful",
        kind="detector",
        parameters=(*TRUTHFUL.parameters, Parameter("board_temperature", unit="C")),
    )
    (finding,) = compare_schemas(TRUTHFUL, richer)
    assert not finding.fatal


def test_a_refined_length_is_reported_without_being_a_fault():
    refined = DeviceSchema(
        name="truthful",
        kind="detector",
        parameters=(
            Parameter("wavelengths", shape=(2048,), unit="nm", role=ParamRole.AXIS),
            Parameter("intensities", shape=(2048,), unit="counts", axes=("wavelengths",)),
        ),
    )
    findings = compare_schemas(TRUTHFUL, refined)
    assert findings and not any(f.fatal for f in findings)
    assert any("(None,) declared, (2048,) live" in f.text for f in findings)


# --- Rendering -------------------------------------------------------------


def test_the_declared_schema_renders_every_parameter():
    text = "\n".join(describe_schema(TRUTHFUL))
    assert "wavelengths" in text and "intensities" in text
    assert "of wavelengths" in text  # the axis relationship, not guessed


@pytest.mark.parametrize(
    ("limits", "shown"),
    [((1.0, 100.0), "[1 … 100]"), ((1.0, None), "≥ 1"), ((None, 10.0), "≤ 10")],
)
def test_a_one_sided_limit_reads_as_one(limits, shown):
    schema = DeviceSchema(
        name="x", kind="detector", parameters=(Parameter("n", limits=limits),)
    )
    assert shown in "\n".join(describe_schema(schema))


# --- End to end, through the command --------------------------------------


class _Lying(AdapterBase):
    """Declares a 1-D trace and a bounded position; returns neither."""

    def __init__(self, resource: str = ""):
        super().__init__()
        self.resource = resource
        self.moved: list[Any] = []

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name="lying",
            kind="detector",
            parameters=(
                Parameter("trace", shape=(16,), unit="counts"),
                Parameter("x", unit="mm", role=ParamRole.POSITION, limits=(0.0, 1.0)),
            ),
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        return {"trace": np.ones(8), "x": 4.0}

    async def write(self, values):  # pragma: no cover - must never be called
        self.moved.append(values)

    async def stage(self) -> None:  # pragma: no cover - must never be called
        self.moved.append("stage")


class _Honest(_Lying):
    def _read_sync(self) -> dict[str, Any]:
        return {"trace": np.ones(16), "x": 0.5}


class _Unreachable(_Lying):
    def _connect_sync(self) -> None:
        raise ConnectionError("no instrument at ''")


@pytest.fixture
def registered():
    """Register the three fakes, and take them out again — the registry is
    process-global and refuses a duplicate key."""
    keys = {"probe_liar": _Lying, "probe_honest": _Honest, "probe_absent": _Unreachable}
    for key, cls in keys.items():
        adapter_registry.register(key, cls)
    yield keys
    for key in keys:
        adapter_registry._registry.pop(key, None)


def _args(adapter_key: str, **overrides) -> argparse.Namespace:
    defaults = {
        "adapter_key": adapter_key,
        "resource": None,
        "param": None,
        "offline": False,
        "no_read": False,
        "json": False,
    }
    return argparse.Namespace(**{**defaults, **overrides})


def test_an_honest_adapter_exits_zero(registered, capsys):
    assert probe(_args("probe_honest")) == OK
    assert "agrees with the declared schema" in capsys.readouterr().out


def test_a_lying_adapter_exits_one_and_says_where(registered, capsys):
    assert probe(_args("probe_liar")) == DISAGREES
    out = capsys.readouterr().out
    assert "axis 0: 16 declared, 8 read" in out
    assert "above the declared 1" in out
    assert "disagreement" in out


def test_an_adapter_that_cannot_be_reached_exits_two(registered, capsys):
    assert probe(_args("probe_absent")) == CANNOT_TELL
    out = capsys.readouterr().out
    assert "ConnectionError" in out
    # The declared schema is printed first, so a failed connect is still a
    # useful run — it is how you review what an adapter claims.
    assert "declared, with no hardware" in out


def test_an_unknown_adapter_suggests_near_misses(capsys):
    assert probe(_args("mock_basic_detector_0")) == CANNOT_TELL
    assert "mock_basic_detector_0d" in capsys.readouterr().out


def test_offline_connects_to_nothing_and_does_not_judge(registered, capsys):
    assert probe(_args("probe_liar", offline=True)) == OK
    out = capsys.readouterr().out
    assert "not tested against hardware" in out
    assert "one reading" not in out


def test_no_read_compares_the_schemas_only(registered, capsys):
    assert probe(_args("probe_liar", no_read=True)) == OK
    assert "one reading" not in capsys.readouterr().out


def test_a_probe_moves_nothing(registered, monkeypatch):
    """The reason this is safe to point at a stage with a sample under the
    objective. `_Lying.write` and `.stage` append to `moved`; nothing on
    the probe's path may reach them."""
    built: list[_Lying] = []
    original = _Lying.__init__

    def record(self, *a, **kw):
        original(self, *a, **kw)
        built.append(self)

    monkeypatch.setattr(_Lying, "__init__", record)
    probe(_args("probe_liar"))
    assert built and all(adapter.moved == [] for adapter in built)


def test_a_probe_disconnects_even_when_it_disagrees(registered, monkeypatch):
    closed: list[bool] = []
    monkeypatch.setattr(_Lying, "_disconnect_sync", lambda self: closed.append(True))
    probe(_args("probe_liar"))
    assert closed == [True]


def test_json_output_is_machine_readable(registered, capsys):
    import json

    probe(_args("probe_liar", json=True))
    report = json.loads(capsys.readouterr().out)
    assert report["agrees"] is False
    assert report["adapter_key"] == "probe_liar"
    assert report["reading"]["x"] == 4.0
    assert any(f["fatal"] for f in report["findings"])


def test_constructor_arguments_are_passed_through(registered, capsys):
    probe(_args("probe_honest", resource="GPIB0::9::INSTR"))
    assert "GPIB0::9::INSTR" in capsys.readouterr().out


def test_a_param_without_an_equals_sign_is_refused(registered, capsys):
    assert probe(_args("probe_honest", param=["resource"])) == CANNOT_TELL
    assert "name=value" in capsys.readouterr().out


def test_a_missing_required_argument_names_what_it_needs(capsys):
    assert probe(_args("keithley_2400")) == CANNOT_TELL
    out = capsys.readouterr().out
    assert "It needs: resource" in out
    assert "--resource" in out
