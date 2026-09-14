# Troubleshooting

**"Signal timed out" in a Qt window.** Usually means the backend
(`:8000`) and/or the React dev server (`:3000`) aren't running — check
with `curl http://localhost:8000/api/health`, and `./launch.sh` restarts
both together.

**A scan freezes or seems stuck partway through.** Check the toolbar
status label — the Execute button disables itself while a run is
genuinely in progress, so if it's clickable again the previous run
already finished (or failed). If the displayed image looks incomplete on
a *very* large/fast scan, the client periodically re-syncs the full
result from the server as a safety net (every few seconds) — give it a
moment before assuming it's stuck.

**Workflow list is slow to load / times out.** This was a real, fixed
bug: listing workflows used to fetch every workflow's full results blob
just to show a summary row. If you're on an old checkout, update — the
list endpoint no longer does that.

**A workflow won't start with "already running".** Only one execution
per workflow can run at a time — a second start would overlap execution
against the same result buffer, or against the same instrument mid-move.
Stop it first, or wait for it to finish.

**A scan's result array would need N elements... over the safety
limit.** `ScanPlan` refuses to start a grid over 200,000
actuator points, and templates that compute a detector-shape-multiplied
total (like `omniscan.py`) refuse over 50,000,000 elements — both fail
before any hardware motion, with the actual numbers in the error, rather
than thrashing memory for minutes and looking like a hang. Reduce
`AXIS_RANGES`' point counts or the detector's own resolution.

**Console won't open / errors immediately.** The `console` extra
(`qtconsole` + `ipykernel`) isn't installed —
`pip install "labpilot[console]"` (included in `[app]` and `[full]`).

**An instrument connects but every read fails.** Check its schema
(`lp['<id>'].schema` from the console, or the Devices tab) — `read()`
raises if the instrument isn't actually connected yet (HTTP 409); most
mock/real adapters need an explicit `.connect()` first, separate from
just being registered.

**A dashboard-connected instrument isn't visible to a workflow right
after a backend restart.** Instrument-set persistence loads the adapter
but doesn't automatically re-register it into the live session on
startup — reconnect it from the Devices tab (or `lp['<id>'].connect()`)
once after a restart.
