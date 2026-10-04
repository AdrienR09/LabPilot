# Troubleshooting

**"Signal timed out" in a Qt window.** Usually means the backend is not
running — check with `curl http://localhost:8000/api/health`. `labpilot app`
starts the backend, the front end and the window together, and restarts all
three.

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

---

## On a lab PC

**`WinError 10013` binding a port, with nothing listening on it.** Hyper-V,
WSL2 and Docker Desktop reserve blocks of TCP ports at boot, and a bind
inside one fails while every "is this port free?" check says it is. See the
reservations with
`netsh interface ipv4 show excludedportrange protocol=tcp`. `labpilot app`
already handles it — it *binds* to test a port rather than connecting, and
picks another when the preferred one is unavailable. Only
`labpilot start --port` needs choosing by hand.

**An instrument is in the catalogue but will not connect.** Almost always a
vendor library that is not installed, and `labpilot probe <adapter>` says
which: a missing driver package is reported as such rather than as a bad
address, because every adapter imports its SDK at connect time, not at
import. [bring_up.md](bring_up.md) lists which instrument needs which
installer.

**`labpilot probe` says the hardware disagrees with the schema.** That is
the probe working. Almost every adapter here was written from a manual and
has never met the instrument it describes, so a first probe finding
something is expected — and the hardware is right. The output names the
disagreement (a parameter declared readable that never came back, a pixel
count that is not what the model table says, a position outside its own
declared travel); that is a report worth sending.

**`labpilot probe --all` says every instrument is unreachable.** Check one
on its own with `--offline` first: if that prints a schema, the adapter and
the config are fine and the problem is drivers or addresses. The TODO
placeholders `labpilot rig-init` leaves behind are reported as unreachable
until they are filled in, which is deliberate — a blank address would read
as "not needed".

**A camera returns something that is not an image.** This was a real, fixed
bug in all nine pylablib camera adapters: an unstaged camera answered
`read()` with a 0-d object array, because pylablib's `read_oldest_image()`
returns `None` when no frame is queued. If you are on an old checkout,
update.

**A sweep against a real microwave source measures a flat line.** Also a
real, fixed bug: `odmr_sweep` never switched the source's output on. It now
calls `cw_on` before the sweep and `off` in a `finally`. On an older
checkout, turn the output on by hand first.
