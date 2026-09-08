# Pulsed measurements — status

**Short answer: no. There is no pulse module yet, and nothing here can
reproduce Qudi's pulsed GUI.** This page says exactly what exists, what
does not, and what the gap is, so nobody plans around a capability that
isn't there.

## What exists today

| Piece | State |
|---|---|
| `instruments/mock/pulse_sequencers.py` — `MockPulseSequencer` | Registered and catalogued. Takes a flat list of `{duration_ns, channels}` steps through a `dtype="json"` setpoint. **No workflow, plan or template drives it** — it is reachable only by hand from an instrument window. |
| `ui/desktop/components/pulse_sequence.py` — the editor | Wired into `ui_blocks.toml`, but hardcoded to that mock's exact dict shape. A second pulse device with a different structure gets a wrong editor. |
| `instruments/mock/{lasers,optical_modulators,microwave_sources}.py` | Registered, catalogued, tagged `ODMR`. No template binds a laser or gate role. The microwave source's entire triggered-scan half (`scan_on`, `reset_scan`, `trigger_next`) is called by nothing. |
| `core/workflow_templates/odmr_sweep.py` | Works, but is **CW ODMR**, not pulsed — and predates the plan layer, so it hand-rolls its loop and gets no descriptor, no pause and no patch streaming. |
| `instruments/AWG/` | Five pylablib **function generators** — frequency, amplitude, offset, enable. Not an arbitrary waveform generator in the pulsed sense: no waveform upload, no sequence, no channels, no triggering. |
| `core/device/` — `Action`, records, capabilities, `Constraints` | **Done.** The four framework gaps that blocked any of this are closed. |

So: the parts of an NV rig are present as individual mock instruments, and
none of them are connected to anything.

## Why they were never connected

A pulse sequence could not be expressed. The only way to declare a
non-scalar setpoint was `dtype="json"`, which validated nothing and which
the settings tree deliberately rendered as nothing. That is why
`MockPulseSequencer` needed a bespoke widget and why no plan could
usefully drive it.

That specific blocker is now gone — structured parameters, actions with
arguments, composed capabilities and constraint negotiation all landed as
the enabling work. What has not been built is everything that sits on top.

## What is missing, against Qudi's pulsed subsystem

Qudi's is roughly 18,000 lines across interface, logic and GUI. The parts
that matter here:

| Qudi | Here |
|---|---|
| `PulseBlockElement` → `PulseBlock` → `PulseBlockEnsemble` → `PulseSequence` | **Missing.** The object model is the whole foundation. |
| `sampling_functions.py` — Idle, DC, Sin, Chirp, ... | **Missing.** No analog shapes. |
| `PulserInterface` — constraints, `write_waveform`, activation configs | **Missing.** No pulser contract. |
| `FastCounterInterface` — gated counting, `get_data_trace()` | **Missing.** No gated counter. |
| `predefined_generate_methods/` — `generate_rabi`, `ramsey`, `hahnecho`, `t1`, XY8, ... | **Missing.** No sequence library. |
| `pulse_extractor.py` / `pulse_analyzer.py` — pluggable extraction and analysis | **Missing.** No laser-pulse extraction, no signal/reference ratio. |
| `PulsedMeasurementLogic` — the measurement loop | **Missing.** Would be a `Plan` here, not a second engine. |
| Pulsed GUI — 5 tabs, dynamic block/ensemble/sequence table editors | **Missing.** The current editor is a fixed two-column table for one mock. |

## What a Rabi measurement would need

Concretely, to run the simplest pulsed experiment end to end:

1. A sequence model that can express `[MW(τ), laser+gate, delay, wait]`
   with τ swept by a per-repetition increment.
2. A pulser contract with real constraints — sample rate, granularity,
   minimum element length, and which channel sets may be on at once.
3. A gated counter contract returning a 2-D `(laser_pulse, time_bin)`
   `Dataset` with real axes.
4. A `PulsedMeasurementPlan` whose `describe()` knows the sweep and the
   laser-pulse count before the first point, so pause, abort, streaming
   and HDF5 come for free.
5. Laser-pulse extraction and signal/reference analysis as pure functions.
6. A sequence editor whose columns come from the connected pulser's
   channel list, not from one mock's dict shape.

None of those exist. Items 1–3 are the ones everything else waits on.

## The plan

Phase 6 of the roadmap covers this, scoped as: a clean-room
reimplementation of Qudi's design (its pulsed sources are LGPL-3.0, this
project is MIT — see [ATTRIBUTION.md](../ATTRIBUTION.md)), validated on
Rabi, Ramsey, Hahn echo and T1, with sequences authored both as Python
generator functions and in a table editor, and drivers for a simulated
rig, a Swabian PulseStreamer and a SpinCore PulseBlaster.

The intended shape follows `hardware_scan_mixin.py`, which is the one
existing example here of a non-read/write device contract that is fully
wired: a mixin declaring a capability, recognised when the wrapper is
composed, driven by a `Plan`, surfaced by a template.

Deliberate differences from Qudi, decided during the design pass:

- A sequence **knows its own sweep**, so `Plan.describe()` can state the
  run's axes up front. Qudi has no equivalent, which is why its templates
  configure the counter through a side-channel dict.
- `repetitions` means what it says. Qudi's means *extra* plays (`reps + 1`
  total), a documented trip-hazard in its own generators.
- Sequences serialise as data (JSON/TOML), never pickle. Qudi's pickle
  persistence costs it ~300 lines of migration shims and a `# FIXME`
  repairing an object its own pickle destroys.
- Extraction and analysis parameters are namespaced **per method**. Qudi
  merges them into one flat dict, which forces the documented rule that no
  two methods may share a keyword of different type.

## Status

Phase 6a — the enabling work — is complete and committed. Phases 6b
(sequence model), 6c (device contracts and drivers), 6d (plan, extraction,
analysis) and 6e (editor, result view, templates) are **not started**.
