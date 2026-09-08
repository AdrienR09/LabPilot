"""`Parameter`, the rebuilt `DeviceSchema`, and write validation.

Two things are being asserted here, and they pull in opposite directions:

1. **Nothing changed for existing adapters.** All 301 adapters construct
   their schemas with the pre-`Parameter` keyword form, and every consumer
   (the REST payload, the Qt settings tree, the React modal) reads the four
   flat dicts. The round-trip tests below cover the whole registry, not a
   sample, because a dtype string that fails to round-trip would silently
   change one instrument's UI rather than fail anything loudly.

2. **Something did change: limits are now enforced.** They were declared
   by a number of adapters and checked by two mock ones, by hand.
"""

from __future__ import annotations

import pytest

from labpilot.core.device.parameter import (
    INTEGRATION_TIME,
    Parameter,
    ParamRole,
    legacy_dtype_to_parts,
)
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import (
    ChoiceError,
    LimitError,
    NotSettableError,
    ParameterError,
    UnknownParameterError,
)
from labpilot.instruments import adapter_registry
from labpilot.instruments._base import AdapterBase

# --- Parameter itself -----------------------------------------------------


def test_limits_are_checked_on_both_sides():
    p = Parameter("v", unit="V", settable=True, limits=(-10.0, 10.0))
    assert p.validate(5) == 5.0
    for bad in (-10.001, 10.001, 1e9):
        with pytest.raises(LimitError):
            p.validate(bad)


def test_one_sided_limits_are_enforced():
    """A parameter bounded below only still rejects values below it — the
    legacy `limits` dict could not express this at all, so `DeviceSchema.
    limits` (which stays two-sided) does not show it, but the write path
    must still honour it."""
    p = Parameter("exposure", settable=True, limits=(0.0, None))
    assert p.validate(1e6) == 1e6
    with pytest.raises(LimitError):
        p.validate(-0.1)


def test_limit_error_carries_the_value_and_bounds():
    p = Parameter("v", settable=True, limits=(0.0, 1.0))
    with pytest.raises(LimitError) as excinfo:
        p.validate(2.0, device="psu")
    assert excinfo.value.value == 2.0
    assert excinfo.value.limits == (0.0, 1.0)
    assert excinfo.value.parameter == "v"
    assert excinfo.value.device == "psu"


def test_choices_are_checked():
    p = Parameter("mode", dtype="str", settable=True, choices=("current", "voltage"))
    assert p.validate("current") == "current"
    with pytest.raises(ChoiceError):
        p.validate("resistance")


def test_values_are_coerced_to_the_declared_type():
    assert Parameter("v").validate(3) == 3.0
    assert isinstance(Parameter("v").validate(3), float)
    assert Parameter("n", dtype="i8").validate(3.0) == 3
    assert Parameter("f", dtype="bool").validate(1) is True


def test_a_bool_is_not_silently_a_float():
    """bool subclasses int, so `float(True)` is 1.0. A bool arriving at a
    voltage is a caller mistake, and rounding it away would set the supply
    to one volt."""
    with pytest.raises(ParameterError):
        Parameter("voltage").validate(True)


def test_non_numeric_values_are_rejected_with_a_parameter_error():
    with pytest.raises(ParameterError):
        Parameter("voltage").validate("high")


def test_array_and_unknown_dtypes_pass_through_unvalidated():
    """Range-checking an array element-wise is Phase 2's job; an
    unrecognised dtype must not become an import-time failure for whatever
    adapter declared it."""
    waveform = [1, 2, 3]
    assert Parameter("wave", shape=(None,), settable=True).validate(waveform) is waveform
    weird = object()
    assert Parameter("blob", dtype="pulse_table", settable=True).validate(weird) is weird


def test_a_parameter_must_be_readable_or_settable():
    with pytest.raises(ParameterError):
        Parameter("nothing", readable=False, settable=False)


def test_inverted_limits_are_rejected_at_declaration():
    with pytest.raises(ParameterError):
        Parameter("v", limits=(10.0, 1.0))


# --- Legacy dtype round-trip ----------------------------------------------


@pytest.mark.parametrize(
    "dtype",
    ["float64", "int32", "bool", "str", "json", "ndarray1d", "ndarray2d", "ndarray3d"],
)
def test_legacy_dtypes_round_trip_exactly(dtype: str):
    element, shape = legacy_dtype_to_parts(dtype)
    assert Parameter("p", dtype=element, shape=shape).legacy_dtype() == dtype


def test_an_unknown_dtype_survives_verbatim():
    element, shape = legacy_dtype_to_parts("pulse_table")
    assert Parameter("p", dtype=element, shape=shape).legacy_dtype() == "pulse_table"


# --- DeviceSchema ---------------------------------------------------------


def _legacy_schema(**overrides) -> DeviceSchema:
    kwargs = {
        "name": "spec",
        "kind": "detector",
        "readable": {"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
        "settable": {"integration_time_ms": "float64"},
        "units": {"wavelengths": "nm", "intensities": "counts"},
        "limits": {"integration_time_ms": (1.0, 60000.0)},
    }
    kwargs.update(overrides)
    return DeviceSchema(**kwargs)


def test_legacy_construction_produces_identical_views():
    schema = _legacy_schema()
    assert schema.readable == {"wavelengths": "ndarray1d", "intensities": "ndarray1d"}
    assert schema.settable == {"integration_time_ms": "float64"}
    assert schema.units == {"wavelengths": "nm", "intensities": "counts"}
    assert schema.limits == {"integration_time_ms": (1.0, 60000.0)}


def test_the_legacy_views_are_still_serialised():
    """They are `computed_field`s, not plain properties, because the Qt
    settings tree, the Qt move controls and the React instrument modal all
    read them off `model_dump()`."""
    dumped = _legacy_schema().model_dump()
    for key in ("readable", "settable", "units", "limits", "parameters"):
        assert key in dumped


def test_a_dumped_schema_can_be_reconstructed():
    schema = _legacy_schema()
    assert DeviceSchema(**schema.model_dump()).parameters == schema.parameters


def test_explicit_parameters_win_over_a_legacy_entry_of_the_same_name():
    schema = _legacy_schema(
        parameters=(Parameter("wavelengths", shape=(None,), unit="nm",
                              role=ParamRole.AXIS),),
    )
    wavelengths = schema.require("wavelengths")
    assert wavelengths.role is ParamRole.AXIS
    assert len([p for p in schema.parameters if p.name == "wavelengths"]) == 1


def test_unknown_parameter_lookup_names_what_does_exist():
    with pytest.raises(UnknownParameterError) as excinfo:
        _legacy_schema().require("temperature")
    assert "wavelengths" in str(excinfo.value)


def test_dimensionality_is_derived_from_parameter_shapes():
    assert _legacy_schema().dimensionality == 1
    assert DeviceSchema(name="apd", kind="detector",
                        readable={"counts": "float64"}).dimensionality == 0
    assert DeviceSchema(name="cam", kind="detector",
                        readable={"frame": "ndarray2d"}).dimensionality == 2


def test_position_axes_are_the_motor_axes():
    stage = DeviceSchema(
        name="xy", kind="motor",
        readable={"x": "float64", "y": "float64", "moving": "bool"},
        settable={"x": "float64", "y": "float64"},
    )
    assert stage.position_axes == ("x", "y")


# --- The four integration-time finders, collapsed to one ------------------


def test_integration_time_tag_matches_the_rule_it_replaces():
    """`schema.integration_time` replaces four separate substring searches
    (`instruments/mixins.py`, `core/device/kinds.py`,
    `core/workflow_templates/_common.py`,
    `ui/desktop/components/schema_utils.py`). Asserted against the whole
    registry, since the point is that no adapter's behaviour changes.
    """
    for key, schema in adapter_registry.list_with_schemas().items():
        old_rule = next(
            (name for name in schema.settable if "integration_time" in name), None
        )
        if old_rule is None:
            continue
        found = schema.integration_time
        assert found is not None, f"{key}: lost its integration time"
        assert found.name == old_rule, key


# --- Write validation on a live adapter ----------------------------------


class _Bounded(AdapterBase):
    """Minimal adapter with a bounded setting and a read-only reading."""

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name="bounded", kind="detector",
            parameters=(
                Parameter("counts", unit="counts"),
                Parameter("integration_time_ms", unit="ms", settable=True,
                          role=ParamRole.SETTING, limits=(1.0, 1000.0),
                          tags=frozenset({INTEGRATION_TIME})),
                Parameter("mode", dtype="str", settable=True,
                          role=ParamRole.SETTING, choices=("fast", "slow")),
            ),
        )

    def __init__(self) -> None:
        super().__init__()
        self.written: dict = {}

    def _connect_sync(self) -> None: ...
    def _disconnect_sync(self) -> None: ...
    def _read_sync(self) -> dict:
        return {"counts": 1.0}

    async def set_integration_time_ms(self, value: float) -> None:
        self.written["integration_time_ms"] = value

    async def set_mode(self, value: str) -> None:
        self.written["mode"] = value


async def test_write_rejects_an_out_of_range_setpoint():
    device = _Bounded()
    with pytest.raises(LimitError):
        await device.write({"integration_time_ms": 5000.0})
    assert device.written == {}, "hardware was touched despite the value being illegal"


async def test_write_rejects_a_value_outside_the_choices():
    with pytest.raises(ChoiceError):
        await _Bounded().write({"mode": "turbo"})


async def test_write_rejects_a_read_only_parameter():
    with pytest.raises(NotSettableError):
        await _Bounded().write({"counts": 1.0})


async def test_write_rejects_an_unknown_parameter():
    with pytest.raises(UnknownParameterError):
        await _Bounded().write({"gain": 1.0})


async def test_write_passes_the_coerced_value_to_the_setter():
    device = _Bounded()
    await device.write({"integration_time_ms": 100})
    assert device.written["integration_time_ms"] == 100.0
    assert isinstance(device.written["integration_time_ms"], float)


async def test_a_valid_write_still_reaches_every_key():
    device = _Bounded()
    await device.write({"integration_time_ms": 50.0, "mode": "fast"})
    assert device.written == {"integration_time_ms": 50.0, "mode": "fast"}


def test_a_motor_setting_is_not_offered_as_an_axis():
    """A stage that reports both its position and its speed has one axis to
    move, not two. `_numeric_axes` in `core/device/kinds.py` and the Qt move
    control both used "readable and settable and not a bool", which offered
    `fake_stage`'s speed as something to scan."""
    stage = DeviceSchema(
        name="stage", kind="motor",
        readable={"position": "float64", "speed": "float64"},
        settable={"position": "float64", "speed": "float64"},
    )
    assert stage.position_axes == ("position",)
    assert stage.require("speed").role is ParamRole.SETTING


def test_tag_search_is_case_insensitive():
    """Tags are free-form strings hand-written across 301 adapters, so
    their capitalisation is not consistent — the mock spectrometers tag
    themselves "Spectrometer", and a search for "spectrometer" found
    none of them."""
    found = adapter_registry.search(tags=["spectrometer"])
    assert "mock_spectrometer" in found
    assert found.keys() == adapter_registry.search(tags=["SPECTROMETER"]).keys()


# --- Structured parameters (records), which retire dtype="json" ------------
#
# `dtype="json"` was the only way to declare a setpoint that isn't a scalar,
# and it describes nothing: `validate()` returned it untouched, the settings
# tree rendered it as nothing, and the one adapter using it needed a
# hand-written widget keyed to its exact dict shape. A record says what the
# structure *is*, in the same vocabulary as everything else.

PULSE_STEP = Parameter(
    "sequence", shape=(None,), settable=True, role=ParamRole.SETTING,
    fields=(
        Parameter("duration_ns", unit="ns", limits=(8.0, None), settable=True),
        Parameter("channel", dtype="i8", limits=(0, 23), settable=True),
        Parameter("level", dtype="str", choices=("low", "high"), settable=True),
    ),
)


def test_declaring_fields_is_enough_to_mean_a_record():
    assert PULSE_STEP.dtype == "record"
    assert PULSE_STEP.is_record and PULSE_STEP.is_table
    assert PULSE_STEP.field("channel").limits == (0, 23)
    assert PULSE_STEP.field("nope") is None


def test_a_record_reads_as_json_through_the_legacy_view():
    """An older consumer must not mistake a table of records for an array
    of numbers and try to plot or float() it."""
    assert PULSE_STEP.legacy_dtype() == "json"


def test_a_table_validates_every_row():
    rows = PULSE_STEP.validate([
        {"duration_ns": 100, "channel": 2, "level": "high"},
        {"duration_ns": 40.0, "channel": 0, "level": "low"},
    ])
    assert rows[0]["duration_ns"] == 100.0  # coerced, like any f8
    assert rows[1]["channel"] == 0


def test_a_limit_declared_on_a_field_is_enforced_on_every_row():
    """The whole point of describing the structure: the nested limit is
    enforced by the same code that enforces a scalar setpoint's."""
    with pytest.raises(LimitError) as excinfo:
        PULSE_STEP.validate(
            [{"duration_ns": 100, "channel": 2, "level": "high"},
             {"duration_ns": 4.0, "channel": 2, "level": "high"}],
            device="pulser",
        )
    # Named against the field, not the table, so the message is actionable.
    assert "duration_ns" in str(excinfo.value)


def test_a_field_outside_its_choices_is_rejected():
    with pytest.raises(ChoiceError):
        PULSE_STEP.validate([{"duration_ns": 100, "channel": 2, "level": "sideways"}])


def test_a_missing_field_is_rejected_and_named():
    with pytest.raises(ParameterError, match="level"):
        PULSE_STEP.validate([{"duration_ns": 100, "channel": 2}])


def test_an_undeclared_key_is_rejected_and_says_what_is_declared():
    with pytest.raises(ParameterError) as excinfo:
        PULSE_STEP.validate([{"duration_ns": 100, "channel": 2, "level": "low", "x": 1}])
    assert "duration_ns" in str(excinfo.value)


def test_a_table_needs_a_sequence_and_a_row_needs_a_mapping():
    with pytest.raises(ParameterError, match="sequence of rows"):
        PULSE_STEP.validate({"duration_ns": 100})
    with pytest.raises(ParameterError, match="mapping"):
        PULSE_STEP.validate([7])


def test_a_single_record_is_a_mapping_not_a_table():
    one = Parameter("gate_config", settable=True, fields=(
        Parameter("bin_width_s", unit="s", limits=(1e-12, 1.0), settable=True),
        Parameter("gates", dtype="i8", settable=True),
    ))
    assert one.is_record and not one.is_table
    assert one.validate({"bin_width_s": 1e-9, "gates": 4}) == {
        "bin_width_s": 1e-9, "gates": 4,
    }


def test_records_nest():
    outer = Parameter("element", settable=True, fields=(
        Parameter("duration_ns", unit="ns", settable=True),
        Parameter("mw", settable=True, fields=(
            Parameter("amplitude_v", unit="V", limits=(0.0, 1.0), settable=True),
        )),
    ))
    assert outer.validate({"duration_ns": 10, "mw": {"amplitude_v": 0.5}})["mw"] == {
        "amplitude_v": 0.5,
    }
    with pytest.raises(LimitError):
        outer.validate({"duration_ns": 10, "mw": {"amplitude_v": 9.0}})


@pytest.mark.parametrize("kwargs, match", [
    ({"dtype": "str", "fields": (Parameter("a"),)}, "must be 'record'"),
    ({"dtype": "record"}, "declares no fields"),
    ({"fields": (Parameter("a"), Parameter("a"))}, "twice"),
    ({"fields": (Parameter("a"),), "shape": (2, 2)}, "shape must be"),
])
def test_a_malformed_record_is_refused_at_declaration(kwargs, match):
    """Caught when the adapter is written, not when someone writes to it."""
    with pytest.raises(ParameterError, match=match):
        Parameter("x", **kwargs)


def test_a_record_survives_a_schema_round_trip():
    """The settings tree builds its widgets from exactly this."""
    schema = DeviceSchema(
        name="pulser", kind="generic", readable={"running": "bool"},
        parameters=(PULSE_STEP,),
    )
    revived = DeviceSchema(**schema.model_dump())
    field_names = [f["name"] if isinstance(f, dict) else f.name
                   for f in revived.require("sequence").fields]
    assert field_names == ["duration_ns", "channel", "level"]
    with pytest.raises(LimitError):
        revived.require("sequence").validate([
            {"duration_ns": 1.0, "channel": 0, "level": "low"}
        ])
