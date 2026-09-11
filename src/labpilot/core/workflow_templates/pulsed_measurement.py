"""Play a saved pulse sequence and measure the curve it produces.

The execution half of the pulsed subsystem. The *authoring* half is
`pulse_sequence_editor.py`, which binds no instruments and writes a
sequence file; this binds the rig and plays one.

Rabi, Ramsey, Hahn echo and T1 are **presets of this file**, not four
templates. They differ in which sequence they load and which curve they
fit, which is a parameter dict — the same consolidation that turned four
scanners into presets of `omniscan`.

## What it does not do

Compile a waveform. `upload_sequence` takes the abstract sequence and the
bound pulser decides what to do with it: a PulseStreamer emits
`(level, duration)`, a PulseBlaster emits spinapi instructions, an AWG
samples the analog shapes. Each reports its own quantisation, so the same
file played on a 1 GS/s sequencer and a 12 GS/s AWG says how each of them
rounded it rather than silently differing.

It also does not own a loop. `PulsedMeasurementPlan` is a plan like any
other, so pause, abort, live patches and the automatic HDF5 save come
from `Run`. Qudi needs a second engine for this; here the only pulsed
thing about the run is what it measures.

## Channels

`CHANNELS` maps the sequence's symbolic channels — `"laser"`, `"mw"`,
`"gate"` — onto this pulser's physical ones. It is the one genuinely
rig-specific fact in a pulsed measurement, which is why it lives here
with the bindings rather than in the saved sequence. Leave it empty on a
pulser whose own channel names match.

## The result is 2-D, and that is not an accident

Nothing moves between points: the whole sweep plays in a few hundred
microseconds and every point improves together. So the axis the run
iterates is *accumulation*, and row `k` is the analysed curve after that
many complete passes. The last row is the answer; the others show whether
it had converged or was still drifting when it stopped.

## Except for a pulsed ODMR, where something does move

A carrier frequency is not a pulse duration, so such a sequence declares
that an *instrument* steps its axis and the plan walks the values,
writing each to the bound `microwave` source. Same rows, same streaming,
same file — rows are complete passes and row `k` is their running mean.
Nothing in this file changes for it: pick `pulsed_odmr` as the SEQUENCE,
bind a microwave source, and set `FIT = "dip"`.
"""

from labpilot.core.analysis.fits import (
    evaluate_decay,
    evaluate_dip,
    evaluate_rabi,
    fit_decay,
    fit_dip,
    fit_rabi,
)
from labpilot.core.pulse import ensure_default_sequences, load_sequence
from labpilot.core.run import PulsedMeasurementPlan
from labpilot.script import bind, execute

REQUIRED_INSTRUMENTS = {
    "pulser": {"kind": "generic", "capability": "pulser"},
    "counter": {"kind": "counter", "capability": "gated_counter"},
    # A digital rig gates an always-on source with the pulser, so neither
    # of these has to be bound. Naming one records it in the run's
    # provenance; naming the microwave also switches it around the run.
    "microwave": {"kind": "source", "optional": True},
    "laser": {"kind": "source", "optional": True},
}

RESULT_UI = {"type": "pulsed"}

# --- What to play -----------------------------------------------------------

# A sequence saved by the editor, in ~/.labpilot/sequences/.
SEQUENCE = "rabi"

# Symbolic channel -> this pulser's physical channel. Empty means the
# sequence's own names are already the physical ones.
CHANNELS: dict = {"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"}

# Complete passes over the sequence. The signal-to-noise knob: counts, and
# so the error bars, improve as its square root.
SWEEPS = 2000

# How many times the curve is recorded on the way — the rows of the
# result, and the run's progress steps.
CHECKPOINTS = 20

# --- How to record it -------------------------------------------------------

BIN_WIDTH = 1e-9
# 0 derives the record length from the sequence: half again its readout
# window, so the record holds the laser pulse plus dark bins either side
# for extraction to find its edges in.
RECORD_LENGTH = 0.0

# --- How to reduce it -------------------------------------------------------

# "conv_deriv" finds the laser pulse as the extrema of a smoothed
# derivative; "threshold" as the longest run above a level.
EXTRACT = "conv_deriv"
EXTRACT_PARAMS: dict = {}

# "auto" picks from the sequence — signal/reference when it alternates,
# per-readout normalisation when it does not. Or name one: "mean",
# "mean_norm", "mean_reference".
ANALYSE = "auto"
ANALYSE_PARAMS: dict = {}

# "rabi" (decaying cosine), "decay" (exponential), "dip" (Lorentzian, for
# a pulsed ODMR) or "none". Named rather than inferred: a sequence's name
# says nothing about the physics it measures, and a hand-edited one may
# measure something else entirely.
FIT = "none"

# The source's own on/off actions. `Source` has no generic
# enable/disable, because real sources disagree about whether they offer
# a settable key, a zero-argument action, or neither. "" for neither.
MICROWAVE_ON = "cw_on"
MICROWAVE_OFF = "off"


# A fresh install has an empty sequence library, so the four standard
# experiments are written out if they are not already there. Never
# overwrites: an edited rabi.json is yours. Delete one to get it back.
ensure_default_sequences()
sequence = load_sequence(SEQUENCE)

# Bound here rather than inside the plan so an unbound role fails now,
# with this workflow's own message, instead of on the worker loop.
bind("pulser")
bind("counter")
microwave = "microwave" if bind("microwave", optional=True) else None

plan = PulsedMeasurementPlan(
    sequence=sequence,
    pulser="pulser",
    counter="counter",
    microwave=microwave,
    microwave_on=MICROWAVE_ON,
    microwave_off=MICROWAVE_OFF,
    laser="laser" if bind("laser", optional=True) else None,
    channels=CHANNELS,
    sweeps=SWEEPS,
    checkpoints=CHECKPOINTS,
    bin_width=BIN_WIDTH,
    record_length=RECORD_LENGTH,
    extract=EXTRACT,
    extract_params=EXTRACT_PARAMS,
    analyse=ANALYSE,
    analyse_params=ANALYSE_PARAMS,
    name=SEQUENCE,
)

measured = execute(plan)

# The last row: the curve after every requested sweep. The rows before it
# are the same measurement with fewer counts, which is worth saving and
# not worth fitting.
points = sequence.points
curve = list(measured["data"][-points:])
# The swept values, whatever they are: a pulse time for the experiments
# the pulser plays, a microwave frequency for a pulsed ODMR. Kept under
# the name `tau` for the views and scripts that already read it.
tau = measured["axis_positions"][1]

fit = None
if FIT == "rabi":
    fit = fit_rabi(tau, curve)
    if fit is not None:
        fit["curve"] = evaluate_rabi(fit, tau)
elif FIT == "decay":
    fit = fit_decay(tau, curve)
    if fit is not None:
        fit["curve"] = evaluate_decay(fit, tau)
elif FIT == "dip":
    fit = fit_dip(tau, curve)
    if fit is not None:
        fit["curve"] = evaluate_dip(fit, tau)

RESULT = {
    **measured,
    # What the run measured, as its own curve rather than the last slice
    # of a flat buffer — so a view, a fit and a person all read the same
    # numbers without re-deriving the row boundary.
    "tau": tau,
    "curve": curve,
    "errors": plan.analysis.to_dict()["errors"] if plan.analysis else [],
    "fit": fit,
    "fit_model": FIT,
    # Where extraction decided the laser pulse was, and the summed record
    # it decided it from. The one thing a pulsed measurement gets wrong
    # silently, so it travels with the result rather than being lost.
    **plan.result,
}
