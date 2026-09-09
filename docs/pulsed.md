# Pulsed measurements — status

**Where this stands: sequences can be authored, saved, drawn and uploaded
to a pulser, and a gated counter will count against them. What does not
exist yet is the measurement that drives the two together** — no plan, no
extraction, no analysis, so nothing produces a Rabi curve. This page says
exactly what exists so nobody plans around a capability that isn't there.

## What works today

```python
from labpilot.core.pulse import save_sequence, timing_diagram
from labpilot.core.pulse.library import RigProfile, build

rig = RigProfile(rabi_period=200e-9, mw_frequency=2.87e9)
sequence = build("rabi", rig, tau_start=20e-9, tau_step=20e-9, points=50)

sequence.points          # 50
sequence.readouts()      # 50
sequence.duration        # 0.261 ms
save_sequence(sequence)  # ~/.labpilot/sequences/rabi.json
```

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
| `ui/desktop/components/pulse_blocks.py` — the block editor | **Done.** Qudi's dynamic-column element table: one row per element, one column per channel, an analog channel expanding into a shape plus its parameters. |
| `core/pulse/table.py` — the column rule | **Done.** Qt-free, so the fiddly part is tested headless. |
| `ui/desktop/components/pulse_editor.py` + the `pulse_sequence` result view | **Done.** Generator, Blocks and Rig tabs, and a one-lane-per-channel diagram. |
| `core/device/` — `Action`, records, capabilities, `Constraints` | **Done.** The four framework gaps that blocked any of this. |
| `instruments/pulser_mixin.py` — `PulserMixin` | **Done.** `upload_sequence` takes the abstract sequence and returns what the device really loaded. |
| `instruments/gated_counter_mixin.py` — `GatedCounterMixin` | **Done.** `configure_gates` returns what it actually set; `get_trace()` is a 2-D `Dataset` with real axes. |
| `instruments/mock/pulse_rig.py` — `MockPulser` + `MockGatedCounter` | **Done.** Real granularity, minimum element and activation configs; NV physics with a decaying readout transient. |
| `instruments/Swabian/pulse_streamer.py`, `instruments/SpinCore/pulse_blaster.py` | **Done.** Optional extras, both `describe()`-able with no SDK installed. |
| **`PulsedMeasurementPlan`, extraction, analysis** | **Missing.** The rig is driveable; nothing drives it yet. |
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

## What the editor is, and what it was not

The **Generator** tab is Qudi's *predefined-methods* panel: pick
`generate_rabi`, fill in a parameter form. That is a starting point, not an
editor, and for a while it was all there was here.

The **Blocks** tab is Qudi's actual PulseEditor. One row per element; one
column per channel, plus Length and Increment; rows added, duplicated,
reordered and typed into. The columns are **not fixed** — a digital channel
is a checkbox, and an analog channel contributes a shape combobox plus one
column per that shape's parameters, so choosing `Sin` on the microwave
channel grows Amplitude, Frequency and Phase columns and choosing `Chirp`
replaces them with the chirp's own.

The two paths meet rather than compete: **Load into editor** puts the last
generated sequence into the table, because the generator's output is
already in the table's own form. A row *is* an element's entry in the
sequence file, so nothing is converted and nothing is lost.

One deliberate difference from Qudi: the columns come from the **rig
profile's symbolic channels**, never from a connected pulser's
`activation_config`. An offline editor has no pulser to ask, and taking
columns from one would tie a saved sequence to a single rig's wiring.

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

## What a Rabi still needs

1. `PulsedMeasurementPlan`, whose `describe()` already has everything it
   needs — the sequence knows its sweep and its readout count before the
   first point, so pause, abort, patch streaming and HDF5 come for free.
2. Laser-pulse extraction: turning the raw `(gate, time_bin)` trace into
   one number per readout. The mock counter's readout transient is a real
   edge to find rather than a rectangle, so this can be verified.
3. Signal/reference analysis, and the fits.
4. `pulsed_measurement.py` plus four presets — Rabi, Ramsey, Hahn echo and
   T1 — the same consolidation that turned four scanners into presets of
   `omniscan`.

The device half is done: a sequence uploads to the mock, a PulseStreamer
and a PulseBlaster, and the counter counts against it. Nothing yet asks
them to do it point by point.

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
- Extraction and analysis parameters will be namespaced **per method**.
  Qudi merges them into one flat dict, which forces the documented rule
  that no two methods may share a keyword of different type.

## Status

- **6a** (actions with arguments, structured parameters, capabilities,
  constraint negotiation) — complete.
- **6a.5** (plain-Python workflow scripts) — complete.
- **6b** (sequence model, generator library, sampling, storage) — complete.
- **6d.5 / 6e, editor half** (the free-standing editor workflow, the
  generator form, the dynamic-column block editor, the timing-diagram
  result view) — complete.
- **6c** (pulser and gated-counter contracts, mock rig, PulseStreamer,
  PulseBlaster) — complete.
- **6d** (measurement plan, extraction, analysis, fits) — not started.
- **6e, measurement half** (the pulsed-measurement template and its four
  presets) — not started.
