"""ODMR: averaging as a dimension, and a swept parameter that is declared.

Two things this template used to do by hand, and one it used to guess.

By hand: its own loop, its own buffer, its own progress counters, and its
own accumulation matrix. All four are now `ScanPlan(repeats=...)`, which
is why the file lost sixty lines without losing a feature.

Guessed: which of the source's settables to sweep. It took the first one
whose name did not contain "power" — a source with a settable phase or
modulation depth silently gets that wrong, and the failure is a plausible
plot rather than an error. A source now declares it with the `FREQUENCY`
tag, and the workflow can be told explicitly instead.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import labpilot.core.workflow_templates as templates
from labpilot.core.run import ScanAxis, ScanPlan
from labpilot.core.run.run import Run
from labpilot.core.run.script import run_script
from labpilot.core.session import Session
from labpilot.instruments import adapter_registry

pytestmark = pytest.mark.anyio

ODMR = Path(templates.__path__[0]) / "odmr_sweep.py"
SOURCE = "mock_microwave_source"
DETECTOR = "mock_basic_detector_0d"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def rig(source: str = SOURCE) -> Session:
    session = Session()
    for role, key in (("source", source), ("detector", DETECTOR)):
        adapter = adapter_registry.get(key)()
        await adapter.connect()
        session.register(adapter, role)
    return session


async def sweep(**params):
    return await run_script(await rig(), ODMR, {"SWEEP_POINTS": 7, "AVERAGES": 3, **params})


# --- A source declares which parameter is which -----------------------------


async def test_the_swept_parameter_is_found_by_its_tag():
    """Not by "the first settable that is not called power" — this source
    has six settables, four of them scan-mode configuration."""
    schema = (await rig()).get("source").schema
    assert len(schema.settable) > 2
    assert schema.frequency.name == "cw_frequency"
    assert schema.frequency.unit == "Hz"
    assert schema.power.name == "cw_power"


async def test_the_sweep_uses_the_tagged_parameter_and_its_unit():
    result = await sweep()
    assert result["swept_parameter"] == "cw_frequency"
    assert result["power_parameter"] == "cw_power"
    assert result["axis_units"]["cw_frequency"] == "Hz"


async def test_the_power_is_parked_once_rather_than_swept():
    """It is `hold`, which is what `hold` is for — a parameter of the
    swept device that this run is not sweeping."""
    session = await rig()
    await run_script(session, ODMR, {"SWEEP_POINTS": 5, "AVERAGES": 1,
                                     "SWEEP_POWER": -22.0})
    assert (await session.get("source").read())["power"] == pytest.approx(-22.0)


async def test_an_untagged_source_says_which_parameter_to_name():
    """Rather than sweeping whichever settable happens to sort first. The
    message has to name the override, because the alternative is reading
    the template's source to find out it exists."""
    with pytest.raises(KeyError, match="SWEEP_PARAMETER"):
        await run_script(
            await rig("mock_basic_source"), ODMR, {"SWEEP_POINTS": 3}
        )


async def test_an_untagged_source_can_be_told_explicitly():
    """An override, not a guess — and it is the same one line whether the
    adapter is one of this repo's or someone else's."""
    session = await rig("mock_basic_source")
    result = await run_script(
        session, ODMR,
        {
            "SWEEP_POINTS": 5, "AVERAGES": 1,
            "SWEEP_START": 0.0, "SWEEP_STOP": 5.0,
            "SWEEP_PARAMETER": "output", "POWER_PARAMETER": "",
        },
    )
    assert result["swept_parameter"] == "output"
    assert result["power_parameter"] == ""


async def test_naming_a_parameter_the_source_does_not_have_lists_the_ones_it_does():
    with pytest.raises(KeyError, match="cw_frequency"):
        await sweep(SWEEP_PARAMETER="wavelength")


# --- Averaging is a dimension ----------------------------------------------


async def test_every_pass_is_kept_not_only_their_mean():
    """Qudi's accumulation matrix, and the reason it exists: a drifting
    resonance and a noisy one look identical once averaged."""
    result = await sweep(SWEEP_POINTS=7, AVERAGES=3)

    assert result["shape"] == [3, 7]
    assert result["axis_names"] == ["repeat", "cw_frequency"]
    assert len(result["matrix"]) == 3
    assert all(len(row) == 7 for row in result["matrix"])
    assert result["repeats_done"] == 3


async def test_the_averaged_trace_is_the_mean_of_the_passes():
    result = await sweep(SWEEP_POINTS=6, AVERAGES=4)
    matrix = np.asarray(result["matrix"], dtype=float)
    assert result["counts"] == pytest.approx(matrix.mean(axis=0))


async def test_a_single_pass_needs_no_repeat_axis():
    """`repeats=1` is the ordinary scan, unchanged — nothing existing
    grows a dimension it did not have."""
    result = await sweep(AVERAGES=1)
    assert result["shape"] == [7]
    assert result["axis_names"] == ["cw_frequency"]


async def test_the_run_streams_and_counts_every_point_of_every_pass():
    result = await sweep(SWEEP_POINTS=5, AVERAGES=3)
    assert result["total"] == 15
    assert result["completed"] == 15


async def test_the_fit_runs_on_the_averaged_trace():
    result = await sweep(SWEEP_POINTS=21, AVERAGES=2)
    assert set(result) >= {"fit", "fit_curve_x", "fit_curve_y", "fit_center"}
    if result["fit"] is not None:
        assert len(result["fit_curve_x"]) == len(result["fit_curve_y"]) == 200


# --- `repeats` on the plan itself -------------------------------------------


async def test_a_pass_is_a_whole_grid_not_a_point_read_twice():
    """They are different measurements, and only the first averages away
    drift. So the repeat axis varies slowest."""
    session = await rig()
    plan = ScanPlan(
        [ScanAxis("cw_frequency", "source", 2.85e9, 2.87e9, 4)],
        detector="detector", repeats=3,
    )
    descriptor = await plan.describe(session)
    seen: list[float] = []
    async for patch in plan.points(session, descriptor):
        seen.append(float(patch.index))

    assert descriptor.shape == (3, 4)
    assert seen == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]


async def test_nothing_is_written_for_the_repeat_axis():
    """It is time, not position — so `repeat` never reaches a device, and
    a source with no parameter of that name is not asked for one."""
    session = await rig()
    plan = ScanPlan(
        [ScanAxis("cw_frequency", "source", 2.85e9, 2.87e9, 3)],
        detector="detector", repeats=2,
    )
    descriptor = await plan.describe(session)
    await Run(descriptor, session).execute(plan.points(session, descriptor))
    assert (await session.get("source").read())["frequency"] == pytest.approx(2.87e9)


async def test_with_repeats_no_axis_is_movable():
    """A crosshair on a `(repeat, x)` image cannot say which pass it
    points at, so no view offers one."""
    plan = ScanPlan(
        [ScanAxis("cw_frequency", "source", 2.85e9, 2.87e9, 3)],
        detector="detector", repeats=4,
    )
    descriptor = await plan.describe(await rig())
    assert descriptor.actuator_axis_count == 0
    assert descriptor.axes[0].movable is False
    assert descriptor.axes[1].movable is True


async def test_repeats_below_one_is_read_as_one():
    """A scan that runs zero times is a misconfiguration, not a request."""
    plan = ScanPlan(
        [ScanAxis("cw_frequency", "source", 2.85e9, 2.87e9, 3)],
        detector="detector", repeats=0,
    )
    descriptor = await plan.describe(await rig())
    assert descriptor.shape == (3,)


# --- What the result view reads ---------------------------------------------


async def test_every_key_the_result_view_names_is_produced():
    """A typo here renders a blank panel with no error anywhere."""
    from labpilot.core.workflow.instrument_roles import read_result_ui

    result = await sweep(AVERAGES=2)
    declared = {
        value for key, value in read_result_ui(ODMR.read_text()).items()
        if key.endswith("_key")
    }
    assert declared <= set(result)


async def test_the_result_is_json_serialisable_for_the_wire():
    import json

    json.dumps(await sweep(AVERAGES=2))


async def test_the_source_output_is_switched_on_and_off_again():
    """A sweep against a source whose RF output is off measures a flat
    line, and `hold` cannot switch it on — on a real source the output is
    an action, not a settable. Nothing used to call it.

    Off again afterwards, so neither a finished nor an aborted run leaves
    the RF on with nobody watching.
    """
    session = await rig()
    source = session.get("source")
    assert not source._adapter._output_on

    await run_script(session, ODMR, {"SWEEP_POINTS": 5, "AVERAGES": 1})

    assert not source._adapter._output_on
    assert source._adapter._mode == "cw"


class _NoActions(adapter_registry.get(SOURCE)):  # type: ignore[misc]
    """The same source with nothing declared in `actions` — a real source
    that has no on/off concept at all, which several do."""

    @property
    def schema(self):
        return super().schema.model_copy(update={"actions": ()})


async def test_a_source_with_no_output_action_still_sweeps():
    """`cw_on` is looked for in the source's declared actions, so a source
    without one is not broken by the attempt to switch it on."""
    session = Session()
    for role, adapter in (("source", _NoActions()), ("detector", adapter_registry.get(DETECTOR)())):
        await adapter.connect()
        session.register(adapter, role)

    result = await run_script(session, ODMR, {"SWEEP_POINTS": 4, "AVERAGES": 1})
    assert len(result["sweep_values"]) == 4
