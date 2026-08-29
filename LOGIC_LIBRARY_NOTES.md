# Logic Library Notes (Phase 1)

Tier-2 logic research across Qudi, pyMoDAQ, and PyMeasure — scanning logic,
optimizer logic, and acquisition/triggering logic. Companion to
`ARCHITECTURE_NOTES.md` (which covered hardware abstraction, GUI↔logic
communication, scan data↔GUI mapping, config-driven wiring, and save/export
across the same three frameworks). Every claim below cites a real file read
directly — either from the local checkouts (`/Users/adrien/Documents/Qudi/
qudi-core`, `/Users/adrien/Documents/Qudi/qudi-iqo-modules`), the installed
`pymeasure` package (v0.16.0, `site-packages/pymeasure`), or pyMoDAQ's GitHub
repo (`PyMoDAQ/PyMoDAQ`, branch `5.2.x` — the current default branch; the
core `pymodaq` package is not pip-installed in this project's env, only its
`pymodaq_data`/`pymodaq_gui`/`pymodaq_utils` support packages are, so pyMoDAQ
source here was fetched fresh from GitHub rather than read locally).

No code is copied verbatim into LabPilot anywhere in this document or planned
from it — this is pattern study for Phase 3's design, not a port.

---

## 1. Scanning logic

"Scanning" = stepping one or more actuator values across a declared set of
points and collecting data at each one. All three frameworks separate *how
many points and where* (pure combinatorics, no hardware) from *actually
driving the hardware through them* — but they draw that line in different
places, and generalize to N dimensions to different degrees.

### 1.1 Qudi — `ScanningProbeLogic` (qudi-iqo-modules/src/qudi/logic/scanning_probe_logic.py)

- **Hard-capped at 1D/2D.** The class docstring says "1D/2D SPM
  measurements" outright; `start_scan(scan_axes, caller_id)` takes a tuple of
  axis names of any length, but the actual constraint enforcement lives one
  layer down in `ScanData` (qudi.interface.scanning_probe_interface,
  documented in ARCHITECTURE_NOTES.md §1.1): `if not (0 < len(scan_axes) <=
  2): raise ValueError`. So the *logic* class's own code is written
  axis-count-agnostic (`scan_axes = tuple(scan_axes)`, settings keyed by
  axis name, not position) but the *data structure* underneath refuses
  anything beyond 2 — a real, deliberate ceiling, not an accident of
  under-generalization.
- **Interface contract:**
  - Connector: `_scanner` → `ScanningProbeInterface` (tier-1 hardware).
  - Settings: `scan_ranges`/`scan_resolution`/`scan_frequency`, each a
    `{axis_name: value}` dict, StatusVar-persisted (survives a restart —
    directly the "come back to your parameters" property this project's
    workflow-template-params persistence, added this session, now also has).
  - Signals: `sigScanStateChanged(bool running, ScanData, caller_id)`,
    `sigScannerTargetChanged(dict pos, caller_id)`,
    `sigScanSettingsChanged(dict)`.
  - Lifecycle: `set_scan_range/resolution/frequency` (each rejected outright
    while a scan is running — "Unable to change scan ranges" — no
    queued-for-next-run semantics) → `start_scan(scan_axes, caller_id)` →
    hardware's own `configure_scan(settings)` can *talk back* adjusted
    ranges/resolution/frequency (clipped to what the hardware actually
    supports), which the logic re-absorbs and re-broadcasts via
    `sigScanSettingsChanged` — a real hardware-can-correct-the-request
    pattern, not just clamp-and-hope.
  - Polling: a *single-shot* `QTimer` that re-arms itself each tick
    (`__scan_poll_loop`), interval computed from one line's estimated
    duration (`resolution / frequency`), not a fixed cadence — cheaper than
    polling faster than data can possibly arrive.
- **`caller_id` threading**: every start/stop call carries an opaque
  `caller_id` (defaults to the logic's own `module_uuid`), propagated all
  the way through `sigScanStateChanged`'s third argument. This is how
  `ScanningOptimizeLogic` (§2.1) tells "did *my* scan finish, or someone
  else's" apart in a shared `sigScanStateChanged` signal — worth carrying
  into any LabPilot tier-2 design where more than one caller (a manual scan,
  an optimizer, a future autofocus routine) might drive the same actuator.

### 1.2 pyMoDAQ — `ScannerBase`/`ScannerFactory` (packages/pymodaq/src/pymodaq/utils/scanner/)

Genuinely N-dimensional, and structured as a **plugin registry**, the same
shape as this project's own `adapter_registry` for instruments
(`@ScannerFactory.register()` decorator, keyed by a `(scan_type,
scan_subtype)` pair — e.g. `('Sequential', 'Linear')`, `('Tabular', ...)`).

- **`ScannerBase` abstract contract** (`utils/scanner/scan_factory.py`):
  `positions: np.ndarray` (shape `(n_steps, n_axes)`, dimension-agnostic),
  `axes_unique: List[np.ndarray]` (per-axis unique values — exactly
  LabPilot's own `axis_positions`), `axes_indexes: np.ndarray` (per-step,
  per-axis index into `axes_unique` — exactly LabPilot's need to map a flat
  step back onto an N-D grid), `n_steps`/`n_axes`,
  `evaluate_steps()`/`get_scan_shape()`/`get_nav_axes()`/
  `get_indexes_from_scan_index()`. `data_actuator_at(scan_index,
  axis_index)` returns one `DataActuator` per axis per step — deliberately
  allows a "position" to itself be non-scalar (its docstring calls out a
  `BeamShaping` plugin whose actuator position is an image, not a float).
- **`SequentialScanner`** (`scanners/sequential.py`) is the concrete N-D
  case: a `(Actuator, Start, Stop, Step)` table with one row *per actuator,
  any number of rows*. `set_scan()` computes every position via a manual
  mixed-radix odometer walk (increment the last axis; on overflow, reset it
  and carry into the previous one; the pattern any nested-`for`-loop
  Cartesian product implements, just without literally nesting N loops
  since N isn't known at write time) — this is the concrete algorithm to
  reuse conceptually for LabPilot's own N-D actuator sweep generation
  (LabPilot's `omniscan.py` currently does something equivalent via
  `itertools.product` over per-axis linspaces — same result, tidier code,
  worth keeping rather than replacing).
- **`TabularScanner`** (`scanners/tabular.py`, not read in full this pass)
  is the other registered subtype: an arbitrary list of explicit N-D points
  (a trajectory) rather than a regular grid — relevant if LabPilot ever
  wants "scan along a path" as a capability distinct from "scan a
  rectangular/box region".
- **`Scanner`** itself (`utils/scanner/scanner.py`) is the thing a GUI
  holds: owns a `ParameterTree`, dispatches to whichever `ScannerBase` the
  user's `(scan_type, scan_sub_type)` selection resolves to via the
  factory, and exposes `positions`/`get_nav_axes()`/`get_scan_shape()`
  pass-through properties. It is *not* what drives the hardware during a
  run — `extensions/scan/daq_scan.py` (the `DAQ_Scan` extension, 1483
  lines, skimmed rather than read in full this pass) is the actual
  orchestrator that iterates `Scanner.positions`, moves actuators via
  `ModulesManager.move_actuators` (§3.2), triggers detectors via
  `ModulesManager.grab_data` (§3.2), and saves each step to HDF5.

### 1.3 PyMeasure — `SequenceHandler` (pymeasure/experiment/sequencer.py)

A completely different philosophy: **no notion of a hardware actuator at
all.** A sweep is a nested tree of `(level, parameter_name, python_expression)`
rows (e.g. `"Voltage", "linspace(0, 10, 5)"`, with a child row nested one
level deeper for an inner loop over a second parameter) — `parameters_
sequence()` safely `eval`s each expression (a fixed allow-list of numpy
functions as the only globals, `__builtins__: None` — a real, deliberate
sandboxed-eval, not literal `eval()`) and computes the nested Cartesian
product into a flat list of `{parameter_name: value}` dicts. These dicts
are then each used to construct one independent `Procedure` instance
(pymeasure/experiment/procedure.py's `Procedure`, a declarative
`startup()`/`execute()`/`shutdown()` lifecycle class with `Parameter`
class-attributes, not unlike a qudi `LogicBase` module but scoped to one
*single measurement run* rather than a whole capability) queued one at a
time via a `Manager` (pymeasure/display/manager.py). **There is no live
position-following loop, no "settle then read" step, and no notion of a
scan axis's real range/resolution as hardware constraints** — a "scan" is
just "run N independent complete experiments with these N parameter
combinations," batch-style, closer to a parameter-sweep queue than to
Qudi's/pyMoDAQ's live, position-aware scan loop. Genuinely simpler, and
genuinely less applicable to LabPilot's "jog live, watch data update live"
requirement — noted as a real architectural difference, not a gap to be
embarrassed about on PyMeasure's part (it's simply solving a different
problem: single independent measurements over swept parameters, not a
continuously-live imaging scan).

---

## 2. Optimizer logic

"Optimizer" = automatically refining/centering a position based on live
feedback from a detector, without the user manually jogging around a
maximum by hand.

### 2.1 Qudi — `ScanningOptimizeLogic` (qudi-iqo-modules/src/qudi/logic/scanning_optimize_logic.py)

- **Not a single N-D grid scan around the target** — a *sequence of
  lower-dimensional sub-scans*, each ≤2D, each fit and centered before the
  next one runs. `OptimizerScanSequence` (same file) computes every valid
  decomposition of the *actual* axis count into a sequence of 1D/2D steps
  (e.g. 3 axes → `[('x','y'), ('z',)]`; a `dimensions=[2,1]` parameter says
  which step-sizes are allowed at all) via `itertools.combinations`+
  `permutations`, filtered to drop redundant/duplicate decompositions. For
  each step: run that sub-scan (through `ScanningProbeLogic`, §1.1, with its
  own `caller_id` so `_scan_state_changed` can tell its own scans apart from
  anyone else's), fit the result with `Gaussian`/`Gaussian2D`
  (`qudi.util.fit_models.gaussian`, 1D or 2D *only* — no `Gaussian3D`, which
  is exactly *why* the sequence approach exists instead of one N-D grid: a
  true N-D Gaussian fit either doesn't exist in the fit-model library or
  isn't attempted), `set_target_position` to the fit center, then start the
  next step. **This genuinely generalizes to any axis count** — the
  decomposition-search algorithm has no hardcoded dimension limit, only the
  *fit step size* (≤2D) is capped, which the sequence search already knows
  and works around.
- **Interface contract**: Connector `_scan_logic` →`ScanningProbeLogic`
  (an optimizer built *on top of* the scan logic, not directly on hardware —
  a real tier-2-depends-on-tier-2 example). `sigOptimizeStateChanged(bool
  running, dict position_update, object fit_data)`,
  `sigOptimizeSettingsChanged(dict)`. Settings (`scan_range`/`scan_
  resolution`/`scan_frequency` per axis, `scan_sequence`, `data_channel`)
  are the optimizer's *own*, separate from the main scan's — `start_
  optimize()` stashes the main scan's settings, overwrites them for the
  duration of the optimize run (`save_to_history: False` — optimizer runs
  never pollute scan history), and restores them in `stop_optimize()`.
- **Failure handling**: a failed fit (`_get_pos_from_2d_gauss_fit` catches
  broadly and returns the region's geometric center with `fit_result=None`
  as a fallback) aborts the whole optimize sequence rather than moving to a
  fit failure's nonsense center and continuing — "Stopping optimization due
  to failed fit."

### 2.2 pyMoDAQ — `optimizers_base`/`adaptive_optim`/`bayesian` (packages/pymodaq/src/pymodaq/extensions/)

A materially different, more general design: an **ask/tell optimization
loop**, the interface real Bayesian-optimization libraries (scikit-optimize,
`bayes_opt`) use, decoupled entirely from what algorithm is behind it.

- **`GenericAlgorithm`** (`extensions/optimizers_base/algorithm.py`, 95
  lines) — the whole contract: `bounds: dict[str, tuple[float, float]]`
  (arbitrary named actuators, no axis-count limit anywhere in this class),
  `ask() -> dict[str, float]` (next point to probe, falls back to
  `get_random_point()` if the underlying prediction function raises
  `PredictionError`), `tell(function_value: float)` (report back the
  objective value measured at the last `ask()`ed point),
  `best_individual`/`best_fitness` (running optimum), `stopping(ind_iter,
  stopping_parameters) -> bool`. Nothing about scanning, grids, or fitting
  — purely "propose a point / here's how good it was."
- **`OptimizationRunner.run_opti()`** (`extensions/optimizers_base/
  optimizer.py:181`) is the actual drive loop, and it is the single most
  useful pattern found in this whole research pass for LabPilot's own
  optimizer generalization:
  ```
  while running:
      next_target = algorithm.ask()                          # dict[str, float], any N actuators
      output = model_class.convert_output(next_target, ...)  # algorithm-space -> actuator DataToExport
      modules_manager.move_actuators(output, mode, polling=sync_acts)
      det_done = modules_manager.grab_data()                 # trigger + wait for every selected detector
      objective = model_class.convert_input(det_done)         # detector DataToExport -> ONE scalar
      algorithm.tell(objective)
  ```
  The `model_class` (`OptimizerModelGeneric`) is the pluggable piece that
  answers exactly the question LabPilot's own optimizer needs answered
  generically: *given whatever this detector produced (scalar, spectrum,
  image, cube), reduce it to one number to optimize.* Decoupling that
  reduction from the ask/tell loop is the cleanest N-D-detector-to-scalar
  pattern seen in any of the three frameworks — genuinely reusable idea,
  independent of whether LabPilot ends up using Bayesian optimization,
  qudi-style Gaussian-fit sequencing, or a simple grid-argmax as the
  concrete `ask`/`tell` algorithm underneath.
- **Honest limit, not a marketing claim**: dimensionality-matching is still
  explicit, not implicit — `AdaptiveOptimisation.update_after_actuators_
  changed` (`extensions/adaptive_optim/adaptive_optimization.py:137`) looks
  up a `LossDim` enum from `len(actuators)` and disables the "start" action
  outright with a "no corresponding Loss function exists" warning if no
  loss/prediction function is registered for that exact axis count. So even
  pyMoDAQ's most-generalized-of-the-three optimizer is "N-D via a
  per-dimension-registered strategy," not "one algorithm that truly works
  at any N" — worth being precise about this distinction in any LabPilot
  design that cites pyMoDAQ's optimizer as the generalized reference,
  rather than overclaiming unlimited-N support it doesn't actually have.
- Two concrete algorithms ship on top of the same `GenericAlgorithm`/
  `OptimizationRunner` base: `AdaptiveOptimisation` (loss-function-guided
  adaptive sampling, `extensions/adaptive_optim/`) and a Bayesian one
  (`extensions/bayesian/bayesian_optimization.py`, not read in detail this
  pass) — concrete evidence the ask/tell split genuinely supports swapping
  the algorithm without touching the drive loop or the actuator/detector
  wiring.

### 2.3 PyMeasure — none

No optimizer logic anywhere in the package (`experiment/`, `display/`
directories checked; no fitting/optimization module beyond `pymeasure.
experiment.parameters`'s plain data-holding `Parameter`/`Measurable`
classes). Confirmed absence, not an oversight in this research — PyMeasure
provides the measurement/sweep/save primitives and leaves anything
optimization-shaped entirely to user code written against `Procedure.
execute()`.

---

## 3. Acquisition / triggering logic

"Acquisition/triggering" = the mechanics of firing off a measurement
(single-shot or continuous), buffering/timing the result, and knowing when
it's done — as distinct from *what* the measurement is for (a scan step, an
optimizer step, a bare live view).

### 3.1 Qudi — `TimeSeriesReaderLogic` (qudi-iqo-modules/src/qudi/logic/time_series_reader_logic.py)

The continuous-streaming case: connects to a `DataInStreamInterface`
(tier-1), and is a *self-perpetuating* acquisition loop — not a `QTimer`
like `ScanningProbeLogic`'s poll loop, but a **queued self-signal**:
`_sigNextDataFrame` (internal signal) connects to `acquire_data_block`
with `QtCore.Qt.QueuedConnection`, and `acquire_data_block` re-emits `_sig
NextDataFrame` at the end of its own body — each frame is processed, then
schedules the next one, forever, until `_stop_requested`. This is a
materially different self-scheduling technique from the scan poll loop's
single-shot re-arming timer, worth having *both* patterns available rather
than picking one universally: a timer is right when you know roughly how
long until data *should* be ready (a scan line); a queued self-signal is
right when you want to drain whatever's available as fast as the event loop
permits (a continuous stream).
- **Buffering/timing contract**: `oversampling_factor` (average N raw
  samples into one reported sample — hardware sample rate vs. reported data
  rate are two different, related numbers), `trace_window_size` (seconds of
  history kept), `moving_average_width` (must be odd — "ensure perfect data
  alignment", a real constraint the config validates and silently+loudly
  corrects), circular-buffer roll-and-insert (`np.roll` then overwrite the
  tail — avoids reallocating the whole trace array every frame), a
  `max_frame_rate` ConfigOption capping how often the GUI actually needs
  redrawing independent of the true sample rate. `configure_settings()` is
  one big validated setter (checks the *combined* effect of oversampling
  ×data_rate against the hardware's real min/max sample rate constraint —
  cross-parameter validation, not just per-field range checks).
- **Recording vs. displaying are separate flags**: `_data_recording_active`
  (accumulating a *save-to-file* buffer) is independent of `module_state()
  == 'locked'` (the stream running at all) — you can stream/display without
  recording, or start recording mid-stream. `start_recording()`/`stop_
  recording()` are their own lifecycle, not tied to `start_reading()`/
  `stop_reading()`.
- **`PIDLogic`** (qudi-iqo-modules/src/qudi/logic/pid_logic.py) is a
  smaller, adjacent case — genuinely marked in-repo as untested/legacy
  (`warnings.warn("has not been tested on the new qudi core...")`) — a thin
  `QTimer`-driven polling wrapper around a `PIDControllerInterface` (get/
  set kp/ki/kd/setpoint, get process/control value each tick into a rolling
  `history` buffer). Noted for completeness (stabilization-adjacent, not a
  scanning/optimizer/acquisition capability itself) rather than treated as
  a strong pattern to copy — even qudi's own maintainers flag it as needing
  rework.

### 3.2 pyMoDAQ — `ModulesManager.grab_data()`/`move_actuators()` (packages/pymodaq/src/pymodaq/utils/managers/modules_manager.py)

The **fan-out-trigger, wait-for-all, aggregate-heterogeneous-results**
pattern — the cleanest multi-instrument acquisition primitive found across
all three frameworks:
- `grab_data(check_do_override, Naverage=None)` (line 341): emits a
  `ThreadCommand(ControlToHardwareViewer.SINGLE, ...)` to *every currently
  selected detector simultaneously* (each is its own `DAQ_Viewer`, its own
  Qt object/thread — this is genuinely parallel dispatch, not sequential
  polling), then busy-waits (`QApplication.processEvents()` pump + a
  `detector_timeout` deadline) until every one of them has signaled done
  via its own `grab_done_signal` → `det_done` slot, accumulating everything
  into one `DataToExport` container that can hold N detectors' worth of
  0D/1D/2D/ND data side by side without any of them needing to agree on
  shape. `Naverage` can override each detector's own averaging setting —
  explicitly to let a caller (an optimizer, e.g.) probe a detector's actual
  data *shape* without paying for full averaging.
- `move_actuators(dte_act, mode='abs'|'rel', polling=True)` (line 516): the
  actuator-side equivalent — moves every selected actuator to its target
  from one `DataToExport` of `DataActuator`s, optionally blocking
  (`polling`) until every one of them reports `move_done`.
- **No generic hardware-trigger-mode concept** at this tier — `grep`ing
  both `daq_scan.py` (1483 lines) and `daq_viewer.py` (1307 lines) for
  "trigger" turns up only GUI button objects literally named `'grab'`/
  `'start'` (`.trigger()` on a `QAction`), never a rising/falling-edge or
  external-trigger-source abstraction. That configuration is left entirely
  to each instrument plugin's own settings tree — a real, useful negative
  finding: pyMoDAQ's tier-2 "acquisition" layer is about *orchestrating
  simultaneous multi-device grabs and knowing when they're all done*, not
  about *hardware trigger electronics*, which stays a tier-1 concern. This
  matches LabPilot's own existing split (DeviceSchema per instrument, no
  generic trigger-mode concept at the workflow-template layer either) —
  no incompatibility to resolve here.

### 3.3 PyMeasure — `Worker` (pymeasure/experiment/workers.py)

Not device-triggering at all — `Worker` is a `StoppableThread` running
exactly one `Procedure`'s `startup()`→`execute()`→`shutdown()` lifecycle,
publishing status/results/progress over a ZMQ PUB socket (`emit(topic,
record)`) so a separate process (the GUI, `pymeasure.display`) can subscribe
without being in the same address space — genuinely useful as a *process-
isolation* pattern (a crashing measurement can't take the GUI down with it)
but it is infrastructure for *running one measurement script safely*, not a
generic "trigger N detectors and wait" primitive the way pyMoDAQ's
`ModulesManager` is. Actual hardware triggering (arm/trigger/timing
settings) is left to each instrument driver's own methods, called directly
from a `Procedure.execute()` the user writes by hand — confirms the same
"no generic tier-2 acquisition abstraction" finding as §2.3's optimizer
absence: PyMeasure's philosophy leaves more to user code and provides less
opinionated framework machinery than either Qudi or pyMoDAQ, in both
directions.

---

## 4. Cross-framework summary

| | Qudi | pyMoDAQ | PyMeasure |
|---|---|---|---|
| **Scanning** | `ScanningProbeLogic` — real, hard-capped at 1D/2D (`ScanData` raises above 2 axes); axis-name-keyed settings, hardware-can-correct-the-request | `ScannerBase`/`ScannerFactory` — genuinely N-D, plugin-registered scan types (`Sequential`/`Tabular`/...), `positions`/`axes_unique`/`axes_indexes` cleanly separate "flat steps" from "N-D grid" | `SequenceHandler` — N-D *parameter* sweep (sandboxed-eval nested tree → Cartesian product), but zero hardware/actuator awareness; produces independent `Procedure` runs, not a live position-following loop |
| **Optimizer** | `ScanningOptimizeLogic` — sequence of ≤2D sub-scans + Gaussian fit per step, genuinely N-D via decomposition search, `caller_id`-disambiguated from manual scans | `GenericAlgorithm`/`OptimizationRunner` — ask/tell loop, N-D bounds/actuators, pluggable `OptimizerModelGeneric.convert_input` reduces any detector shape to one scalar; dimensionality still gated by a per-N registered loss function, not truly unlimited | none — confirmed absent |
| **Acquisition/triggering** | `TimeSeriesReaderLogic` — continuous stream, queued self-re-triggering loop, oversampling/moving-average/circular-buffer, recording independent of streaming | `ModulesManager.grab_data`/`move_actuators` — parallel fan-out trigger + wait-for-all-done + heterogeneous aggregation across N detectors/actuators; no generic hardware-trigger-mode concept (stays tier-1) | `Worker` — process-isolated single-Procedure execution + ZMQ pub/sub monitoring; no generic multi-detector trigger primitive, hardware triggering left to user's `execute()` |

**Overall generalization ranking for LabPilot's purposes**: pyMoDAQ's
scanning and optimizer logic are the most directly useful *shape* to
generalize from (genuinely N-D on both the actuator and, for the optimizer,
the detector side); Qudi's `caller_id` pattern and its optimizer's
decomposition-into-fittable-sub-scans idea are worth keeping even though its
own scan logic is 2D-capped; PyMeasure's sequencer's *sandboxed-eval, nested
Cartesian-product* parameter-tree technique is a genuinely nice idea for
letting a user type `linspace(0, 10, 5)` instead of manually filling in
start/stop/step fields, decoupled from PyMeasure's batch-queue execution
model, which is otherwise the least applicable of the three to LabPilot's
"live, position-following" requirement.

---

## 5. Licensing

- **Qudi** (`qudi-core`, `qudi-iqo-modules`): every file read this pass
  (`scanning_probe_logic.py`, `scanning_optimize_logic.py`, `time_series_
  reader_logic.py`, `pid_logic.py`) carries an identical **LGPLv3** header
  ("GNU Lesser General Public License... version 3, or (at your option) any
  later version") — matches the correction already recorded in
  ARCHITECTURE_NOTES.md (the repo ships a GPLv3 `LICENSE` file alongside
  `LICENSE.LESSER`, but every individual source file's own header is LGPL).
  No code from these files is copied here or planned to be copied verbatim
  — only the *shape* of the interfaces/algorithms is being studied for an
  independent re-implementation.
- **pyMoDAQ**: confirmed **MIT** via `GET /repos/PyMoDAQ/PyMoDAQ/license`
  (`spdx_id: "MIT"`) — matches ARCHITECTURE_NOTES.md's prior correction
  (not CeCILL-B, which was this project's original, incorrect assumption
  before that file was written). MIT permits far more direct reuse than
  Qudi's LGPL if any actual code (not just pattern/shape) were ever lifted
  — still not done here, but worth noting MIT is the least restrictive of
  the three if a future phase ever wants to adapt a larger chunk verbatim
  (e.g. `SequenceHandler`'s sandboxed-eval allow-list).
- **PyMeasure**: confirmed **MIT** — every file read this pass
  (`procedure.py`, `sequencer.py`, `workers.py`) carries an identical MIT
  header ("Copyright (c) 2013-2026 PyMeasure Developers... Permission is
  hereby granted, free of charge...").

No verbatim code from any of the three was copied into this document or
into LabPilot as part of this research pass — every description above is
a re-explanation of what was read, written independently.
