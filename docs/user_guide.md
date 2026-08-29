# LabPilot User Guide

LabPilot is a data-acquisition framework for laboratory instruments. It wraps
real instrument-control libraries (PyMeasure, pylablib) plus mock/test-fixture
devices behind one common interface, lets you connect and drive them from an
auto-generated UI, combine them into multi-step **workflows**, and now also
reach the whole thing programmatically from a **Jupyter notebook** or an
**IPython console** — all from one Manager window.

This guide is task-oriented: it walks through what you can actually do, not
just what each module contains. For internals/architecture, see the top-level
[README.md](../README.md) and the per-package READMEs it links to
(`src/instruments/README.md`, `src/ui/desktop/README.md`).

## Contents

1. [Architecture at a glance](#1-architecture-at-a-glance)
2. [Installing and launching](#2-installing-and-launching)
3. [The Manager window](#3-the-manager-window)
4. [Instruments](#4-instruments)
5. [Workflows](#5-workflows)
6. [Notebook & Console](#6-notebook--console)
7. [AI Assistant](#7-ai-assistant)
8. [Data & storage](#8-data--storage)
9. [Troubleshooting](#9-troubleshooting)
10. [Extending LabPilot](#10-extending-labpilot)

---

## 1. Architecture at a glance

```
┌────────────────────────────────────────────────────────────┐
│  Manager window (src/ui/desktop/)                            │
│  A native Qt window embedding the React app (frontend/)      │
│  via QWebEngineView                                           │
└───────────────────────┬────────────────────────────────────┘
                         │ HTTP + WebSocket (:8000)
┌───────────────────────▼────────────────────────────────────┐
│  LabPilot server (src/core/server.py) — FastAPI backend      │
│  Session (device registry), WorkflowEngine, AI assistant,    │
│  config persistence, Jupyter server lifecycle                │
└───────────────────────┬────────────────────────────────────┘
                         │
┌───────────────────────▼────────────────────────────────────┐
│  Instrument adapters (src/instruments/)                      │
│  258 instruments across 80 manufacturers, one common          │
│  interface (DeviceSchema): readable/settable params,          │
│  units, limits                                                 │
└────────────────────────────────────────────────────────────┘
```

Everything — instruments, the workflow engine, the AI assistant, the running
`Session` — lives inside **one backend process** (`labpilot start`, listening
on port 8000 by default). Every other piece (the Qt Manager window, the React
web app, a notebook kernel, an IPython console) is a separate process that
talks to that one backend over its REST + WebSocket API. This matters
practically: if you want to interact with a *live* instrument or a *running*
workflow from your own script or notebook, you do it the same way the GUI
does — through the API, not by importing instrument classes directly (see
[§6](#6-notebook--console)).

## 2. Installing and launching

```bash
# Core + every optional extra (instrument drivers, Qt GUI, CLI, notebook)
pip install -e ".[full]"
```

Individual extras, if you don't need everything:

| Extra | Adds |
|---|---|
| `pymeasure` | PyMeasure-backed instrument adapters |
| `pylablib` | pylablib-backed instrument adapters |
| `gui` | PyQt6 desktop shell + native instrument windows |
| `cli` | `labpilot` command-line tool |
| `notebook` | Embedded Jupyter server (see [§6](#6-notebook--console)) |

**Everything together** (backend + React dev server + Qt Manager window):

```bash
./launch.sh
```

**Backend only** (useful for headless use, or if you're driving it from a
notebook/script without the GUI):

```bash
labpilot start                       # http://localhost:8000
labpilot start --port 8765           # a different port
labpilot list-adapters                # see what's connectable
labpilot list-adapters --tags camera  # filter by DeviceSchema tag
labpilot check-ollama                 # verify the local AI service is reachable
```

## 3. The Manager window

The sidebar has one tab per major area:

| Tab | What it's for |
|---|---|
| **Dashboard** | Session status: backend connection, devices connected, AI availability |
| **Devices** | Browse the instrument catalog, connect/disconnect instruments, open a live instrument window |
| **Workflows** | List, load, and run workflows; edit their scripts and parameters |
| **Flow Chart** | Node-graph view/editor for a workflow's DAG |
| **AI Assistant** | Chat with the local AI assistant (see [§7](#7-ai-assistant)) |
| **Data** | Data visualization (in progress) |
| **Notebook** | A Jupyter notebook, pre-connected to this session (see [§6](#6-notebook--console)) |
| **Console** | An IPython terminal, pre-connected to this session (see [§6](#6-notebook--console)) |
| **Settings** | Session/instrument configuration |

## 4. Instruments

### Connecting an instrument

1. Open the **Devices** tab.
2. Pick an instrument from the catalog (filterable by manufacturer, type,
   dimensionality — 0D scalar, 1D spectrum/trace, 2D image, ND).
3. Choose a connection method if the instrument supports more than one
   (VISA, serial, TCP, USB serial number, ...) and fill in its parameters.
4. Click **Connect**.

Once connected, an instrument gets:

- A row in the Devices tab showing its live readable values.
- A native Qt window (via the desktop shell) with an auto-generated UI shaped
  by its dimensionality — a scalar readout + controls for 0D, a live plot for
  1D/2D/ND, with settings editable from the same window.

### The instrument catalog

258 instruments across 80 manufacturers: mock/test-fixture devices (for
development without real hardware), PyMeasure-backed adapters (hand-written
and auto-generated from every class in the installed `pymeasure` library),
and pylablib-backed adapters. Every adapter — regardless of what library
backs it — exposes the same `DeviceSchema` contract: named readable/settable
parameters with dtypes, units, and limits. That's what lets the UI generate
itself instead of needing a custom window per instrument.

```python
from instruments import adapter_registry, INSTRUMENT_CATALOG

adapter_registry.list()                    # {key: AdapterClass} — everything registered
adapter_registry.search(tags=["camera"])    # filter by DeviceSchema tags
INSTRUMENT_CATALOG                          # manufacturer/model/dimensionality metadata
```

## 5. Workflows

A workflow is a script (`run(session)`) that drives one or more instruments
through a sequence — a scan, a sweep, an optimization — and reports live
progress back to the UI. LabPilot ships 14 templates covering common
acquisition patterns (adapted from Qudi's and pyMoDAQ's own standard
workflows):

`omniscan`, `generic_1d_scan`, `generic_2d_scan`, `confocal_scanner`,
`hyperspectral_imaging`, `grating_spectrometer`, `odmr_sweep`, `autofocus`,
`actuator_optimization`, `pid_stabilization`, `pump_probe_spectroscopy`,
`peak_fit_series`, `time_series_acquisition`.

### Running a workflow

1. Open the **Workflows** tab, load or select one.
2. Bind any instrument roles it needs (e.g. "xy_actuator", "detector") to
   real connected instruments.
3. Adjust its parameters (e.g. a scan's axis ranges/resolution) — these are
   separate from any bound instrument's own settings.
4. Click **Execute** in the toolbar. **Stop** cancels a running execution.

While running, the result view updates live (over a WebSocket, not polling —
see the "Notebooks & console" note below on how this reaches other clients
too) and shows whatever `RESULT_UI` the template declares: a spectrum plot, a
2D image with a crosshair, an N-dimensional scan viewer with per-axis-pair
panels, etc.

### Multi-dimensional scans (omniscan, confocal_scanner, ...)

For any actuator/detector-based scan template:

- The **crosshair** marks the actuator's current target position on each
  axis-pair panel; dragging it also moves the live 1D projection shown in the
  Channels dock to match the crosshair's selected region.
- **Optimize** (toolbar, when the template declares a crosshair) re-centers
  the bound actuator on the detector's local maximum around the current
  position — a small ad-hoc sub-scan, not a full re-run. Once it finds a
  peak, the crosshair and the actuator's target position both update to
  match.
- The crosshair and axis controls are hidden while a scan is actively
  running (they'd otherwise fight the scan's own actuator moves) and
  reappear once it stops.
- A safety ceiling on total grid points/elements fails a scan fast with a
  clear error, rather than letting it silently thrash memory on an
  accidentally huge grid.

### Editing a workflow's script

The **Workflows** tab's script editor lets you view/edit the underlying
Python directly. Every template follows the same contract
(`core/workflow/script.py`): an `async def run(session)` function that calls
`session.report_progress(...)` (and, for high-point-rate scans,
`session.report_reading(...)` too — see `core/session.py`) as it acquires
data.

## 6. Notebook & Console

Every notebook kernel and terminal opened from the Manager auto-connects to
this running session as `lp` — a `LabPilotSession` (see
`src/core/notebook_api.py`). It talks to the exact same backend the GUI
does, over the same REST/WebSocket API, so anything you do from a notebook
is visible in the GUI and vice versa: writing an instrument setting from a
cell moves the same instrument the Devices tab shows; a workflow you start
from the GUI shows up as `running` if you check its state from a notebook.

> **Why an API client and not direct object access:** instruments are live
> hardware handles owned by the backend process. A notebook kernel is a
> separate OS process and can't share those objects directly — `lp` reaches
> them exactly the way the desktop app and web UI already do, over the
> network API, just with a friendlier interface.

### Opening it

- **Notebook** tab: opens a Jupyter file browser/notebook interface. New
  notebooks use the "LabPilot (Python 3)" kernel, which has `lp` ready
  the moment it starts.
- **Console** tab: opens an IPython terminal (running inside the same
  package environment as the backend) with `lp` already bound — no
  `import` needed.

Both are backed by one Jupyter server the backend launches on first use (a
few seconds to start; stays up for the life of the backend process, or until
`POST /api/jupyter/stop`).

### The `lp` API

```python
lp.instruments                       # ['mock_xyz_stage_2', 'fake_apd_8', ...] every registered id
lp['fake_apd_8'].read()              # {'counts': 1023.4} — current readable values
lp['fake_apd_8'].schema              # readable/settable param names, dtypes, units, limits
lp['mock_xyz_stage_2'].write(x=1.0, y=0.5)   # set one or more settable values
lp['mock_xyz_stage_2'].connect()     # connect it if it isn't already

lp.workflows                         # ['641a113f-...', ...] every loaded workflow's id
wf = lp.workflow('641a113f-...')
wf.params                            # this workflow's own tunable parameters
wf.set_param('AXIS_RANGES', {'x': [-4.0, 4.0, 20], 'y': [-4.0, 4.0, 20]})
wf.script                            # the workflow's Python source, as text
wf.run()                             # starts execution, returns immediately
wf.state()                           # {'running': ..., 'progress': ..., 'last_results': ...}
wf.wait()                            # blocks until the current run finishes, returns final state
wf.stop()                            # cancel a running execution

lp.client                            # the underlying core.api_client.LabPilotClient,
                                      # for anything not wrapped above (see that module)
```

A typical notebook cell — run a scan and plot the result once it's done:

```python
wf = lp.workflow('641a113f-7c42-4872-9826-a636c8810cdf')
wf.set_param('AXIS_RANGES', {'x': [-2.0, 2.0, 40], 'y': [-2.0, 2.0, 40]})
wf.run()
result = wf.wait()

import numpy as np, matplotlib.pyplot as plt
data = np.array(result['last_results']['data']).reshape(result['last_results']['shape'])
plt.imshow(data)
```

### Security note

The Jupyter server executes arbitrary code on request — that's the point of
a notebook. It's configured to allow being embedded in the Manager's iframe
(relaxed CSRF/CORS/CSP checks) and is only safe because it's bound to
`127.0.0.1` and every request needs its per-launch random token, which is
never exposed outside this backend's own already-authenticated
`/api/jupyter/status`. Don't expose the backend (or this Jupyter server) on
a network interface other than localhost without adding your own
authentication in front of it.

## 7. AI Assistant

The **AI Assistant** tab is a chat interface (backed by a local Ollama
model, e.g. `mistral`) that can hold a conversation, generate new workflow
scripts, and drive the Qt window-spawning DSL (`src/ui/dsl/`) to open
plots/controls bound to live device parameters on request. Run
`labpilot check-ollama` to confirm the AI service is reachable if the tab
shows "Unavailable".

## 8. Data & storage

- Session/instrument configuration persists as JSON under `~/.labpilot/`
  (`core/config/`), including saved instrument-sets and per-workflow
  parameter values, so they survive a backend restart.
- Workflow execution history (status, timing, results) is kept in a SQLite
  catalogue (`core/workflow/store.py`), queryable from the Workflows tab.
- Larger structured datasets are written via the HDF5 writer in
  `core/storage/`.

## 9. Troubleshooting

**"Signal timed out" in a Qt window.** Usually means the backend
(`:8000`) and/or the React dev server (`:3000`) aren't running — check with
`curl http://localhost:8000/api/health`, and `./launch.sh` restarts both
together.

**A scan freezes or seems stuck partway through.** Check the toolbar status
label — the Execute button disables itself while a run is genuinely in
progress, so if it's clickable again the previous run already finished (or
failed). If the displayed image looks incomplete on a *very* large/fast
scan, the client periodically re-syncs the full result from the server as a
safety net (every few seconds) — give it a moment before assuming it's stuck.

**Workflow list is slow to load / times out.** This was a real bug (fixed):
listing workflows used to fetch every workflow's full results blob just to
show a summary row. If you're on an older checkout, update — the list
endpoint no longer does that.

**A workflow won't start with "already running".** Only one execution per
workflow can run at a time (by design — a second start doesn't overlap
execution against the same result buffer, or against the same
instrument mid-move). Stop it first, or wait for it to finish.

**Notebook/Console tab shows an error instead of loading.** The Jupyter
server takes a few seconds to start on first use; the tab shows a spinner
during that window and a **Retry** button if it still fails afterward — the
error message names what went wrong (usually the `notebook`/`ipykernel`
package extra not being installed: `pip install -e ".[notebook]"`).

## 10. Extending LabPilot

- **New instrument adapter**: add a class under `src/instruments/<Manufacturer>/`
  following `instruments/_base.py`'s `AdapterBase` contract, plus a matching
  entry in `instruments/catalog.py`. See `src/instruments/README.md`.
- **New workflow template**: add a script under `src/core/workflow_templates/`
  following the existing templates' shape (`async def run(session)`,
  `RESULT_UI`, reporting progress via `session.report_progress`/
  `report_reading`) — reuse `core/workflow_templates/_common.py`'s
  settle/detection helpers and `core/analysis/fits.py`'s fit models rather
  than re-implementing them.
- **New API client language/tool**: everything above works from any process
  that can speak HTTP/WebSocket to the backend — `src/core/api_client.py`'s
  `LabPilotClient` is the reference (Python) implementation; the same REST
  surface is what the React frontend and the notebook/console integration
  both already use.
