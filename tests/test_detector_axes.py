"""Which of a detector's arrays is the axis and which is the measurement.

A 1-D detector typically reports two same-shaped arrays — an x-axis and
the values on it — and nothing in the old schema said which was which.
Three places guessed, from one hardcoded list of axis-ish names:
"wavelength", "time", "frequency", "x". A detector whose axis is called
something else fell through and had its **axis plotted as the
measurement**; the IR mock (`wavenumbers`/`transmittance`) and the Raman
mock (`shift`/`intensity`) both did.

`Parameter(role=AXIS)` is the adapter saying so outright. The name hints
survive as the fallback for adapters that declare nothing, so these tests
cover both paths.
"""

from __future__ import annotations

import pytest

from labpilot.core.device.parameter import Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.workflow_templates._common import detector_axes, spectrum_key
from labpilot.instruments import adapter_registry


@pytest.mark.parametrize(
    ("adapter_key", "value_key", "axis_key"),
    [
        ("mock_ir_spectrometer", "transmittance", "wavenumbers"),
        ("mock_raman_spectrometer", "intensity", "shift"),
        ("mock_spectrometer", "intensities", "wavelengths"),
        ("mock_uv_vis_spectrometer", "absorbance", "wavelengths"),
        ("mock_fluorescence_spectrometer", "fluorescence", "wavelengths"),
    ],
)
async def test_a_declared_axis_is_never_mistaken_for_the_measurement(
    adapter_key: str, value_key: str, axis_key: str
):
    adapter = adapter_registry.get(adapter_key)()
    await adapter.connect()
    try:
        sample = await adapter.read()
        found_value, axis_names, _ = detector_axes(adapter.schema, sample)
        assert found_value == value_key
        assert axis_names == [axis_key]
        assert spectrum_key(adapter) == value_key
    finally:
        await adapter.disconnect()


async def test_a_scope_with_no_axis_array_keeps_sample_index():
    """Four channels are four measurements, not an axis and three values —
    the fallback must not invent an axis where the device has none."""
    adapter = adapter_registry.get("mock_oscilloscope")()
    await adapter.connect()
    try:
        value_key, axis_names, _ = detector_axes(adapter.schema, await adapter.read())
        assert value_key == "ch1"
        assert axis_names == ["sample"]
    finally:
        await adapter.disconnect()


def test_the_name_hints_still_work_for_an_undeclared_schema():
    """A workflow instance saved before roles existed passes the legacy
    `schema.readable` dict, and must keep resolving as it did."""
    legacy = {"wavelengths": "ndarray1d", "intensities": "ndarray1d"}
    sample = {"wavelengths": [1.0, 2.0, 3.0], "intensities": [4.0, 5.0, 6.0]}
    value_key, axis_names, positions = detector_axes(legacy, sample)
    assert value_key == "intensities"
    assert axis_names == ["wavelengths"]
    assert positions == [[1.0, 2.0, 3.0]]


def test_a_declaration_beats_a_misleading_name():
    """The decisive case: a device whose *value* is named like an axis.
    The hint list would pick "time_us" as the axis; the declaration says
    it is the measurement."""
    schema = DeviceSchema(
        name="tdc", kind="detector",
        parameters=(
            Parameter("bin", shape=(None,), role=ParamRole.AXIS),
            Parameter("time_us", shape=(None,), unit="us", axes=("bin",)),
        ),
    )
    sample = {"bin": [0, 1, 2], "time_us": [10.0, 11.0, 12.0]}
    value_key, axis_names, _ = detector_axes(schema, sample)
    assert value_key == "time_us"
    assert axis_names == ["bin"]
