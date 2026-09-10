# Workflows

A workflow is a Python script with one entry point:

```python
async def run(session: Session) -> dict:
    ...
```

`session` is the live `Session` (`src/labpilot/core/session.py`) — the same device
registry and event bus the whole running server shares. Everything else
(instrument roles, live result rendering, tunable parameters, the
optimizer, safety limits) is layered on top of that one contract via a
handful of well-known module-level constants and helper classes, covered
below. LabPilot ships 16 ready-to-use entries in its template library —
each adapted from a standard Qudi/pyMoDAQ acquisition pattern — in two
kinds.

**Templates** are modules in `src/labpilot/core/workflow_templates/`:
`omniscan`, `hardware_timed_scan`, `grating_spectrometer`, `odmr_sweep`,
`autofocus`, `actuator_optimization`, `pid_stabilization`,
`pump_probe_spectroscopy`, `peak_fit_series`, `time_series_acquisition`,
`pulse_sequence_editor`, `pulsed_measurement`.

**Presets** are named configurations of a template, declared in
`workflow_templates/presets.toml` — `generic_1d_scan`, `generic_2d_scan`,
`confocal_scanner` and `hyperspectral_imaging` are all `omniscan` with
different default ranges. They load, bind and run exactly like a template
(a workflow instance was always a row — a script path, a parameters dict
and a bindings dict — so a preset just supplies a different parameters
dict). They were four separate modules until each turned out to be
`omniscan` plus a params dict once `Run` owned the scan loop and a
`Dataset` could describe its own axes.

## Running a workflow

**From the Manager:**

1. Open the **Workflows** tab, load or select a workflow (or click
   **Templates…** to load one of the 14 built-ins as a fresh, unbound
   workflow).
2. Bind any instrument roles it needs (see below) to real connected
   instruments — the Flow Chart tab, or the workflow window's own binding
   UI.
3. Adjust its tunable parameters if needed.
4. Click **Execute**. **Stop** cancels a running execution. Only one
   execution per workflow can run at a time — the Execute button
   disables itself while a run is in progress.

**From code:**

```python
wf = lp.workflow('<workflow_id>')
wf.params                      # this workflow's own tunable constants
wf.set_param('AXIS_RANGES', {'x': [-2.0, 2.0, 40], 'y': [-2.0, 2.0, 40]})
wf.run()                       # starts, returns immediately
wf.state()                     # {'running': ..., 'progress': ..., 'last_results': ...}
wf.wait()                      # blocks until the run finishes, returns final state
wf.stop()
```

## Instrument roles

A template references the instruments it needs by **role**, not by a
literal instrument id — `session.get("xy_actuator")`, not
`session.get("mock_xy_stage_3")` — declared via a module-level constant:

```python
REQUIRED_INSTRUMENTS = {
    "xy_actuator": {"kind": "motor", "dimensionality": "ND"},
    "detector":    {"kind": "detector"},               # dimensionality omitted -> any
}
```

The role -> real-instrument-id binding is separate, mutable state
(`WorkflowGraph.metadata["instrument_bindings"]`), resolved at run time
via `Session.register_alias` — the script text itself never changes when
a binding is made or changed. `REQUIRED_INSTRUMENTS` is read with
`ast.literal_eval` on the parsed AST (`core/workflow/instrument_roles.py`)
— the script is never executed just to discover what it needs, and an
unbound role fails fast with a clear error naming it, rather than a
generic `KeyError` deep inside the script.

`session.get(role_name)` returns a kind-typed object (`Motor`/`Detector`/
`Source`/`Scanner`) with the ergonomic method set for that role's kind
(`move_abs()`, `read_value()`, ...) rather than just a generic
`read()`/`write()` dict interface — see [Scripting](scripting.md) for the
full method reference.

## Tunable parameters

Any top-level **UPPERCASE** constant a script declares — other than
`REQUIRED_INSTRUMENTS`/`RESULT_UI`/`CAPABILITIES` and any `..._ID` role
constant — is automatically a tunable workflow parameter, editable from
the Workflows tab or via `wf.set_param(name, value)`/`GET|PUT
/api/workflows/{id}/params`. No registration needed: `AXIS_RANGES`,
`SETTLE_TOLERANCE`, `HOLD_POSITIONS` in `omniscan.py` are ordinary module
constants that just happen to be all-caps. Only literal-eval-able values
(numbers, strings, bools, lists/dicts of those) are picked up; an
expression is silently skipped. Edits are applied as a precise,
span-targeted source rewrite (`write_workflow_param`) — not a blind
find-and-replace — so they can't accidentally touch an unrelated later
occurrence of the same text.

## `RESULT_UI` — live result rendering

A `RESULT_UI` constant tells the native desktop window (and the REST
`execution_state` response) how to render this workflow's live/last
result, without any per-template UI code. Four shapes exist today:

**`spectrum`** (a growing 1D trace) — `grating_spectrometer.py`:

```python
RESULT_UI = {
    "type": "spectrum",
    "x_key": "wavelengths_nm", "y_key": "spectrum",
    "x_label": "Wavelength (nm)", "y_label": "Intensity",
}
```

`spectrum` (and `odmr`, below) also accept an optional fit-curve overlay
(a dashed curve plus a vertical center marker, drawn over the raw trace
once a run finishes):

```python
RESULT_UI = {
    "type": "spectrum",
    "x_key": "...", "y_key": "...",
    "fit_x_key": "fit_curve_x", "fit_y_key": "fit_curve_y",
    "fit_center_key": "fit_center",
}
```

`fit_x_key`/`fit_y_key` name a dense reconstructed curve (see
`core/analysis/fits.py`'s `evaluate_dip`) in your script's return dict —
only meaningful in the final result (a per-iteration `report_progress()`
call has nothing to put there yet), so the overlay appears once the run
completes, not while it's live. Omit all three keys for a plain trace.

**`odmr`** (qudi's own ODMR GUI shape: the averaged spectrum + fit,
stacked above a "matrix" accumulation image — one row per repeat, so
drift or a bad average is visible directly, not just in the final
number) — `odmr_sweep.py`:

```python
RESULT_UI = {
    "type": "odmr",
    "x_key": "sweep_values", "y_key": "counts",
    "matrix_key": "matrix", "repeat_key": "repeats_done",
    "fit_x_key": "fit_curve_x", "fit_y_key": "fit_curve_y", "fit_center_key": "fit_center",
    "x_label": "Frequency (Hz)", "y_label": "Detector reading",
}
```

`matrix_key` names a list-of-rows (one row per completed repeat, same
length as `x_key`'s array) in your script's return dict/progress payload;
`repeat_key` names how many repeats have completed so far. This
workflow's own `SWEEP_START`/`SWEEP_STOP`/`SWEEP_POINTS`/`SWEEP_POWER`/
`AVERAGES`/`FIT_SHAPE` constants are edited live from the native window's
Sweep Control/Fit docks (`components/odmr_control.py`) via the same
tunable-param mechanism `AXIS_RANGES` uses (see below) — plain literal
numbers/strings, not a computed list, so they actually qualify.

**`image2d`** (a 2D image, optionally with a draggable crosshair tracking
a live actuator position) — as a template declaring a fixed position pair
would use it:

```python
RESULT_UI = {
    "type": "image2d",
    "value_key": "image", "x_key": "x_positions_mm", "y_key": "y_positions_mm",
    "value_label": "Counts",
    "crosshair": {"role": "xy_actuator", "x_axis": "x", "y_axis": "y"},
}
```

**`ndscan`** (any number of actuator axes, one 2D projection panel per
axis pair, plus a per-channel 1D projection) — `omniscan.py`:

```python
RESULT_UI = {
    "type": "ndscan",
    "value_key": "data", "shape_key": "shape",
    "axis_names_key": "axis_names", "axis_positions_key": "axis_positions",
    "actuator_axis_count_key": "actuator_axis_count",
    "value_label": "Detector reading",
    "crosshair": {"role": "actuator"},
}
```

Every `*_key` names a key your script's `session.report_progress(...)`
payload (and the run's final return value) must contain — the UI reads
through those names, not fixed ones, so different templates can call
their result array whatever makes sense (`"image"`, `"data"`,
`"live_image"`, ...).

Each of these four shapes also has a typed dataclass alternative
(`core.workflow.result_types.ImageResult`/`SpectrumResult`/`OdmrResult`/
`NDScanResult`) usable in place of the raw dict — see
[Scripting → RESULT_UI](scripting.md#result_ui--typed-alternative-to-the-dict).
The raw dict form above is still fully supported; the dataclass form's only
difference is that a typo'd field name or missing required one raises a
clear error at bind time instead of silently rendering a blank panel.

Each image panel in the scanner view has its own colorbar: a colormap
picker, a draggable histogram, and numeric min/max fields (pyMoDAQ-style)
— dragging a level or typing into a spinbox pins that panel's levels
until auto-level is turned back on from the workflow window's Settings
menu.

## Reporting progress

```python
await session.report_progress({
    "data": full_array_so_far,      # the FULL accumulated result — cheap to
    "shape": [...], "axis_names": [...], ...   # store (a reference, not a copy),
})                                              # but thinned before WebSocket broadcast

await session.report_reading({      # OPTIONAL companion for high point-rate scans:
    "index": start, "values": [...],  # this point's own contribution only —
    "shape": [...],                    # always small, applied by the client with
})                                      # no throttling/refetching needed
```

`report_progress` is the durable, REST-facing state (what a client
re-syncs from after a reconnect); `report_reading` is a lightweight,
bounded-size companion for templates producing many points quickly (see
`omniscan.py`'s `on_progress`) — call both together if your scan is
high-rate, or just `report_progress` alone otherwise.

## `ScanPlan` and `OptimizePlan`

These replaced `core/workflow/capabilities.py`'s `ScanCapability` /
`OptimizerCapability`, which are gone. Both live in `core/run/plans.py`
and share one move+read engine, so a full N-D scan and an optimiser's own
sub-scans don't each reimplement actuator movement and settling:

```python
from labpilot.core.run import execute
from labpilot.core.run.plans import ScanAxis, ScanPlan

plan = ScanPlan(
    axes=[ScanAxis("x", actuator_id, -2.0, 2.0, 40),
          ScanAxis("y", actuator_id, -2.0, 2.0, 40)],
    detector=detector_id,
    hold={"z": 0.0},                 # parked once before the grid starts
    settle_tolerance=0.02, max_settle_polls=5000,
)
result = await execute(session, plan)
```

The important difference from the old capability classes: a plan
**describes itself before it runs**. `describe()` returns the axes, shape
and units up front, so the run manager allocates the grid, counts
progress, streams `DatasetPatch`es, writes HDF5 and registers the run —
none of which a template does by hand any more.

A grid over 200,000 points or 50,000,000 elements raises immediately,
before any hardware motion — a typo'd point count fails fast with the real
numbers instead of thrashing memory for minutes first.

`OptimizePlan` decomposes any number of actuator axes into a sequence of
≤2-D sub-scans, each fit (`core/analysis/fits.py`'s `fit_peak`/
`fit_peak_2d`) and centred before the next runs — the generalisation of
Qudi's own confocal optimiser past its native 1-D/2-D ceiling. Declare
`CAPABILITIES = {"optimizer": {"around": "<role>"}}` (see below) and the
server auto-wires `/optimize/start|stop|state` for your template with no
extra code.

Note that a workflow's `CAPABILITIES` (below) and a *device's* capabilities
(`core/device/capabilities.py`) are different things that share a word: the
first says what a template can be asked to do, the second says which
hardware contracts an instrument satisfies.

## `CAPABILITIES`

```python
CAPABILITIES = {
    "scan": {},
    "optimizer": {"around": "actuator"},   # "around" names the REQUIRED_INSTRUMENTS role to re-center
    "save": {},
}
```

Optional — every template without one still works: `optimizer` is
inferred from `RESULT_UI["crosshair"]` when present, matching every
existing template's behavior before `CAPABILITIES` existed. Declare it
explicitly once your template needs more than that inference gives you.

## Writing a new template

1. Create `src/labpilot/core/workflow_templates/my_template.py`.
2. Declare `REQUIRED_INSTRUMENTS`, `RESULT_UI` (if it should render
   live), and any tunable UPPERCASE constants.
3. Write `async def run(session: Session) -> dict`, resolving roles via
   `session.get(role_name)` and reporting progress as you go.
4. Reuse `core/workflow_templates/_common.py` (`move_and_settle`,
   `detector_axes`, `spectrum_key`, `integration_time_key`) and
   `core/analysis/fits.py` rather than re-implementing settle-waiting or
   peak fitting — every built-in template is built on these.
5. It shows up automatically in the Workflows tab's **Templates…**
   library (discovered from the module, not a separate registration
   step) — cite its Qudi/pyMoDAQ origin in its docstring, following the
   existing templates' convention.

## Editing a workflow's script directly

The Workflows tab's script editor lets you view/edit a workflow's Python
directly (`GET`/`PUT /api/workflows/{id}/script`). A workflow built from
the node-graph editor also has a **generated**, read-only rendering of
its graph as a script (`core/workflow/script.py`'s `graph_to_script`) —
one-directional (graph -> script) for auditability; hand-edited script
text is saved as text only, not re-parsed back into graph nodes.
