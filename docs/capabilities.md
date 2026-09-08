# What LabPilot can and cannot do

One page, current as of the completion of Phase 6a. Numbers are measured
by importing the live registry, not estimated.

## The instrument layer

**301 adapters, 95 manufacturers, all describable without hardware.**

| Backend | Count |
|---|---|
| PyMeasure | 188 |
| pylablib | 55 |
| Mock | 49 |
| Test fixtures | 9 |

`describe()` constructs each adapter with placeholder arguments, so tag
search and the instrument browser see all 301 — not only the 90 that
happen to take no constructor arguments. Catalogue and registry are
checked for parity by `tests/test_adapter_contracts.py`, which also
asserts every key a schema declares settable has a working setter.

### What a device can describe about itself

- **`Parameter`** — name, dtype, shape, unit, role (`VALUE`/`AXIS`/
  `POSITION`/`SETTING`/`STATUS`), readable/settable, limits, choices,
  which axes index it, and tags. Limits and choices are **enforced on
  every write**, not merely declared.
- **Structured parameters** — a `record` describes a mapping, and a table
  of records describes a list of rows, with each field a `Parameter`
  carrying its own unit and limits. A limit on a field is enforced on
  every row.
- **`Action`** — a command with typed arguments and a declared reply.
  Arguments validate before the call leaves the client; the reply carries
  what the hardware actually applied.
- **`Constraints`** — what this particular unit can do: bounds,
  granularity, and genuinely discrete allowed values. `quantise()` reports
  every adjustment instead of silently changing the request.
- **Capabilities** — contracts beyond read/write, declared by mixins and
  composed onto the schema. Today: `hardware_scan`. A device may satisfy
  several, and the wrapper is composed from all of them.

### What it cannot do

- No entry-point plugin discovery for **pulse sequence** libraries yet
  (adapters themselves do have it).
- Trigger modes are declared on the schema but populated by no adapter and
  read by no consumer.
- Array setpoints (a sampled waveform) still pass through unvalidated —
  records cover structure, not numeric arrays.

## Data

`Dataset` / `DataArray` / `Axis` / `RunMeta` — a measurement carries its
own units, dtypes and axis coordinates. `Axis.kind` distinguishes an
actuator axis from a detector axis, which is what makes a crosshair
drawable as a structural fact rather than a naming convention.

`DatasetPatch` carries one incremental update, so the wire carries a point
rather than a re-serialised N-D array.

`Dataset` subclasses `dict`, so every older caller that indexed a result
by key still works.

## Runs

`Plan` is a protocol with `describe()` — everything knowable before the
first point. That is what lets the run manager allocate the grid, count
progress and stream patches, instead of each template doing it by hand.

| Plan | What it does |
|---|---|
| `ScanPlan` | N-D grid over actuator axes, with settling |
| `OptimizePlan` | Optimiser by decomposition into ≤2-D sub-scans |
| `TimeSeriesPlan` | Repeated reads against a time axis |
| `HardwareTimedScanPlan` | Drives a `hardware_scan` device |
| `ScriptPlan` | Runs a workflow `.py` — how templates execute |

Real `pause`/`resume`/`abort` — abort cancels the scope *and* stops every
actuator, rather than only flipping a state machine. Every run is written
to HDF5 with named axes and registered in the run catalogue without anyone
clicking Save.

**Limit:** only `ScanPlan` can be started from the console or REST. A new
plan type needs a request model and a route.

## The lab

`InstrumentSpec` (persistent: id, adapter key, connection, defaults) is
separated from `InstrumentHandle` (live: adapter, status, error). A
runtime write cannot be persisted onto the config by mistake, because a
spec has no field to hold one.

Roles are bound per run through a `ContextVar`, so two concurrent
workflows using the role `"detector"` no longer clobber each other.

## Workflows

A workflow is a `.py` file with `async def run(session)`. Its parameters
live in a database row, not in the source — loading a template no longer
writes a timestamped copy into the installed package.

**10 templates + 4 presets.** A preset is a named parameter dict against
an existing template, so `confocal_scanner` and `hyperspectral_imaging`
are configurations of `omniscan` rather than near-duplicate source files.
Adding a preset requires no code.

## User interfaces

One component registry keyed by `(context, component_type)`, covering
instrument blocks, workflow controls and result views.

- `ui_blocks.toml` — which blocks a window has **and where they go**
  (`area`, `tab_with`), plus per-capability selection.
- `workflow_blocks.toml` — the same mechanism for workflow controls,
  selected by what the template declares.
- The settings tree renders float, int, string, boolean, dropdown and
  record-group widgets from the schema.
- Instrument readings are **pushed** over a WebSocket at the rate the
  window asks for, falling back to HTTP polling if the socket won't open.

Front ends: a Qt desktop shell and a React browser app, both over one
backend.

## Scripting

The same code runs in the IPython console, a workflow template and a plain
notebook:

```python
run = lp.scan(over={"x": (0, 10, 51)}, read=["apd"])
run.wait()
run.result().to_hdf5("scan.h5")
```

Instruments come back as typed wrappers (`Motor`, `Detector`, `Source`,
`Scanner`) with a stable identity — `lp["stage"] is lp["stage"]`.

## Not built

- **Pulsed measurements** — no sequence model, no pulser or gated-counter
  contract, no pulsed plan, no editor. See [pulsed.md](pulsed.md).
- **True AWG support** — `instruments/AWG/` is five function generators.
- **A DAG workflow executor** — deliberately deferred; the script path is
  better for the scripting goal.
- **`pint` quantities end-to-end** — unit strings carry most of the value.

## Quality gates

- 550 tests, headless and Qt-free.
- A lint ratchet (`scripts/lint_budget.py`) that must not rise without a
  stated reason.
- Desktop checks as offscreen harnesses: `scripts/verify_ui_registry.py`,
  `scripts/verify_settings_tree.py`, `scripts/verify_adapter_registry.py`,
  `scripts/verify_workflow_system.py`.

**Caveat worth stating:** everything is verified against mocks and
simulated devices. Adapters that have never been run against real
hardware say so in their docstrings.
