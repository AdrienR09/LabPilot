# LabPilot

A data-acquisition framework for laboratory instruments. LabPilot wraps real instrument-control libraries (PyMeasure, pylablib) plus mock/test-fixture devices behind a common adapter interface, so instruments can be discovered, connected, and given an auto-generated UI without writing device-specific GUI code. Instruments can be combined into multi-step workflows; everything is reachable from one manager window — including a native IPython console pre-connected to the running session.

See **[docs/index.md](docs/index.md)** for the full documentation (instruments, workflows, the console, the full API reference, troubleshooting). This README covers setup and internals.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  src/ui/desktop/  — desktop shell                            │
│  manager_qt_webview.py: Qt window embedding the React app    │
│  via QWebEngineView, bridged through qt_bridge.py             │
└───────────────────────┬────────────────────────────────────┘
                         │ HTTP + WebSocket (:8000)
┌───────────────────────▼────────────────────────────────────┐
│  src/core/server.py  — FastAPI backend                       │
│  devices, workflows, AI chat, config persistence, Qt spawn   │
└───────────────────────┬────────────────────────────────────┘
                         │
┌───────────────────────▼────────────────────────────────────┐
│  src/instruments/  — instrument adapter registry             │
│  organized by manufacturer, then instrument type             │
│  catalog.py: manufacturer/model/dimensionality metadata      │
└────────────────────────────────────────────────────────────┘
```

Everything installable lives under `src/`, as three top-level packages:

- **`src/instruments/`** — the instrument library. `adapter_registry` is the source of truth for what's connectable; `catalog.py` adds the display metadata (manufacturer, model, 0D/1D/2D/ND classification) the UI needs to pick a window layout.
- **`src/core/`** — everything non-UI: device schema, session/FSM, scan plans, the workflow DAG engine, storage, config persistence, the AI assistant, and the FastAPI server.
  - `device/` — `DeviceSchema`/protocols that every adapter implements (readable/settable parameters, units, limits, trigger modes).
  - `session.py` / `fsm.py` / `events.py` — `Session` (device registry + event bus), scan lifecycle state machine.
  - `plans/` — linear TOML-serializable scan plans (`ScanPlan`), for simple parameter sweeps.
  - `workflow/` — general DAG-based experiment workflows (Acquire/Analyse/Branch/Loop/Optimise nodes), used by the AI chat assistant and the workflow editor. A different, more general abstraction than `plans/`, not a duplicate of it.
  - `workflow_library/` — AI-generated workflow files saved via the chatbot.
  - `ai/` — RAG-backed AI assistant that can chat, generate workflows, and drive the `ui.dsl` DSL.
  - `config/` — session persistence (`ConfigPersistence`, JSON under `~/.labpilot/`).
  - `storage/` — HDF5 data writer + SQLite run catalogue.
  - `api/` — the `/api/dashboard/*` router (fake-instrument demo dashboard).
  - `server.py` / `cli.py` — the FastAPI app and the `labpilot` CLI.
- **`src/ui/`** — everything UI:
  - `dsl/` — the DSL the AI assistant uses to spawn Qt windows on demand (plots/controls bound to live device parameters), plus the `QtBridge`/`WindowFactory` that execute it. Runs inside the `core.server` process.
  - `desktop/` — the standalone Qt desktop shell (see [src/ui/desktop/README.md](src/ui/desktop/README.md)). A separate process from `core.server`, talks to it over HTTP.

## Running

```bash
./launch.sh
```

Starts the React dev server (`frontend/`, port 3000) and the Qt shell (`src/ui/desktop/manager_qt_webview.py`) together. See [src/ui/desktop/README.md](src/ui/desktop/README.md) for how the Qt/React pieces fit together, and note the caveat there: the embedded shell currently talks to `qt_bridge.py`'s mock instrument data rather than the real backend — wiring it to `core.server` is the main piece of unfinished integration work.

To run the backend standalone (needed for the AI chat, workflow execution, and the browser at `http://localhost:8000`):

```bash
pip install -e ".[full]"
labpilot start
labpilot list-adapters             # see what's connectable
labpilot list-adapters --tags camera
labpilot check-ollama              # verify the local AI service
```

## Instrument adapters

```python
from instruments import adapter_registry, INSTRUMENT_CATALOG

adapter_registry.list()                   # {key: AdapterClass} for everything registered
adapter_registry.search(tags=["camera"])  # filter by DeviceSchema tags
INSTRUMENT_CATALOG                        # manufacturer/model/dimensionality metadata
```

`src/instruments/` is organized by manufacturer, then instrument type (`<Manufacturer>/<type>.py`) — not by which library backs the adapter. 262 instruments are catalogued across 80 manufacturers: 40 mock, 9 test fixtures, 188 PyMeasure (6 hand-written + 182 auto-generated from every real class in the installed pymeasure library), 25 pylablib. See [src/instruments/README.md](src/instruments/README.md) for coverage notes, including what's not covered yet (PyMoDAQ).

To add a new instrument, create an adapter under `src/instruments/<Manufacturer>/` following `instruments/_base.py`'s `AdapterBase`, and add a matching entry to `instruments/catalog.py`.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
