"""The sequence editor is a workflow that binds nothing.

Authoring is offline; execution is online. The editor writes a file and
the pulsed measurement plays it, and they are separate workflows so that
sequences can be designed away from the lab — no instruments, no
connection, no risk.

That benefit only holds if the editor genuinely depends on nothing, which
is not something a comment can guarantee. So the first test here runs it
against a session with no instruments at all: if the editor ever grows a
hardware dependency, this is where it shows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import labpilot.core.workflow_templates as templates
from labpilot.core.pulse import PulseSequence, list_sequences, load_sequence
from labpilot.core.run.script import run_script
from labpilot.core.session import Session
from labpilot.core.workflow.instrument_roles import (
    read_required_instruments,
    read_result_ui,
)

pytestmark = pytest.mark.anyio

EDITOR = Path(templates.__path__[0]) / "pulse_sequence_editor.py"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def sequences(tmp_path, monkeypatch):
    """A throwaway ~/.labpilot, so the editor's saves stay in this test."""
    monkeypatch.setenv("LABPILOT_HOME", str(tmp_path))
    return tmp_path / "sequences"


async def edit(**params):
    """Run the editor with no instruments whatsoever."""
    return await run_script(Session(), EDITOR, params)


# --- Free-standing ---------------------------------------------------------


def test_the_editor_declares_no_instruments():
    assert read_required_instruments(EDITOR.read_text()) == {}


async def test_the_editor_runs_with_nothing_connected_and_still_writes_a_file(
    sequences,
):
    """The check that the free-standing claim is real rather than
    incidental. A session with no devices is what a laptop on a train is."""
    result = await edit()

    saved = sequences / "rabi.json"
    assert saved.exists()
    assert result["path"] == str(saved)
    PulseSequence.from_dict(json.loads(saved.read_text())).validate()


async def test_what_it_writes_is_the_abstract_sequence_not_a_device_format(
    sequences,
):
    """A free-standing editor cannot emit a device's format because it does
    not know the device: sample rate, granularity, minimum element length
    and activation sets all belong to whichever pulser plays it."""
    await edit()
    written = json.loads((sequences / "rabi.json").read_text())

    assert "blocks" in written and "sweep" in written
    text = json.dumps(written)
    for device_word in ("sample_rate", "d_ch", "a_ch", "granularity", "samples"):
        assert device_word not in text


async def test_channels_are_symbolic_so_the_file_is_not_tied_to_one_rig(sequences):
    await edit()
    assert load_sequence("rabi").channels == {"laser", "mw", "gate"}


# --- Generating ------------------------------------------------------------


@pytest.mark.parametrize(
    ("generator", "params", "points"),
    [
        ("rabi", {"points": 12}, 12),
        ("ramsey", {"points": 10}, 10),
        ("hahn_echo", {"points": 8}, 8),
        ("t1", {"points": 6}, 6),
    ],
)
async def test_every_generator_can_be_authored_and_saved(
    generator, params, points, sequences
):
    result = await edit(
        GENERATOR=generator, SEQUENCE_NAME=generator, GENERATOR_PARAMS=params
    )
    assert result["points"] == points
    assert load_sequence(generator).validate() is None


async def test_the_saved_name_is_the_parameter_not_the_generator(sequences):
    """So two variants of one experiment are two files, not a new
    template — the same consolidation that turned four scanners into
    presets."""
    await edit(SEQUENCE_NAME="rabi_sample_b", GENERATOR_PARAMS={"points": 5})
    assert (sequences / "rabi_sample_b.json").exists()
    assert load_sequence("rabi_sample_b").name == "rabi_sample_b"


async def test_the_rig_profile_is_physics_and_reaches_the_sequence(sequences):
    """Rabi period, laser length and delay are properties of the
    experiment, not of any driver, which is why they are editable with
    nothing plugged in."""
    await edit(
        RABI_PERIOD=400e-9, GENERATOR="ramsey", SEQUENCE_NAME="ramsey",
        GENERATOR_PARAMS={"points": 4},
    )
    elements = load_sequence("ramsey").blocks[0].elements
    pulses = [e.duration for e in elements if "mw" in e.channels and e.duration]
    assert pulses[0] == pytest.approx(100e-9)  # a quarter of the Rabi period


async def test_a_digital_rig_needs_only_a_flag(sequences):
    """A PulseBlaster gating an external source rather than an AWG
    synthesising the drive — the sequences are otherwise identical."""
    await edit(ANALOG_MW=False, GENERATOR_PARAMS={"points": 4})
    element = load_sequence("rabi").blocks[0].elements[0]
    assert element.channels["mw"] is True


async def test_an_ungated_rig_counts_laser_pulses_as_readouts(sequences):
    result = await edit(GATE_CHANNEL=None, GENERATOR_PARAMS={"points": 7})
    assert result["readouts"] == 7
    assert load_sequence("rabi").readout_channel == "laser"


async def test_an_unplayable_sequence_is_refused_before_it_becomes_a_file(
    sequences,
):
    """Caught here rather than by the hardware an hour later."""
    from labpilot.core.errors import LimitError

    with pytest.raises(LimitError):
        await edit(GENERATOR_PARAMS={"points": 0})
    assert list_sequences(sequences) == []


async def test_a_misspelled_generator_lists_the_real_ones(sequences):
    from labpilot.core.pulse import SequenceError

    with pytest.raises(SequenceError, match="hahn_echo"):
        await edit(GENERATOR="hahnecho")


# --- The result view -------------------------------------------------------


async def test_the_result_carries_a_timing_diagram_of_one_point(sequences):
    """One shot, not the whole sweep: a 50-point Rabi drawn at once is a
    solid block, and boxes rather than samples because a 2.87 GHz carrier
    in a 100 ns pulse cannot be drawn any other way."""
    result = await edit(GENERATOR="ramsey", GENERATOR_PARAMS={"points": 20})

    segments = result["segments"]
    assert segments
    assert {s["channel"] for s in segments} == {"laser", "mw", "gate"}
    assert all(s["stop"] > s["start"] for s in segments)
    assert max(s["stop"] for s in segments) == pytest.approx(result["point_duration"])


async def test_a_later_point_of_the_sweep_is_longer_than_the_first(sequences):
    """What the preview control is for — seeing the sequence at the end of
    the sweep, where an element may have grown past what the pulser holds."""
    first = await edit(GENERATOR_PARAMS={"points": 30}, PREVIEW_POINT=0)
    last = await edit(GENERATOR_PARAMS={"points": 30}, PREVIEW_POINT=29)
    assert last["point_duration"] > first["point_duration"]


async def test_asking_for_a_point_that_does_not_exist_says_how_many_there_are(
    sequences,
):
    from labpilot.core.pulse import SamplingError

    with pytest.raises(SamplingError, match="5 point"):
        await edit(GENERATOR_PARAMS={"points": 5}, PREVIEW_POINT=99)


async def test_the_result_is_json_serialisable_for_the_wire(sequences):
    """It crosses REST and a WebSocket to reach the workflow window."""
    json.dumps(await edit(GENERATOR_PARAMS={"points": 5}))


async def test_every_key_the_result_view_names_is_produced(sequences):
    """The same invariant the smoke harness applies to every template — a
    typo here renders a blank panel with no error anywhere."""
    result = await edit(GENERATOR_PARAMS={"points": 5})
    declared = {
        value for key, value in read_result_ui(EDITOR.read_text()).items()
        if key.endswith("_key")
    }
    assert declared <= set(result)


async def test_the_sweep_is_reported_so_a_measurement_knows_its_axis(sequences):
    result = await edit(
        GENERATOR_PARAMS={"tau_start": 20e-9, "tau_step": 20e-9, "points": 10}
    )
    assert result["sweep"]["name"] == "tau"
    assert result["sweep"]["unit"] == "s"
    assert result["sweep"]["stop"] == pytest.approx(200e-9)
