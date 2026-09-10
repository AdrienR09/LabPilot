# Pulsed measurements — status

**Where this stands: Phase 6 is complete.** A Rabi runs end to end — from
one line at the console, from a script, or from the GUI as a preset. A sequence is authored, saved, drawn, uploaded to a pulser and
played; a gated counter counts against it; extraction finds the readout
window, analysis reduces it to a curve and a fit recovers the injected π
pulse. What is not built yet is the *workflow* around it — no template,
no presets, no result view — so today this is driven from a script or the
console rather than from the GUI.

## What works today

```python
from labpilot.core.pulse import save_sequence, timing_diagram
from labpilot.core.pulse.library import RigProfile, build

rig = RigProfile(rabi_period=200e-9, mw_frequency=2.87e9)
sequence = build("rabi", rig, tau_start=20e-9, tau_step=20e-9, points=50)

sequence.points            # 50
sequence.readouts()        # 50
sequence.readout_window()  # 3 us — what the counter records per gate
sequence.duration          # 0.261 ms
save_sequence(sequence)    # ~/.labpilot/sequences/rabi.json
```

and then, against a rig — at the console, with no workflow and no GUI:

```python
seq = lp.pulse.rabi(tau=(20e-9, 2e-6, 50))
run = lp.pulsed(seq, pulser="pulse_streamer", counter="tt", sweeps=2000,
                channels={"laser": "d_ch1", "mw": "a_ch1", "gate": "d_ch2"})
run.wait().result().to_hdf5("rabi.h5")
```

or as the plan object itself, inside a template:

```python
from labpilot.core.run import PulsedMeasurementPlan, execute

result = await execute(session, PulsedMeasurementPlan(
    sequence, pulser="pulser", counter="counter", channels=..., sweeps=2000,
))
```

The same plan either way. Which plans can be started from outside the
server is declared by the plans themselves (`core/run/requests.py`) —
`POST /api/runs/scan` could rebuild a `ScanPlan` and nothing else, which
is a wall `HardwareTimedScanPlan` hit first and this hit second.

Or through the GUI: the **Pulse Sequence Editor** workflow binds no
instruments, so it opens and runs with everything disconnected.

| Piece | State |
|---|---|
| `core/pulse/sequence.py` — the object model | **Done.** `PulseElement` → `PulseBlock` → `PulseSequence`, symbolic channels, JSON round trip. |
| `core/pulse/shapes.py` — `Idle`, `DC`, `Sin`, `Gauss`, `Chirp` | **Done.** Parameters are `Parameter` objects, so the settings tree renders a shape editor with no new code. |
| `core/pulse/library.py` — `rabi`, `ramsey`, `hahn_echo`, `t1` | **Done.** Plus `RigProfile`, the physics a sequence is written against. |
| `core/pulse/sampling.py` — `expand`, `sample`, `timing_diagram` | **Done.** Two compilation paths; see below. |
| `core/pulse/store.py` — saved sequence files | **Done.** `~/.labpilot/sequences/<name>.json`, listed with a reason when one will not play. |
| `workflow_templates/pulse_sequence_editor.py` | **Done.** Binds nothing; writes a sequence file and returns its timing diagram. |
| `core/pulse/tracks.py` — the timeline model | **Done.** Per-track intervals to time slices and back, by one rule: every edge on every track is a slice boundary. Qt-free, so the fiddly part is tested headless. |
| `ui/desktop/components/pulse_timeline.py` — the canvas | **Done.** One lane per instrument, pulses dragged and resized on it, sweep regions shaded across it. |
| `ui/desktop/components/pulse_editor.py` + the `pulse_sequence` result view | **Done.** The canvas, the sweep panel and a Rig tab, plus a one-lane-per-channel diagram of the finished sequence. |
| `core/device/` — `Action`, records, capabilities, `Constraints` | **Done.** The four framework gaps that blocked any of this. |
| `instruments/pulser_mixin.py` — `PulserMixin` | **Done.** `upload_sequence` takes the abstract sequence and returns what the device really loaded. |
| `instruments/gated_counter_mixin.py` — `GatedCounterMixin` | **Done.** `configure_gates` returns what it actually set; `get_trace()` is a 2-D `Dataset` with real axes. |
| `instruments/mock/pulse_rig.py` — `MockPulser` + `MockGatedCounter` | **Done.** Real granularity, minimum element and activation configs; NV physics with a decaying readout transient. |
| `instruments/Swabian/pulse_streamer.py`, `instruments/SpinCore/pulse_blaster.py` | **Done.** Optional extras, both `describe()`-able with no SDK installed. |
| `core/pulse/extract.py` — `conv_deriv`, `threshold` | **Done.** Finds the laser pulse in the raw record; parameters per method, never shared. |
| `core/pulse/analyse.py` — `mean`, `mean_norm`, `mean_reference` | **Done.** One value per swept point, with Poisson errors. |
| `core/run/plans.py` — `PulsedMeasurementPlan` | **Done.** Accumulation is the iterated axis; the result is a `(sweeps, tau)` history. |
| `core/analysis/fits.py` — `fit_rabi`, `fit_decay` | **Done.** Extends the one fitting module rather than starting a second. |
| `workflow_templates/pulsed_measurement.py` | **Done.** *One* acquisition workflow. Which experiment it runs is which sequence you pick in its dock. |
| `ui/desktop/components/pulse_control.py` | **Done.** Sequence library, sweeps, and the two method combos, filled from the registries. |
| `PulsedResultView` + a `pick_view` branch | **Done.** The curve with Poisson error bars and its fit, over the raw record with the extracted window shaded on it. |
| `instruments/AWG/` | Five pylablib **function generators** — frequency, amplitude, offset, enable. Not an arbitrary waveform generator: no upload, no sequence, no channels, no triggering. |
| `workflow_templates/odmr_sweep.py` | Works, but is **CW ODMR**, not pulsed — and predates the plan layer, so it hand-rolls its loop. |

## Authoring is offline; execution is online

The editor and the measurement are two separate workflows, and that split
is the design rather than an accident of ordering.

The editor binds **no instruments**. A sequence can be designed away from
the lab, and it becomes a *file* — named, versioned, diffable, shareable,
reusable by every measurement that wants it. `tests/` runs the editor
against a session with no devices at all, so if it ever grows a hardware
dependency that is where it shows.

What it writes is the **abstract sequence**, never a device's format. A
free-standing editor cannot emit a device's format because it does not
know the device: sample rate, memory granularity, minimum element length
and channel activation sets are all properties of whichever pulser
eventually plays it. So the pulser compiles, and the workflow never sees a
waveform.

Channels are symbolic — `"laser"`, `"mw"`, `"gate"` — never `d_ch1`. The
mapping onto physical channels is the rig's, so it lives with the
measurement workflow's bindings. Qudi bakes `d_ch1` into its generation
parameters, which ties a saved sequence to one wiring.

## The editor is the timeline

One canvas, one lane per instrument — laser, microwave, APD readout,
whatever the rig profile names. A pulse is a box on its lane: drag it
along, drag its edges to resize, click it to type what dragging cannot
set. There is no table and no separate generator form.

That is the shape a pulse sequence actually has. Every paper draws one,
every oscilloscope shows one, and a person setting a rig up thinks "the
gate opens 300 ns after the laser" rather than "element 4 has
`gate=True`".

**Start from** draws one of the four standard experiments onto the
canvas. A starting point, not a mode: after that the timeline is what
gets saved, so a hand-moved gate stays moved.

### Editing is horizontal; the model is vertical

A `PulseElement` is one interval with a value for *every* channel, so a
sequence is a run of time slices — which is what a pulser plays, and what
makes `increment` one number per slice. A person draws three independent
objects on three lanes, none of which knows about the others' edges.

`core/pulse/tracks.py` reconciles them with one rule: **every edge on
every track is a slice boundary**. Collect the times at which anything
changes, sort them, and each consecutive pair becomes an element. Going
back, adjacent slices holding the same value on a channel merge into the
one pulse someone drew. All four experiments round-trip exactly — points,
readouts, duration and sweep values.

Two things fall out of that rule and are easy to get wrong:

- **The timeline has a length of its own**, not "wherever the last pulse
  ends". The repolarisation wait is silence, and silence has no edges. A
  sequence that repolarises for 0 ns instead of 1 µs still runs and still
  produces a curve — the wrong one.
- **An empty lane is not a channel.** A T1 on a rig with a microwave
  source does not use it, and writing `mw: False` into every element
  would make the saved sequence claim a channel the pulser then has to
  have free.

### The sweep is drawn, not configured elsewhere

A sweep region is a shaded span across every lane. Everything after it
shifts as it grows, which is what a swept sequence physically does. One
mechanism covers every case:

- a Rabi marks the region over its microwave pulse;
- a Ramsey marks a **gap** — which is not a drawn object at all, so a
  per-pulse increment could not express it without a second gesture;
- a Ramsey marks **two** regions and a Hahn echo **four**, because each
  point's tau appears once per alternating arm. They are regions of one
  axis, so dragging one resizes the others rather than leaving two sweeps
  to be kept in step by hand.

Linear spacing compiles to one block repeated `points` times with an
`increment` — the model's own sweep primitive. Log spacing cannot be
written that way, since no constant increment produces a geometric
series, so it compiles to one block per point. Both produce the same
`Sweep` on the finished sequence, so nothing downstream knows which was
used.

One deliberate difference from Qudi: the lanes come from the **rig
profile's symbolic channels**, never from a connected pulser's
`activation_config`. An offline editor has no pulser to ask, and taking
lanes from one would tie a saved sequence to a single rig's wiring.

## Sampling is a library, not a pipeline stage

Qudi's pulser interface is `write_waveform(analog_samples,
digital_samples)`, so its logic layer samples every sequence to dense
arrays and each driver just uploads them. For a true AWG that is right.
For a digital sequencer it is badly wrong, and Qudi's own PulseStreamer
driver documents the symptom: it notes that `waveform_length` is
ill-defined for that device because the hardware run-length-encodes
identical consecutive samples.

The numbers make the point. A 20-point T1:

| | Cost |
|---|---|
| `expand()` — what a PulseStreamer or PulseBlaster consumes | **120 instructions** |
| `sample()` at 1 GS/s — what Qudi's interface would force | **17.5 million booleans**, five million of them a single idle |

So `upload_sequence` takes the *abstract* sequence and each driver reaches
for whichever it needs. Sampling is a library an adapter **may** use, not
a step imposed on everything upstream.

## The four experiments

Built and validated headless, on both an analog rig and a digital one
(`RigProfile(analog_mw=False)` gates an external source instead — the
sequences are otherwise identical):

| | Points | Readouts | Alternating | Duration | Blocks |
|---|---|---|---|---|---|
| Rabi | 50 | 50 | no | 0.26 ms | 1 |
| Ramsey | 50 | 100 | yes | 0.73 ms | 1 |
| Hahn echo | 40 | 80 | yes | 1.97 ms | 1 |
| T1 | 20 | 20 | no | 14.0 ms | 20 |

Two conventions are stated rather than assumed, because both are the kind
of thing that produces a plausible but wrong result:

- **A readout is where the counter gate opens**, not merely where the
  laser is on. T1 polarises with the laser, waits, then reads out —
  counting laser edges scores that initialisation as a second readout and
  silently halves the sweep. An ungated rig falls back to laser pulses,
  which for it is correct.
- **`tau` is the idle time between pulse edges**, not centre-to-centre.
  With a 200 ns Rabi period the two differ by 50 ns on *every* point.
  `centre_to_centre()` converts on request rather than one convention
  being applied silently.

## A pulsed run is not a scan

Nothing moves between points, and that single fact decides the shape of
the plan. The pulser plays the *whole* sweep in a few hundred
microseconds; the counter accumulates one readout per point per pass; and
every point of the curve improves together. There is no "measure point 7"
to pause in the middle of.

So the axis `PulsedMeasurementPlan` iterates is **accumulation**. Row `k`
of the result is the analysed curve after `checkpoint_sweeps[k]` complete
passes, which makes the result a genuine 2-D `(sweeps, tau)` array rather
than one curve overwritten twenty times. It costs one float per point per
checkpoint and buys three things:

- the run streams, pauses and aborts through the ordinary `Run` machinery
  with no special case — Qudi needs its own `pulsed_measurement_logic`
  with its own state and its own signals for exactly this;
- the live plot is just the last row;
- the saved file shows whether the measurement had converged or was still
  drifting when it stopped.

Abort is ordered: the pulser stops first, so the laser gate closes before
anything else is touched. A sample left under continuous illumination
bleaches.

## Extraction and analysis

Two steps, both registries of pure functions, both with **per-method**
parameters.

`extract` says *where* the laser pulse is. The window is found once, on
the record summed over every readout, and applied to all of them — a
physical statement rather than a shortcut, since every gate is raised by
the same pulser edge. `conv_deriv` takes the extrema of a
Gaussian-smoothed derivative, so it finds an edge rather than a level and
survives a background that drifts during a run. `threshold` takes the
longest run above a fraction of the record's range — simpler, more
brittle, and informative when the two disagree.

`analyse` says what to do with it, and always returns **one value per
swept point**, not per readout: an alternating sequence's 80 readouts
become 40 points here, where `alternating` is known, rather than
downstream where the convention would have to be guessed. `mean` is raw
counts; `mean_norm` divides each readout by its own repolarised tail, so
laser drift cancels shot by shot; `mean_reference` divides the signal
readout by the reference beside it and **refuses** non-alternating data
rather than pairing unrelated readouts. Errors are Poisson and propagate
through the ratios.

The plan's `analyse="auto"` picks from the sequence — `mean_reference`
when it alternates, `mean_norm` when it does not. A fixed default would
be wrong for half the experiments.

Two windows a real rig needs stating, both defaulting to NV values: the
signal window is the first 300 ns of the laser pulse, measured from where
extraction found the pulse rather than from the start of the record, so
it survives someone re-cabling an AOM; the normalisation window is a
microsecond of the tail, late enough that the laser has repolarised the
spin and the count rate there measures the laser rather than the state.

## One acquisition workflow

Not one per experiment. `pulsed_measurement` binds `pulser` and
`counter`, and which experiment it runs is **which sequence you pick in
its dock** — the library on disk, listed with its point count and its
duration, and marked with a reason when a file will not play. Rabi,
Ramsey, Hahn echo and T1 are four files, not four workflows.

That is the same reasoning that turned four scanners into presets of
`omniscan`, taken one step further: there is nothing left for a preset to
configure that is not already a parameter in the dock.

The fit is **named, not inferred**. A sequence's name says nothing about
the physics it measures, and a hand-drawn one may measure something else
entirely, so `FIT` is `"rabi"`, `"decay"` or `"none"` rather than a guess
from the file it was loaded from.

A fresh install has an empty sequence library, so the workflow writes the
four standard experiments out on its first run. It never overwrites: an
edited `rabi.json` is yours, and silently restoring the shipped one would
undo an afternoon of calibration.

## Seeing the extraction, not just the curve

The result view draws two things. The curve — one point per swept tau,
with Poisson error bars and the fit over it — is the measurement. Below
it is the **raw record summed over every readout, with the extracted
window shaded on it**, because that is the step that goes wrong quietly:
a window fifty nanoseconds early mixes in dark counts, one fifty
nanoseconds late throws away the photons that carry the spin state, and
neither raises anything. The curve simply comes out flatter and the T2
comes out short. Being able to look at it is the only defence.

## Verified

On the simulated rig, whose injected constants are recovered: a 200 ns
Rabi period fits to 199.7 ns, a 1.5 µs T2\* to 1.46 µs, a 4 µs Hahn echo
to 3.83 µs. The sequences upload unchanged to a PulseStreamer and a
PulseBlaster, each reporting its own quantisation.

Headless: `test_pulse_tracks.py`, `test_pulse_extract.py`,
`test_pulse_analyse.py`, `test_pulsed_plan.py`, `test_plan_transport.py`,
plus both templates in `test_template_smoke.py`. Offscreen:
`scripts/verify_pulse_editor.py` (52 checks, driving the real canvas) and
`scripts/verify_pulse_measurement.py` (34).

## Deliberate differences from Qudi

A clean-room reimplementation of the design — Qudi's pulsed sources are
LGPL-3.0 and this project is MIT, see [ATTRIBUTION.md](../ATTRIBUTION.md).
The design is cited; the source is not copied.

- A sequence **knows its own sweep**, so `Plan.describe()` can state the
  run's axes up front. Qudi passes the equivalent through a side-channel
  dict after generation, which is why its templates configure the counter
  by hand.
- `repetitions` means what it says. Qudi's means *extra* plays
  (`reps + 1` total), a documented trip-hazard in its own generators.
- Sequences serialise as **data, never pickle**. Qudi's pickle persistence
  costs it ~300 lines of loader — migration shims, a `ModuleNotFound`
  guard, and a `# FIXME` repairing an object its own pickle destroyed.
- A generator declares its parameters as `Parameter` objects. Qudi takes
  them from `inspect.signature` defaults, so its GUI guesses each unit
  from substrings of the name (`'amp' in name` means volts).
- Sampling is a library, not an interface requirement — see above.
- Extraction and analysis parameters are namespaced **per method**. Qudi
  merges them into one flat dict, which forces the documented rule that
  no two methods may share a keyword of different type, and a
  `type(a) == type(b)` check to enforce it.
- A pulsed run is a `Plan`, so pause, abort, streaming and persistence
  are inherited. Qudi's `pulsed_measurement_logic` is a second engine
  beside its scanning one.

## Status

- **6a** (actions with arguments, structured parameters, capabilities,
  constraint negotiation) — complete.
- **6a.5** (plain-Python workflow scripts) — complete.
- **6b** (sequence model, generator library, sampling, storage) — complete.
- **6d.5 / 6e, editor half** (the free-standing editor workflow, the
  timeline canvas, the drawn sweep, the timing-diagram result view) —
  complete.
- **6c** (pulser and gated-counter contracts, mock rig, PulseStreamer,
  PulseBlaster) — complete.
- **6d** (measurement plan, extraction, analysis, fits) — complete.
- **6e, measurement half** (the one pulsed-measurement workflow, its
  control dock and the `pulsed` result view) — complete.
