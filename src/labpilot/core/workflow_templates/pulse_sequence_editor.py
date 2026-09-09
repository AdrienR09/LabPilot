"""Design a pulse sequence with no hardware — a workflow that binds nothing.

This is the authoring half of the pulsed subsystem, and it is deliberately
a *separate workflow* from the measurement that plays what it writes.

Three things follow from that, and each is the reason for the split:

- **Sequences can be designed away from the lab.** No instruments, no
  connection, no risk of firing a laser while thinking. That benefit only
  holds if the editor genuinely depends on nothing, which is why
  `REQUIRED_INSTRUMENTS` is empty and why the end-to-end check runs this
  with every instrument disconnected.
- **A sequence becomes a file** — named, versioned, diffable, shareable,
  and reusable by every measurement that wants it. Not a blob inside one
  measurement's parameters.
- **It stays testable headless.** This is a pure function from parameters
  to a document.

## What it writes, and what it deliberately does not

The file is the **abstract sequence** (`core/pulse/sequence.py`), not any
device's format. A free-standing editor cannot emit a device's format
because it does not know the device: sample rate, memory granularity,
minimum element length and channel activation sets all belong to whichever
pulser eventually plays it, and none of them are knowable here.

So the pulser compiles. A PulseStreamer emits `(level, duration)`, a
PulseBlaster emits spinapi instructions, a Tektronix AWG samples the
analog shapes — each from this same file, each reporting its own
quantisation. The measurement workflow never sees a waveform.

Channels are symbolic — `"laser"`, `"mw"`, `"gate"` — never `d_ch1`. The
mapping onto physical channels is the rig's, so it lives with the
measurement workflow's bindings. Qudi bakes `d_ch1` into its generation
parameters, which ties a saved sequence to one wiring; this is the one
place that choice is worth diverging on.

## The rig profile

What the editor *does* need is physics, not driver settings: the Rabi
period (pi and pi/2 derive from it), the laser length and delay, the wait
time, and the symbolic channel names. All of it is editable offline and
saved with the sequence.

`ANALOG_MW = False` describes a digital-only rig — a PulseBlaster gating
an external microwave source rather than an AWG synthesising the drive.
The four sequences are otherwise identical, which is the whole point of
the flag.
"""

from labpilot.core.pulse import save_sequence, timing_diagram
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.table import sequence_from_table, table_from_sequence

# Binds nothing. That is the feature, not an omission.
REQUIRED_INSTRUMENTS: dict = {}

RESULT_UI = {
    "type": "pulse_sequence",
    "segments_key": "segments",
    "channels_key": "channels",
    "duration_key": "point_duration",
}

# --- Where the sequence comes from -----------------------------------------

# "generator" builds one of the four standard experiments from the
# parameters below. "table" plays back BLOCKS, which is what the block
# editor writes — so the usual path is to generate a Rabi, press "Load into
# editor", and hand-edit from there.
SOURCE = "generator"

# The edited block table: one entry per block, each with its own elements.
# Exactly the form a sequence file stores, so nothing is lost round-tripping
# between the generator, the table and the file.
BLOCKS: list = []

# A hand-edited sequence has to say what it swept, because nothing else
# can know. Empty means "no declared sweep" — the run then plots against
# readout index, which is right for a sequence that is not a sweep.
SWEEP: dict = {}

# Whether consecutive readouts alternate signal and reference. Set by the
# generator for the experiments that need it; declare it yourself when
# hand-authoring one that does.
ALTERNATING = False

# One of core/pulse/library.py's generators: rabi, ramsey, hahn_echo, t1.
GENERATOR = "rabi"

# Saved as ~/.labpilot/sequences/<slug>.json, and what the pulsed
# measurement workflow's SEQUENCE parameter names.
SEQUENCE_NAME = "rabi"

# This generator's own parameters. Which ones it takes, with their units
# and limits, comes from `generator_parameters(GENERATOR)` — the editor UI
# builds its controls from exactly that.
GENERATOR_PARAMS: dict = {"tau_start": 20e-9, "tau_step": 20e-9, "points": 50}

# --- The rig profile: physics, not driver settings -------------------------

RABI_PERIOD = 200e-9      # one full oscillation; pi is half, pi/2 a quarter
MW_FREQUENCY = 2.87e9     # the NV zero-field splitting
MW_AMPLITUDE = 0.25       # volts, before any driver's own normalisation
LASER_LENGTH = 3e-6       # readout window
LASER_DELAY = 700e-9      # photons arriving and the laser actually shutting off
WAIT_TIME = 1e-6          # repolarisation before the next repetition

LASER_CHANNEL = "laser"
MW_CHANNEL = "mw"
GATE_CHANNEL = "gate"     # None on an ungated rig: laser pulses are readouts
ANALOG_MW = True          # False gates an external source (PulseBlaster)

# Which point of the sweep the timing diagram shows. A whole 50-point Rabi
# drawn at once is a solid block; one shot is the picture worth looking at.
PREVIEW_POINT = 0


profile = RigProfile(
    rabi_period=RABI_PERIOD,
    mw_frequency=MW_FREQUENCY,
    mw_amplitude=MW_AMPLITUDE,
    laser_length=LASER_LENGTH,
    laser_delay=LASER_DELAY,
    wait_time=WAIT_TIME,
    laser_channel=LASER_CHANNEL,
    mw_channel=MW_CHANNEL,
    gate_channel=GATE_CHANNEL,
    analog_mw=ANALOG_MW,
)

# Either way the sequence is validated before it is returned, so an
# unplayable one is caught here rather than by the hardware an hour later.
if SOURCE == "table" and BLOCKS:
    sequence = sequence_from_table(
        BLOCKS,
        SEQUENCE_NAME,
        sweep=SWEEP or None,
        laser_channel=LASER_CHANNEL,
        gate_channel=GATE_CHANNEL,
        alternating=ALTERNATING,
        description="Hand-edited in the block editor.",
    )
else:
    sequence = build(GENERATOR, profile, **GENERATOR_PARAMS).evolve(name=SEQUENCE_NAME)

path = save_sequence(sequence)
segments = timing_diagram(sequence, PREVIEW_POINT)

RESULT = {
    "sequence": SEQUENCE_NAME,
    "source": SOURCE,
    "generator": GENERATOR,
    "path": str(path),
    "description": sequence.description,
    # What the block editor loads. Carrying it in the result is what makes
    # "generate a Rabi, then hand-edit it" one gesture rather than two
    # separate authoring paths that cannot meet.
    "blocks": table_from_sequence(sequence),
    "points": sequence.points,
    "readouts": sequence.readouts(),
    "duration": sequence.duration,
    "channels": sorted(sequence.channels),
    "alternating": sequence.alternating,
    "sweep": {
        "name": sequence.sweep.name,
        "unit": sequence.sweep.unit,
        "start": sequence.sweep.values[0],
        "stop": sequence.sweep.values[-1],
    } if sequence.sweep else None,
    "preview_point": PREVIEW_POINT,
    "point_duration": max((s.stop for s in segments), default=0.0),
    "segments": [s.to_dict() for s in segments],
}
