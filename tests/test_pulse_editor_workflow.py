"""The sequence editor is a workflow that binds nothing.

Authoring is offline; execution is online. The editor writes a file and
the pulsed measurement plays it, and they are separate workflows so that
sequences can be designed away from the lab — no instruments, no
connection, no risk.

That benefit only holds if the editor genuinely depends on nothing, which
is not something a comment can guarantee. So the first test here runs it
against a session with no instruments at all: if the editor ever grows a
hardware dependency, this is where it shows.

What the editor holds is a **timeline** — one track per instrument, with
the swept regions marked across them. `START_FROM` draws one of the four
standard experiments onto an empty canvas as a starting point; after that
the timeline is what gets saved, so a hand-moved gate stays moved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import labpilot.core.workflow_templates as templates
from labpilot.core.pulse import PulseSequence, list_sequences, load_sequence
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.tracks import (
    FREQUENCY,
    LOG,
    Pulse,
    Region,
    SweepAxis,
    Timeline,
    Track,
    timeline_from_sequence,
)
from labpilot.core.run.script import run_script
from labpilot.core.session import Session
from labpilot.core.workflow.instrument_roles import (
    read_required_instruments,
    read_result_ui,
)

pytestmark = pytest.mark.anyio

EDITOR = Path(templates.__path__[0]) / "pulse_sequence_editor.py"
CHANNELS = ("laser", "mw", "gate")
NS = 1e-9
US = 1e-6


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


def drawn(name: str, points: int = 8) -> dict:
    """One of the standard experiments, as a timeline parameter."""
    sequence = build(name, RigProfile(), points=points)
    return timeline_from_sequence(sequence, CHANNELS).to_dict()


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


# --- Starting from one of the four ------------------------------------------


@pytest.mark.parametrize("start", ["rabi", "ramsey", "hahn_echo", "t1"])
async def test_an_empty_canvas_draws_the_chosen_experiment(start, sequences):
    """So a freshly loaded workflow has something to run rather than an
    error, and the Fill button has a default."""
    result = await edit(START_FROM=start, SEQUENCE_NAME=start)
    assert result["start_from"] == start
    assert result["points"] > 0
    assert load_sequence(start).validate() is None


async def test_what_is_drawn_wins_over_the_starting_point(sequences):
    """The whole reason it is an editor: a hand-moved gate must survive
    pressing Save, rather than being redrawn from the generator."""
    line = Timeline(
        tracks=[
            Track("laser", [Pulse(0.0, 2 * US)]),
            Track("gate", [Pulse(0.0, 2 * US)]),
        ],
        duration=4 * US,
    )
    result = await edit(
        START_FROM="ramsey", TIMELINE=line.to_dict(), SEQUENCE_NAME="hand"
    )
    assert result["readouts"] == 1
    assert result["duration"] == pytest.approx(4 * US)


async def test_the_saved_name_is_the_parameter_not_the_experiment(sequences):
    """So two variants of one experiment are two files, not a new
    template — the same consolidation that turned four scanners into
    presets."""
    await edit(SEQUENCE_NAME="rabi_sample_b")
    assert (sequences / "rabi_sample_b.json").exists()
    assert load_sequence("rabi_sample_b").name == "rabi_sample_b"


async def test_the_rig_profile_is_physics_and_reaches_the_sequence(sequences):
    """Rabi period, laser length and delay are properties of the
    experiment, not of any driver, which is why they are editable with
    nothing plugged in."""
    await edit(RABI_PERIOD=400e-9, START_FROM="ramsey", SEQUENCE_NAME="ramsey")
    elements = load_sequence("ramsey").blocks[0].elements
    pulses = [e.duration for e in elements if "mw" in e.channels and e.duration]
    assert pulses[0] == pytest.approx(100e-9)  # a quarter of the Rabi period


async def test_a_digital_rig_needs_only_a_flag(sequences):
    """A PulseBlaster gating an external source rather than an AWG
    synthesising the drive — the sequences are otherwise identical."""
    await edit(ANALOG_MW=False)
    element = load_sequence("rabi").blocks[0].elements[0]
    assert element.channels["mw"] is True


async def test_an_ungated_rig_counts_laser_pulses_as_readouts(sequences):
    result = await edit(GATE_CHANNEL=None)
    assert result["readouts"] == result["points"]
    assert load_sequence("rabi").readout_channel == "laser"


async def test_a_misspelled_starting_point_lists_the_real_ones(sequences):
    from labpilot.core.pulse import SequenceError

    with pytest.raises(SequenceError, match="hahn_echo"):
        await edit(START_FROM="hahnecho")


# --- The timeline is the sequence -------------------------------------------


async def test_the_timeline_is_what_gets_compiled(sequences):
    """One track per instrument, edges everywhere anything changes."""
    result = await edit(TIMELINE=drawn("rabi", points=12), SEQUENCE_NAME="rabi")
    assert result["points"] == 12
    assert set(result["channels"].split(", ")) == set(CHANNELS)
    assert result["timeline"]["tracks"]


async def test_the_point_count_comes_from_the_drawn_sweep(sequences):
    """Where a generator parameter used to be: the sweep panel sets the
    points, and the region sets where tau starts."""
    line = Timeline.from_dict(drawn("rabi", points=8))
    line.sweep = SweepAxis(
        regions=line.sweep.regions, points=25, step=40 * NS, name="tau"
    )
    result = await edit(TIMELINE=line.to_dict())

    assert result["points"] == 25
    assert result["sweep"]["stop"] == pytest.approx(
        line.sweep.length + 24 * 40 * NS
    )


async def test_dragging_the_region_wider_moves_where_the_sweep_starts(sequences):
    line = Timeline.from_dict(drawn("rabi", points=8))
    line.sweep = SweepAxis(
        regions=(Region(0.0, 100 * NS),), points=5, step=20 * NS, name="tau"
    )
    result = await edit(TIMELINE=line.to_dict())
    assert result["sweep"]["start"] == pytest.approx(100 * NS)


async def test_a_log_sweep_is_drawn_the_same_way(sequences):
    """T1 spans decades, so linear spacing wastes almost every point."""
    line = Timeline.from_dict(drawn("t1", points=6))
    assert line.sweep.spacing == LOG
    result = await edit(TIMELINE=line.to_dict(), SEQUENCE_NAME="t1")
    assert result["points"] == 6
    assert result["sweep"]["stop"] > result["sweep"]["start"] * 10


async def test_several_regions_grow_together(sequences):
    """A Ramsey's tau appears once per alternating arm, and both have to
    grow or half the sequence is not swept at all."""
    line = Timeline.from_dict(drawn("ramsey", points=6))
    assert len(line.sweep.regions) == 2
    result = await edit(TIMELINE=line.to_dict(), ALTERNATING=True,
                        SEQUENCE_NAME="ramsey")
    assert result["alternating"] is True
    assert result["readouts"] == 2 * result["points"]


async def test_a_hand_drawn_timeline_becomes_a_playable_sequence(sequences):
    line = Timeline(
        tracks=[
            Track("mw", [Pulse(0.0, 20 * NS, name="drive")]),
            Track("laser", [Pulse(20 * NS, 3020 * NS, name="readout")]),
            Track("gate", [Pulse(20 * NS, 3020 * NS)]),
        ],
        duration=4 * US,
        sweep=SweepAxis(regions=(Region(0.0, 20 * NS),), points=8, step=20 * NS),
    )
    result = await edit(TIMELINE=line.to_dict(), SEQUENCE_NAME="hand_rabi")

    assert result["readouts"] == 8
    load_sequence("hand_rabi", sequences).validate()


async def test_an_unplayable_timeline_is_refused_before_it_becomes_a_file(
    sequences,
):
    """Caught here rather than by the hardware an hour later."""
    from labpilot.core.pulse import SequenceError

    line = Timeline(
        tracks=[Track("mw", [Pulse(0.0, 20 * NS)])], duration=US
    )
    with pytest.raises(SequenceError):
        await edit(TIMELINE=line.to_dict())
    assert list_sequences(sequences) == []


async def test_the_result_carries_the_timeline_back_for_the_editor(sequences):
    """What makes "start from a Rabi, then edit it" one gesture rather
    than two authoring paths that cannot meet."""
    result = await edit(START_FROM="hahn_echo", SEQUENCE_NAME="hahn")
    line = Timeline.from_dict(result["timeline"])

    assert [t.channel for t in line.tracks][:3] == list(CHANNELS)
    assert len(line.track("mw").pulses) == 6  # 3 pulses per alternating arm
    assert len(line.sweep.regions) == 4


async def test_the_timeline_round_trips_through_the_workflow(sequences):
    """Load what came back straight in again and the sequence is
    unchanged — no lossy conversion between drawing and playing."""
    first = await edit(START_FROM="hahn_echo", SEQUENCE_NAME="hahn", ALTERNATING=True)
    again = await edit(
        TIMELINE=first["timeline"], ALTERNATING=True, SEQUENCE_NAME="hahn_again"
    )
    assert again["readouts"] == first["readouts"]
    assert again["points"] == first["points"]
    assert again["duration"] == pytest.approx(first["duration"])


# --- The window is the editor, and nothing else ----------------------------


async def test_the_editor_declares_no_result_view(sequences):
    """The canvas *is* the timing diagram. A second plot of the same
    picture beside it cost the editor half the window, and the half it
    cost was the one you can edit."""
    assert read_result_ui(EDITOR.read_text()) == {}


async def test_no_result_view_is_inferred_from_what_it_returns_either(sequences):
    """Declaring no `RESULT_UI` is only half of it: `pick_view` builds one
    from the data when a template declares none, so the result has to
    carry no arrays for it to find — which is why `channels` is a string
    and the timing diagram is gone entirely."""
    from labpilot.core.workflow.view import pick_view

    assert pick_view(await edit(TIMELINE=drawn("rabi", points=5))) is None


async def test_the_result_is_json_serialisable_for_the_wire(sequences):
    """It crosses REST and a WebSocket to reach the workflow window."""
    json.dumps(await edit(TIMELINE=drawn("rabi", points=5)))


async def test_the_sweep_is_reported_so_a_measurement_knows_its_axis(sequences):
    line = Timeline.from_dict(drawn("rabi", points=10))
    line.sweep = SweepAxis(
        regions=(Region(0.0, 20 * NS),), points=10, step=20 * NS, name="tau"
    )
    result = await edit(TIMELINE=line.to_dict())

    assert result["sweep"]["name"] == "tau"
    assert result["sweep"]["unit"] == "s"
    assert result["sweep"]["stop"] == pytest.approx(200 * NS)
    assert result["sweep"]["stepped_by"] == ""


# --- Sweeping the microwave frequency instead of a drawn time --------------


async def test_a_frequency_sweep_leaves_the_drawing_alone(sequences):
    """The sweep no pulse duration can encode. The pattern is fixed and
    the source steps between passes, so there is nothing to mark on the
    canvas — which is exactly why it needed a second `quantity` rather
    than another region."""
    line = Timeline.from_dict(drawn("pulsed_odmr"))
    result = await edit(TIMELINE=line.to_dict(), SEQUENCE_NAME="odmr")

    assert result["sweep"]["name"] == "frequency"
    assert result["sweep"]["unit"] == "Hz"
    assert result["sweep"]["stepped_by"] == "frequency"
    # Many points, one readout per pass: the points are not in the
    # sequence at all.
    assert result["points"] > 1
    assert result["readouts"] == 1


async def test_a_drawn_sequence_can_be_switched_to_a_frequency_sweep(sequences):
    """The editor's own gesture: take a Rabi drawing, change what is
    swept, and the pulses stay exactly where they were put."""
    line = Timeline.from_dict(drawn("rabi", points=10))
    before = [(p.start, p.stop) for t in line.tracks for p in t.sorted()]
    line.sweep = SweepAxis(
        quantity=FREQUENCY, start_value=2.8e9, stop_value=2.94e9, points=71
    )
    result = await edit(TIMELINE=line.to_dict(), SEQUENCE_NAME="odmr_from_rabi")

    assert result["points"] == 71
    assert result["sweep"]["start"] == pytest.approx(2.8e9)
    assert result["sweep"]["stop"] == pytest.approx(2.94e9)
    after = [
        (p["start"], p["stop"])
        for t in result["timeline"]["tracks"] for p in t["pulses"]
    ]
    assert after == before
