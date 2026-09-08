# LabPilot Documentation

LabPilot is a data-acquisition framework for laboratory instruments. It
wraps real instrument-control libraries (PyMeasure, pylablib) plus
mock/test-fixture devices behind one common interface (`DeviceSchema`),
auto-generates a UI for anything that implements it, lets you combine
instruments into multi-step **workflows**, and gives you programmatic
access to all of it — from workflow scripts, from a native IPython
console, or from any external process — over one REST/WebSocket API.

LabPilot builds on the design of **Qudi** and **PyMoDAQ**, and its
implementation is **AI-assisted** — see
**[ATTRIBUTION.md](../ATTRIBUTION.md)** for what comes from where, and for
a known licensing issue affecting two vendored theme files.

This is the full documentation, organized like a standard package's docs:
a guide per subsystem, plus a full API reference. Start with **Getting
Started** if this is your first time; jump straight to a section if
you're looking for something specific.

## Contents

1. **[Getting Started](getting_started.md)** — install, launch, run your
   first workflow.
2. **[Capabilities](capabilities.md)** — what the framework can and cannot
   do today, in one page.
3. **[Instruments](instruments.md)** — the `DeviceSchema`/`AdapterBase`
   contract, the instrument catalog, connecting/configuring instruments,
   and writing a new adapter.
4. **[Workflows](workflows.md)** — the script contract
   (`REQUIRED_INSTRUMENTS`/`RESULT_UI`/`CAPABILITIES`), plans, presets,
   running and editing workflows, and writing a new template.
5. **[Console](console.md)** — the native IPython console built into the
   Manager, and its `lp` session object.
6. **[API Reference](api_reference.md)** — every REST endpoint, the
   WebSocket event stream, and the `LabPilotClient`/`LabPilotSession`
   Python API.
7. **[The Manager UI](manager_ui.md)** — a tour of every tab.
8. **[Pulsed measurements](pulsed.md)** — status: **not built yet**, and
   what would be needed.
9. **[Troubleshooting](troubleshooting.md)** — common problems and fixes.

## Architecture at a glance

```
┌────────────────────────────────────────────────────────────┐
│  Manager window (src/labpilot/ui/desktop/)                            │
│  A native Qt window embedding the React app (frontend/)      │
│  via QWebEngineView, plus its own native windows (instrument  │
│  windows, the workflow window, the IPython console)          │
└───────────────────────┬────────────────────────────────────┘
                         │ HTTP + WebSocket (:8000)
┌───────────────────────▼────────────────────────────────────┐
│  LabPilot server (src/labpilot/core/server.py) — FastAPI backend      │
│  Lab (instrument specs + live handles), RunManager, Session   │
│  (event bus + role binding), storage, config persistence      │
└───────────────────────┬────────────────────────────────────┘
                         │
┌───────────────────────▼────────────────────────────────────┐
│  Instrument adapters (src/labpilot/instruments/)                      │
│  one common DeviceSchema interface: readable/settable        │
│  parameters, units, limits — regardless of what library      │
│  (PyMeasure, pylablib, mock) backs the adapter                │
└────────────────────────────────────────────────────────────┘
```

Everything that owns hardware state — instruments, the `Lab`, the running
`Session`, the `RunManager` — lives inside **one backend process**
(`labpilot start`, port 8000 by default). Every other piece (the Qt
Manager window, the React web app, an IPython console, a workflow
script's own `session` parameter) reaches that state either directly
(inside the server process — workflow scripts) or over its REST/
WebSocket API (everything running as a separate process). This is the
single organizing idea behind the whole framework: one authoritative
process, several different front ends onto the same live state.
