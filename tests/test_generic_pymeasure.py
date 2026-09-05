"""Schema introspection for the 182 generated PyMeasure adapters.

These adapters are all thin subclasses of `PyMeasureGenericAdapter`, so
everything asserted here holds for every one of them from a single
implementation — which is also why getting it wrong was expensive: the
previous version marked every property settable, because it tested
`attr.fset is not None` and a pymeasure read-only measurement still has a
setter closure (one whose `set_command` is None and which raises
LookupError when called).

Tests are written against pymeasure's own instrument classes rather than
fixtures: the point is that we read *pymeasure's* declarations correctly,
which a fixture would assume rather than check.
"""

from __future__ import annotations

import pytest

pymeasure = pytest.importorskip("pymeasure")

from labpilot.core.device.parameter import ParamRole  # noqa: E402
from labpilot.instruments._generic_pymeasure import (  # noqa: E402
    PyMeasureGenericAdapter,
    introspect_parameters,
)


@pytest.fixture(scope="module")
def sr830():
    from pymeasure.instruments.srs import SR830
    return {p.name: p for p in introspect_parameters(SR830)}


@pytest.fixture(scope="module")
def keithley():
    from pymeasure.instruments.keithley import Keithley2400
    return {p.name: p for p in introspect_parameters(Keithley2400)}


def test_a_read_only_measurement_is_not_advertised_as_settable(sr830):
    """SR830.x is `Instrument.measurement(...)` — reading the lock-in's
    in-phase component. Setting it is meaningless, and the GUI used to
    draw a spin box for it."""
    x = sr830["x"]
    assert x.readable and not x.settable
    assert x.role is ParamRole.VALUE


def test_a_settable_property_keeps_its_declared_range(sr830):
    frequency = sr830["frequency"]
    assert frequency.settable
    assert frequency.limits == (0.001, 102000.0)
    assert frequency.role is ParamRole.SETTING


def test_a_discrete_set_becomes_choices_not_a_range(sr830):
    """SR830's time constant is 20 specific values, not an interval.
    Flattening it to (min, max) would let a UI offer 1.7 s, which the
    instrument silently rounds."""
    time_constant = sr830["time_constant"]
    assert time_constant.limits is None
    assert time_constant.choices is not None
    assert 1e-05 in time_constant.choices and 30000 in time_constant.choices


def test_mapped_string_values_become_string_choices(keithley):
    mode = keithley["source_mode"]
    assert mode.dtype == "str"
    assert set(mode.choices) == {"current", "voltage"}


def test_units_come_from_the_docstring_phrasing_pymeasure_uses(sr830, keithley):
    assert sr830["frequency"].unit == "Hz"
    assert sr830["phase"].unit == "deg"
    assert keithley["source_voltage"].unit == "V"
    assert keithley["compliance_current"].unit == "A"


def test_a_hyphen_before_in_does_not_eat_the_unit(sr830):
    """"...represents the lock-in frequency in Hz" — a hyphen is a word
    boundary, so the naive first-match rule finds "in frequency"."""
    assert sr830["frequency"].unit == "Hz"


def test_an_integer_valued_range_on_a_float_property_stays_a_float(keithley):
    """Keithley2400 declares `values=[-210, 210]` for a voltage. The legal
    values being written as Python ints does not make the property an
    integer one — pymeasure's own `cast` says float."""
    assert keithley["source_voltage"].dtype == "f8"


def test_no_parameter_is_neither_readable_nor_settable(sr830, keithley):
    for parameters in (sr830, keithley):
        for parameter in parameters.values():
            assert parameter.readable or parameter.settable


def test_every_generated_adapter_describes_itself_without_hardware():
    """`list_with_schemas()` used to instantiate with no arguments, so it
    saw 90 of 301 adapters — every VISA instrument needing `resource=`
    disappeared, and `search(tags=)` is built on it."""
    from labpilot.instruments import adapter_registry

    generated = {
        key: cls for key, cls in adapter_registry.list().items()
        if issubclass(cls, PyMeasureGenericAdapter) and key != "pymeasure_generic"
    }
    assert len(generated) > 150, "the generated pymeasure adapters are missing"

    undescribed = [key for key, cls in generated.items() if cls.describe() is None]
    assert undescribed == []


def test_generated_adapters_have_real_limits_or_choices():
    """The whole point of reading pymeasure's descriptors rather than
    `dir()`. Asserted in aggregate because per-instrument counts are
    pymeasure's business, not ours — but "almost none of them" would mean
    the introspection silently stopped working against a new release."""
    from labpilot.instruments import adapter_registry

    constrained = 0
    total = 0
    for key, cls in adapter_registry.list().items():
        if not issubclass(cls, PyMeasureGenericAdapter) or key == "pymeasure_generic":
            continue
        schema = cls.describe()
        if schema is None:
            continue
        for parameter in schema.parameters:
            total += 1
            if parameter.limits is not None or parameter.choices is not None:
                constrained += 1

    assert total > 2000
    assert constrained / total > 0.25, (
        f"only {constrained}/{total} parameters carry limits or choices — "
        "pymeasure's descriptor layout has probably changed"
    )
