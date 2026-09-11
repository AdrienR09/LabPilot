"""Draw a pulse sequence with no hardware — a workflow that binds nothing.

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

## The timeline is the sequence

`TIMELINE` is what the editor draws and what this file compiles: one
track per instrument — laser, microwave, APD readout — with pulses on it,
and the swept regions marked across them. Editing is horizontal, one lane
per instrument; a pulser plays a run of vertical time slices; and
`core/pulse/tracks.py` converts by the one rule that every edge on every
track is a slice boundary.

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
time, and the symbolic channel names. All of it is editable offline, and
it is what **Start from** draws with.

`ANALOG_MW = False` describes a digital-only rig — a PulseBlaster gating
an external microwave source rather than an AWG synthesising the drive.
The four starting points are otherwise identical, which is the whole
point of the flag.
"""

from labpilot.core.pulse import save_sequence
from labpilot.core.pulse.library import RigProfile, build
from labpilot.core.pulse.tracks import Timeline, timeline_from_sequence

# Binds nothing. That is the feature, not an omission.
REQUIRED_INSTRUMENTS: dict = {}

# No RESULT_UI, deliberately. The editor's canvas *is* the timing diagram:
# one lane per instrument, pulses drawn on the lanes, the sweep shaded
# across them. A second plot of the same picture beside it was a duplicate
# that cost the canvas half the window, and the canvas is the half you can
# actually edit. So this workflow's window is the editor and nothing else,
# and the result below carries no arrays for `core/workflow/view.py` to
# infer a view from.

# --- What is drawn ----------------------------------------------------------

# The editor's canvas, as data: one entry per track, each with its pulses;
# the timeline's own length; and the swept regions. Empty means nothing has
# been drawn yet, and START_FROM fills it.
TIMELINE: dict = {}

# Which of core/pulse/library.py's experiments the "Start from" button
# draws — rabi, ramsey, hahn_echo, t1. Recorded so a sequence says where
# it began, not used unless the timeline is empty.
START_FROM = "rabi"

# Saved as ~/.labpilot/sequences/<slug>.json, and what the pulsed
# measurement workflow's SEQUENCE parameter names.
SEQUENCE_NAME = "rabi"

# Whether consecutive readouts alternate signal and reference. Set for you
# by the experiments that need it; declare it when hand-drawing one.
ALTERNATING = False

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
channels = [name for name in (LASER_CHANNEL, MW_CHANNEL, GATE_CHANNEL) if name]

# An empty canvas draws the chosen experiment, so a freshly loaded
# workflow has something to run rather than an error. Anything drawn wins:
# a hand-moved gate must survive pressing Save.
timeline = Timeline.from_dict(TIMELINE)
alternating = ALTERNATING
if not any(track.pulses for track in timeline.tracks):
    started = build(START_FROM, profile)
    timeline = timeline_from_sequence(started, channels)
    alternating = started.alternating

# Validated before it is returned, so an unplayable sequence is caught
# here rather than by the hardware an hour later.
sequence = timeline.to_sequence(
    SEQUENCE_NAME,
    laser_channel=LASER_CHANNEL,
    gate_channel=GATE_CHANNEL,
    alternating=alternating,
    description=f"Drawn in the pulse editor, starting from {START_FROM}.",
)

path = save_sequence(sequence)

RESULT = {
    "sequence": SEQUENCE_NAME,
    "start_from": START_FROM,
    "path": str(path),
    "description": sequence.description,
    # What the editor loads back. Carrying it in the result is what makes
    # "start from a Rabi, then edit it" one gesture rather than two
    # authoring paths that cannot meet.
    "timeline": timeline.to_dict(),
    "points": sequence.points,
    "readouts": sequence.readouts(),
    "duration": sequence.duration,
    # A string, not a list, and that is load-bearing rather than cosmetic:
    # a result carrying no array is a result `pick_view` infers nothing
    # from, which is what keeps this window the editor alone.
    "channels": ", ".join(sorted(sequence.channels)),
    "alternating": sequence.alternating,
    "sweep": {
        "name": sequence.sweep.name,
        "unit": sequence.sweep.unit,
        "start": sequence.sweep.values[0],
        "stop": sequence.sweep.values[-1],
        # Empty for a sweep the pulser plays; "frequency" for one an
        # instrument steps — see core/pulse/sequence.py's Sweep.parameter.
        "stepped_by": sequence.sweep.parameter,
    } if sequence.sweep else None,
}
