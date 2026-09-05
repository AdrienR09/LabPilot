# API Reference

Every REST endpoint returns the same envelope:

```json
{"success": true, "data": {...}, "error": null, "timestamp": 1234567890.1}
```

`success: false` responses carry an HTTP 4xx/5xx status and put a message
in `error`/the HTTP body's `detail`.

## Python client

Two layers, both in `src/labpilot/core/`:

- **`api_client.LabPilotClient`** — thin, synchronous `httpx`-based
  wrapper, one method per endpoint below. No Qt dependency; usable from
  any script.
- **`notebook_api.LabPilotSession`** (what the console's `lp` is) — a
  friendlier layer on top, with `lp[id]`/`lp.workflow(id)` handles. See
  [console.md](console.md) for its full surface.

```python
from labpilot.core.api_client import LabPilotClient
client = LabPilotClient("http://localhost:8000")
client.list_instruments()
```

The desktop app's `src/labpilot/ui/desktop/backend_client.py` re-exports
`LabPilotClient` as `BackendClient` (its historical name there) and adds
a Qt-signal-based `WorkflowStatePoller` on top for live GUI updates.

## Session & devices

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/api/health` | `{"status": "healthy"}` |
| GET | `/api/session/status` | `{session_id, devices_connected, workflow_engine_running}` |
| GET | `/api/session/config` | Full session config (devices, preferences, recent scans) |
| GET | `/api/config` | Config summary |
| POST | `/api/config/save` | Persist current session config to disk |
| GET | `/api/devices` | Legacy plain device list (see the dashboard API below for the one the UI actually uses) |
| POST | `/api/devices/connect` | Legacy connect |
| DELETE | `/api/devices/{name}` | Legacy disconnect |

## Instruments (`/api/dashboard/...`)

The dashboard router is what the Devices tab and `LabPilotClient` both
actually use — a separate, richer instrument registry from the legacy
`/api/devices` above.

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/api/dashboard/state` | Full dashboard state |
| GET | `/api/dashboard/instruments` | Every registered instrument's status |
| GET | `/api/dashboard/instruments/{id}/schema` | That instrument's `DeviceSchema` |
| GET | `/api/dashboard/instruments/{id}/data` | Current readable values (409 if not connected) |
| POST | `/api/dashboard/instruments/{id}/settings` | `{"values": {...}}` — write settable params |
| GET/POST | `/api/dashboard/instruments/{id}/ui_prefs` | Native-UI display preferences (`use_slider`, ...) |
| GET | `/api/dashboard/instruments/{id}/ui_prefs_schema` | What preferences this instrument type declares |
| GET | `/api/dashboard/catalog` | The full instrument catalog (see [instruments.md](instruments.md)) |
| POST | `/api/dashboard/instruments` | Create a new instrument from a catalog key |
| POST | `/api/dashboard/instruments/{id}/connect` | |
| POST | `/api/dashboard/instruments/{id}/disconnect` | |
| PATCH | `/api/dashboard/instruments/{id}/connection` | Update connection params |
| DELETE | `/api/dashboard/instruments/{id}` | Remove |
| GET | `/api/dashboard/configs` | List saved instrument-set configs |
| POST | `/api/dashboard/configs/new` | Create a blank one |
| POST | `/api/dashboard/configs/upload` | Import a full instrument-set |
| POST | `/api/dashboard/configs/{name}/activate` | Switch the active set |
| DELETE | `/api/dashboard/configs/{name}` | |

## Workflows

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/api/workflows` | List, with `last_status` from the most recent execution |
| POST | `/api/workflows` | Create a blank workflow |
| GET | `/api/workflows/templates` | The 14 built-in templates (see [workflows.md](workflows.md)) |
| POST | `/api/workflows/templates/{name}/load` | Load one as a new workflow |
| POST | `/api/workflows/load` | Load a workflow from an arbitrary script path |
| GET | `/api/workflows/{id}` | Full graph (nodes/edges/metadata) |
| DELETE | `/api/workflows/{id}` | Unload from the active workflow-set (doesn't delete the script/history) |
| GET/PUT | `/api/workflows/{id}/script` | Raw script text |
| GET | `/api/workflows/{id}/params` | This workflow's tunable constants |
| PUT | `/api/workflows/{id}/params/{name}` | `{"value": ...}` |
| GET | `/api/workflows/{id}/bindings` | Instrument-role bindings |
| PUT | `/api/workflows/{id}/bindings/{role}` | Bind a role to a real instrument id |
| POST | `/api/workflows/{id}/execute` | Start execution — 400 if already running |
| POST | `/api/workflows/{id}/stop` | Cancel a running execution |
| GET | `/api/workflows/{id}/execution_state` | Live progress (while running) + last-completed status/results |
| POST | `/api/workflows/{id}/optimize/start` | `{axes?, ranges?, points?, points_per_axis?}` — see [workflows.md](workflows.md)'s `OptimizerCapability` |
| POST | `/api/workflows/{id}/optimize/stop` | |
| GET | `/api/workflows/{id}/optimize/state` | `{running, progress, last_result, error}` |

## WebSocket (`/ws`)

One shared connection, broadcasting every server-side event as
`{"type": "event", "event": {"kind": ..., "data": {...}}}`. The kinds a
client actually needs to handle for live workflow display:

| Kind | Data | When |
|---|---|---|
| `WORKFLOW_STARTED` | `{workflow_id, execution_id, name}` | Execution begins |
| `WORKFLOW_PROGRESS` | The `session.report_progress()` payload, large fields (>4096 elements) stripped | Every `report_progress()` call — a "something changed" signal; re-fetch `execution_state` for the full snapshot |
| `READING` | The `session.report_reading()` payload, always small | Every `report_reading()` call, for templates that use it |
| `WORKFLOW_COMPLETED` | `{results}` | Run finishes successfully |
| `WORKFLOW_ERROR` | `{error}` | Run raises |
| `WORKFLOW_STOPPED` | `{}` | Cancelled via `/stop` |

`WorkflowStatePoller` (`src/labpilot/ui/desktop/backend_client.py`) is the
reference client implementation — it maintains a local buffer from
`READING` events (cheap, applied instantly, no refetch) and periodically
self-heals it from the always-authoritative `execution_state` REST
snapshot as a safety net against any dropped WebSocket message.

## Qt window launch

| Method | Endpoint | Notes |
|---|---|---|
| POST | `/api/instruments/{id}/launch-qt` | Spawns a native instrument window as a subprocess |
