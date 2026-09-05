# LabPilot Qt Frontend

The desktop shell for LabPilot: a Qt window that embeds the [React manager UI](../../../frontend/) via `QWebEngineView`, plus native PyQt6 windows for individual instruments (real-time PyQtGraph plotting, hardware-accelerated).

## Architecture

```
┌─────────────────────────────────────────────┐
│  Qt QMainWindow (manager_qt_webview.py)      │
│  ┌─────────────────────────────────────────┐ │
│  │ QWebEngineView → React app (:3000)       │ │
│  │  Dashboard / Devices / Workflows /       │ │
│  │  Flow / Data / Settings                  │ │
│  └─────────────────────────────────────────┘ │
└───────────────────┬───────────────────────────┘
                     │ QWebChannel bridge (qt_bridge.py)
                     ▼
     launch_instrument.py / launch_workflow.py
     → one OS process per window
```

Windows are always separate processes. The React app calls
`qtBridge.launchInstrumentUI(id)` / `launchWorkflowUI(id)`, which spawn
`main.py --instrument ...` (or the workflow equivalent); the backend's
`POST /api/instruments/{id}/launch-qt` spawns exactly the same thing, which is
how a browser-only deployment opens a native window. Each window fetches what
it needs from the backend by id — the bridge carries no instrument data.

## Running

```bash
# from repo root — starts the React dev server, then the Qt shell
./launch.sh
```

This runs `frontend/` (`npm run dev`, port 3000) and then
`src/labpilot/ui/desktop/manager_qt_webview.py`, which starts and owns its own
backend process (`managed_server.py`) and waits for it to be ready before the
window opens. Pass `--external-backend` to point it at an already-running or
remote server instead.

To run the backend on its own:

```bash
labpilot start   # runs labpilot.core.server, default port 8000
```

## Files

| File | Role |
|---|---|
| `manager_qt_webview.py` | Entry point. Qt window embedding the React app. |
| `qt_bridge.py` | `QtBridge` — QWebChannel object exposed to the React app as `window.qtBridge`. Two slots only: `launchInstrumentUI` / `launchWorkflowUI`. Carries no instrument data. |
| `managed_server.py` | Starts and owns the backend subprocess for the manager window. |
| `main.py` | Standalone entry point for a single instrument window, invoked as a subprocess (`--instrument`/`--type`/`--dimensionality` args). Not meant to be imported. |
| `launch_instrument.py` / `launch_workflow.py` | Subprocess launchers for `main.py`, called by `qt_bridge.py` and by `labpilot.core.server`'s `launch-qt` endpoint. |
| `instrument_windows.py` | Per-instrument Qt window factory used by `main.py` (takes a `DashboardInstrument` dataclass). |
| `session_gui.py` / `session_manager.py` | Save/restore window layout under `~/.labpilot/sessions`, wired into `main.py`'s window menu only. |

## Requirements

```bash
pip install -r requirements.txt   # PyQt6, PyQt6-WebEngine, pyqtgraph, numpy, requests
```
