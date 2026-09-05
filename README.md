# LabPilot

A data-acquisition framework for laboratory instruments. LabPilot wraps real instrument-control libraries (PyMeasure, pylablib) plus mock/test-fixture devices behind a common adapter interface, so instruments can be discovered, connected, and given an auto-generated UI without writing device-specific GUI code. Instruments can be combined into multi-step workflows; everything is reachable from one manager window — including a native IPython console pre-connected to the running session.

See **[docs/index.md](docs/index.md)** for the full documentation (instruments, workflows, the console, the full API reference, troubleshooting). This README covers setup and internals.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  labpilot.ui.desktop  — desktop shell                       │
│  manager_qt_webview.py: Qt window embedding the React app   │
│  via QWebEngineView, bridged through qt_bridge.py           │
└───────────────────────┬────────────────────────────────────┘
                        │ HTTP + WebSocket (:8000)
┌───────────────────────▼────────────────────────────────────┐
│  labpilot.core.server  — FastAPI backend                    │
│  devices, workflows, config persistence, Qt window spawning │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│  labpilot.instruments  — instrument adapter registry        │
│  organized by manufacturer, then instrument type            │
│  catalog.py: manufacturer/model/dimensionality metadata     │
└────────────────────────────────────────────────────────────┘
```

Everything installable lives under `src/labpilot/`, as one package with three
subpackages. `import labpilot` itself is cheap — it pulls in no subpackage, so
it never triggers the adapter discovery pass `labpilot.instruments` performs on
import.

- **`labpilot.instruments`** — the instrument library. `adapter_registry` is the source of truth for what's connectable; `catalog.py` adds the display metadata (manufacturer, model, 0D/1D/2D/ND classification) the UI needs to pick a window layout. `available_catalog()` narrows that to adapters that actually registered on this machine.
- **`labpilot.core`** — everything non-UI: device schema, session, the workflow engine, storage, config persistence, and the FastAPI server.
  - `device/` — `DeviceSchema` plus the kind-typed `Motor`/`Detector`/`Source`/`Scanner` wrappers `Session.get()` returns.
  - `session.py` / `fsm.py` / `events.py` — `Session` (device registry + event bus), scan lifecycle state machine.
  - `plans/` — linear TOML-serializable scan plans (`ScanPlan`), for simple parameter sweeps.
  - `workflow/` — the workflow engine. A workflow is a Python module exposing `async def run(session) -> dict`; `WorkflowGraph` is its stored record (id, metadata, instrument bindings), not an execution model.
  - `workflow_templates/` — the 14 shipped templates. `workflow_library/` holds the per-instance copy made when one is loaded (generated at runtime, gitignored).
  - `config/` — persistent state under `~/.labpilot`, relocatable with `LABPILOT_HOME` (`config/paths.py`).
  - `storage/` — HDF5 data writer + SQLite run catalogue. Built, not yet wired into the acquisition path.
  - `api/` — the `/api/dashboard/*` router: the instrument manager the Devices tab drives.
  - `server.py` / `cli.py` — the FastAPI app and the `labpilot` CLI.
- **`labpilot.ui`** — everything UI:
  - `desktop/` — the standalone Qt desktop shell (see [src/labpilot/ui/desktop/README.md](src/labpilot/ui/desktop/README.md)). A separate process from `labpilot.core.server`, talking to it over HTTP.

## Running

```bash
./launch.sh
```

Starts the React dev server (`frontend/`, port 3000) and the Qt shell (`src/labpilot/ui/desktop/manager_qt_webview.py`) together; the Qt shell starts and owns its own backend process. See [src/labpilot/ui/desktop/README.md](src/labpilot/ui/desktop/README.md) for how the Qt and React pieces fit together.

To run the backend standalone (needed for workflow execution and the browser at `http://localhost:8000`):

```bash
pip install -e ".[full]"
labpilot start
labpilot list-adapters             # see what's connectable
labpilot list-adapters --tags camera
```

## Instrument adapters

```python
from labpilot.instruments import adapter_registry, INSTRUMENT_CATALOG

adapter_registry.list()                   # {key: AdapterClass} for everything registered
adapter_registry.search(tags=["camera"])  # filter by DeviceSchema tags
INSTRUMENT_CATALOG                        # manufacturer/model/dimensionality metadata
```

`src/labpilot/instruments/` is organized by manufacturer, then instrument type (`<Manufacturer>/<type>.py`) — not by which library backs the adapter. 262 instruments are catalogued across 80 manufacturers: 40 mock, 9 test fixtures, 188 PyMeasure (6 hand-written + 182 auto-generated from every real class in the installed pymeasure library), 25 pylablib. See [src/labpilot/instruments/README.md](src/labpilot/instruments/README.md) for coverage notes, including what's not covered yet (PyMoDAQ).

To add a new instrument, create an adapter under `src/labpilot/instruments/<Manufacturer>/` following `_base.py`'s `AdapterBase`, and add a matching entry to `catalog.py`. `tests/test_adapter_contracts.py` checks that the two agree and that every key your schema declares settable has a working setter.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
