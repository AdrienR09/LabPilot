# LabPilot

A data-acquisition framework for laboratory instruments. LabPilot wraps real
instrument-control libraries (PyMeasure, pylablib) plus mock/test-fixture
devices behind a common adapter interface, so instruments can be discovered,
connected, and given an auto-generated UI without writing device-specific GUI
code. Instruments can be combined into multi-step workflows; everything is
reachable from one manager window — including a native IPython console
pre-connected to the running session.

LabPilot is built on the design work of **Qudi** and **PyMoDAQ**, and its
implementation is **AI-assisted**. See **[ATTRIBUTION.md](ATTRIBUTION.md)** for
what comes from where, and for a known licensing issue affecting two vendored
theme files.

See **[docs/index.md](docs/index.md)** for the full documentation. This README
covers setup and internals.

## What it does today

| | |
|---|---|
| **Instruments** | 301 catalogued adapters across 95 manufacturers — 49 mock, 9 test fixtures, 188 PyMeasure, 55 pylablib. All 301 describable without hardware attached. |
| **Parameters** | Typed `Parameter` objects with units, limits, choices, roles and tags. Limits are enforced on every write. Structured setpoints (records and tables) are described, not escaped as JSON. |
| **Actions** | Device commands with typed arguments that report back what the hardware actually applied. |
| **Capabilities** | Contracts beyond read/write (`hardware_scan`, and the pulse contracts in progress) declared by mixins, composed onto the schema, visible over REST. |
| **Data** | `Dataset` / `DataArray` / `Axis` — self-describing measurements with units and real axis coordinates. Incremental `DatasetPatch` streaming. |
| **Runs** | `Plan` protocol with `describe()`; scan, optimise, time-series, hardware-timed, and script plans. Real pause/resume/abort, automatic HDF5 + run catalogue. |
| **Lab** | `InstrumentSpec` (persistent config) split from `InstrumentHandle` (live process state), with run-scoped role binding. |
| **Workflows** | 10 templates + 4 presets. A workflow is a `.py` file with `async def run(session)`; its parameters live in a row, not in the source. |
| **UI** | One component registry, config-driven layout (`ui_blocks.toml`, `workflow_blocks.toml`), Qt desktop + React browser front ends over one backend. |
| **Console** | The same API in the IPython console, a workflow template and a plain notebook. |

**Not yet built:** the pulsed-measurement subsystem (pulse sequence model,
pulser/gated-counter contracts, pulsed plans and editor). See
[docs/pulsed.md](docs/pulsed.md) for what exists, what does not, and the plan.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  labpilot.ui.desktop  — desktop shell                       │
│  manager_qt_webview.py: Qt window embedding the React app   │
│  via QWebEngineView, in its own process                     │
└───────────────────────┬────────────────────────────────────┘
                        │ HTTP + WebSocket (:8000)
┌───────────────────────▼────────────────────────────────────┐
│  labpilot.core.server  — FastAPI backend                    │
│  lab, runs, workflows, config persistence, storage          │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│  labpilot.instruments  — instrument adapter registry        │
│  organized by manufacturer, then instrument type            │
│  catalog.py: manufacturer/model/dimensionality metadata     │
└────────────────────────────────────────────────────────────┘
```

One authoritative backend process, several front ends. That boundary is what
lets a Qt window, a browser and a console share live state; it is deliberate
and should not be collapsed.

Everything installable lives under `src/labpilot/`, as one package with three
subpackages. `import labpilot` itself is cheap — it pulls in no subpackage, so
it never triggers the adapter discovery pass `labpilot.instruments` performs on
import.

- **`labpilot.instruments`** — the instrument library. `adapter_registry` is the
  source of truth for what's connectable; `catalog.py` adds display metadata.
  `available_catalog()` narrows that to adapters that registered on this machine.
  - `_base.py` — `AdapterBase`: read/write/stage lifecycle, per-device lock,
    `describe()` for offline schema introspection.
  - `hardware_scan_mixin.py` — the hardware-timed scan contract, and the model
    for how any non-read/write device contract plugs in.
- **`labpilot.core`** — everything non-UI.
  - `device/` — `Parameter`, `DeviceSchema`, `Action`, `Constraints`,
    `capabilities`, and the kind-typed `Motor`/`Detector`/`Source`/`Scanner`
    wrappers `Session.get()` returns.
  - `data/` — `Dataset`, `DataArray`, `Axis`, `DatasetPatch`.
  - `run/` — `RunManager`, `Run`, `RunDescriptor`, and the concrete plans.
  - `lab/` — `Lab`, `InstrumentSpec`, `InstrumentHandle`.
  - `workflow/` — the workflow store, presets, migration, role binding.
  - `workflow_templates/` — the 10 shipped templates plus `presets.toml`.
  - `config/` — persistent state under `~/.labpilot`, relocatable with
    `LABPILOT_HOME`.
  - `storage/` — HDF5 writer + SQLite run catalogue, wired into every run.
  - `api/` — the `/api/dashboard/*` router.
  - `server.py` / `cli.py` — the FastAPI app and the `labpilot` CLI.
- **`labpilot.ui`** — everything UI.
  - `desktop/` — the Qt desktop shell, a separate process talking HTTP.

## Installing

```bash
pip install labpilot            # the framework, the server and the CLI
pip install "labpilot[app]"     # plus the Qt desktop app and its console
```

`labpilot` on its own is enough to write and run acquisition scripts, serve the
REST/WebSocket API and drive every mock instrument. Driver libraries are extras,
because an NI card is not a reason for a lab with a spectrometer to install
NI-DAQmx:

| Extra | Brings | For |
|---|---|---|
| `app` | PyQt6, pyqtgraph, pymodaq_gui, qtconsole | the desktop app |
| `pymeasure` / `pylablib` | those libraries | the ~200 adapters backed by each |
| `ni` | nidaqmx (not macOS — NI ships no build) | NI DAQ cards |
| `ni-fpga` | nifpga | NI R-Series FPGA cards |
| `oceanoptics` | seabreeze | Ocean Optics spectrometers |
| `swabian` | pulsestreamer | the Pulse Streamer |
| `spincore` | spinapi + the vendor driver | the PulseBlaster |
| `full` | everything that installs cleanly from PyPI anywhere | |

Every adapter imports its driver inside the method that needs it, so a missing
extra costs a clear error when you connect *that* instrument and nothing at all
otherwise. `labpilot list-adapters` lists all 300-odd either way, because an
adapter describes itself without its driver.

## Running

```bash
labpilot app                       # everything: backend, front end, manager window
labpilot app --no-window           # same, for a browser instead of the Qt window
labpilot start                     # the backend alone, on :8000
labpilot probe <adapter>           # check one instrument against its declared schema
labpilot list-adapters             # see what's connectable
labpilot list-adapters --tags camera
labpilot-manager                   # the desktop app, against a running backend
```

`labpilot app` starts the backend, settles the front end, opens the window, and
shuts all of it down together. **Nothing about the front end needs arranging
first:** an installed wheel carries the built bundle, and from a checkout the
command runs `npm install` and `npm run build` itself when they are missing. The
first launch on a new machine is `labpilot app` and nothing else.

| | |
|---|---|
| (default) | Serves the built bundle — no Node needed at launch |
| `--dev` | Vite dev server instead, with hot reload |
| `--build` | Rebuild the bundle first |
| `--no-window` | No Qt window; prints a URL for a browser |

`--port` is a preference, not a demand: if it cannot be bound, the launcher takes
one the OS offers and says which. That is what makes it work on Windows, where
Hyper-V, WSL2 and Docker Desktop reserve blocks of TCP ports at boot and a bind
inside one fails with WinError 10013 though nothing is listening there.

It replaces the `launch.sh` shell script, which only ever worked in a
macOS/conda checkout.

## Instrument adapters

```python
from labpilot.instruments import adapter_registry, INSTRUMENT_CATALOG

adapter_registry.list()                   # {key: AdapterClass} for everything registered
adapter_registry.search(tags=["camera"])  # filter by DeviceSchema tags
INSTRUMENT_CATALOG                        # manufacturer/model/dimensionality metadata
```

`src/labpilot/instruments/` is organised by manufacturer, then instrument type
(`<Manufacturer>/<type>.py`) — not by which library backs the adapter.

To add a new instrument, create an adapter under
`src/labpilot/instruments/<Manufacturer>/` following `_base.py`'s `AdapterBase`,
and add a matching entry to `catalog.py`. `tests/test_adapter_contracts.py`
checks that the two agree and that every key your schema declares settable has
a working setter.

## Development

```bash
pip install -e ".[dev,app]"
pytest                                  # 1108 tests, headless and Qt-free
ruff check .
python scripts/lint_budget.py           # the lint ratchet — must not rise
python scripts/verify_packaging.py      # the wheel installs and runs standalone
```

Desktop checks live in `scripts/verify_*.py` rather than `pytest`, because
importing pymodaq_gui's Qt stack into the test suite crashes collection with a
metaclass conflict:

```bash
QT_QPA_PLATFORM=offscreen python scripts/verify_ui_registry.py
QT_QPA_PLATFORM=offscreen python scripts/verify_settings_tree.py
```

## License

MIT — with one exception that must be resolved before public release; see
[ATTRIBUTION.md §5](ATTRIBUTION.md).
