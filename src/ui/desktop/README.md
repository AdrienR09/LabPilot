# LabPilot Qt Frontend

The desktop shell for LabPilot: a Qt window that embeds the [React manager UI](../../../frontend/) via `QWebEngineView`, plus native PyQt6 windows for individual instruments (real-time PyQtGraph plotting, hardware-accelerated).

## Architecture

```
┌─────────────────────────────────────────────┐
│  Qt QMainWindow (manager_qt_webview.py)      │
│  ┌─────────────────────────────────────────┐ │
│  │ QWebEngineView → React app (:3000)       │ │
│  │  Dashboard / Devices / Workflows / AI /  │ │
│  │  Data / Settings                         │ │
│  └─────────────────────────────────────────┘ │
└───────────────────┬───────────────────────────┘
                     │ QWebChannel bridge (qt_bridge.py)
                     ▼
     hybrid_instrument_windows.py
     → new top-level Qt window per instrument
```

A second, independent path exists for opening a standalone instrument window without the embedded shell: the backend (`core.server`'s `POST /api/instruments/{id}/launch-qt`) spawns `launch_instrument.py`, which runs `main.py --instrument ...` as its own OS process using `instrument_windows.py`. This is the mechanism a browser-only (no Qt shell) deployment would use. Both paths open comparable per-instrument windows but use two separate, independently-maintained window-factory implementations (`hybrid_instrument_windows.py` for the in-process/embedded path, `instrument_windows.py` for the subprocess path) — unifying them is a good next step, not yet done.

## Running

```bash
# from repo root — starts the React dev server, then the Qt shell
./launch.sh
```

This runs `frontend/` (`npm run dev`, port 3000) and then `src/ui/desktop/manager_qt_webview.py`. No backend is required for this flow — `qt_bridge.py` currently serves hardcoded mock instrument/workflow data rather than calling `core.server`. Wiring `QtBridge` to the real backend/adapter registry instead of its mock dicts is the main piece of unfinished work here.

To also exercise the backend-driven standalone-window path (`launch-qt` endpoint), start the server separately:

```bash
labpilot start   # runs core.server, default port 8000
```

## Files

| File | Role |
|---|---|
| `manager_qt_webview.py` | Entry point. Qt window embedding the React app. |
| `qt_bridge.py` | `QtBridge` — QWebChannel object exposed to the React app as `window.qtBridge`; opens instrument windows in-process via `hybrid_instrument_windows`. |
| `hybrid_instrument_windows.py` | Per-instrument Qt window factory used by `qt_bridge.py` (takes a plain dict). |
| `main.py` | Standalone entry point for a single instrument window, invoked as a subprocess (`--instrument`/`--type`/`--dimensionality` args). Not meant to be imported. |
| `launch_instrument.py` | Subprocess launcher for `main.py`, called by `core.server`'s `launch-qt` endpoint. |
| `instrument_windows.py` | Per-instrument Qt window factory used by `main.py` (takes a `DashboardInstrument` dataclass). |
| `session_gui.py` / `session_manager.py` | Save/restore window layout under `~/.labpilot/sessions`, wired into `main.py`'s window menu only. |

## Requirements

```bash
pip install -r requirements.txt   # PyQt6, PyQt6-WebEngine, pyqtgraph, numpy, requests
```
