# The Manager UI

The Manager is a native Qt window (`src/ui/desktop/manager_qt_webview.py`)
embedding the React app (`frontend/`) via `QWebEngineView`, plus its own
native toolbar and windows for things that don't belong inside the
embedded web page.

## Sidebar tabs

| Tab | What it's for |
|---|---|
| **Dashboard** | Session status: backend connection, devices connected, workflows running |
| **Devices** | Browse the instrument catalog, connect/disconnect instruments, open a live instrument window — see [instruments.md](instruments.md) |
| **Workflows** | List, load, and run workflows; edit their scripts and parameters — see [workflows.md](workflows.md) |
| **Flow Chart** | Node-graph view/editor for a workflow's DAG |
| **Data** | Data visualization (in progress) |
| **Settings** | Session/instrument configuration |

## Toolbar

**Console** opens a native IPython console window pre-connected to this
session — see [console.md](console.md).

## Instrument windows

Connecting an instrument (Devices tab) or clicking through to it opens a
separate native Qt window, auto-generated from that instrument's
`DeviceSchema` and dimensionality (0D scalar readout + controls, 1D/2D/ND
live plot, settings editable from the same window).

## The workflow window

Executing or opening a workflow opens its own native window
(`src/ui/desktop/workflow_window.py`) with:

- An **Execute**/**Stop** toolbar pair (Execute disables itself while a
  run is in progress) and a **Save** action exporting every visible scan
  panel as PNG.
- A live result view shaped by the workflow's `RESULT_UI` (see
  [workflows.md](workflows.md)) — a spectrum plot, a 2D image with an
  optional crosshair, or an N-dimensional scan viewer with one 2D
  projection panel per axis pair plus a per-channel 1D projection.
- Each 2D image panel has its own colorbar sidebar: a colormap picker,
  a draggable histogram, and numeric min/max fields — dragging a level
  or typing a number pins that panel out of auto-level until turned back
  on from the Settings menu.
- An **Optimize** toggle (when the workflow declares a crosshair) that
  re-centers the bound actuator on the detector's local maximum around
  the current position.
- Axes controls and the crosshair are hidden while a scan is actively
  running (they'd otherwise fight the scan's own actuator moves) and
  reappear once it stops.

## What used to be here

Two earlier iterations of this UI are documented for context, not
because they're still present:

- An **AI Assistant** tab (chat backed by a local Ollama model, workflow
  generation, a Qt-window-spawning DSL) existed and was removed. The
  underlying `core/ai/` module and DSL code are still in the tree
  (unwired) — see git history on the `main` branch for the last commit
  where it was active, if you need to bring it back.
- A **Notebook** tab embedded a full Jupyter server (file browser +
  notebook UI) in an iframe. It was replaced by the native Console
  toolbar button above — lighter (no Jupyter server process), and
  consistent with how every other native window in this app works.
