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

**The manager window opens completely dark, with its title stuck at
`Loading 0%`.** The window's title tracks Chromium's load progress, so
`Loading 0%` means the page never arrived — as opposed to a window that
reached `LabPilot Manager ✅` and is *still* dark, which is a rendering
problem rather than a loading one. The window now prints the likely causes
itself after 20 seconds instead of staying silent.

Split it in one step: **open the same URL in a browser** (the terminal prints
it, or use `labpilot app --no-window`). That tells you which half is broken,
and the two halves have nothing in common.

*The browser works too.* Then the server, the port and the bundle are all
fine, and the problem is the embedded Chromium. On a managed or lab PC it is
usually one of:

* **A system proxy.** QtWebEngine picks up the machine's proxy configuration,
  including an auto-detected (WPAD) or PAC one, and a corporate proxy that
  cannot answer for `localhost` stalls the load forever. A browser escapes
  this because its own settings bypass local addresses. `labpilot app` now
  passes `--no-proxy-server`, since the page it loads is served from this
  same machine; on an older checkout, `git pull`.
* **Security software blocking `QtWebEngineProcess.exe`.** Chromium renders
  in a child process, and a blocked one leaves the window blank with no error
  anywhere. Look for it in Task Manager while the window is open: if it is
  not there, that is the answer, and it needs an exclusion.
* **A graphics driver QtWebEngine cannot use**, or a remote-desktop session.
  Try `labpilot app --safe-graphics`, which renders without the GPU.

Until it is sorted, `labpilot app --no-window` is a complete workaround —
the browser UI is the same application, not a reduced one.

*The browser is blank as well.* Then the page itself is at fault: the front
end is not built (`labpilot app --build`), or it is waiting on a resource it
cannot reach. That last one was a real, fixed bug — the built `index.html`
loaded two webfont stylesheets from `fonts.googleapis.com` with a plain
`rel="stylesheet"`, which is render-blocking, so on a PC with no internet
Chromium painted nothing while it waited. They are now loaded non-blocking
and the app falls back to `system-ui`. On an older checkout, `git pull` and
`labpilot app --build`.

**`FileExistsError: [WinError 183]` saving a config, naming a `.cfg.tmp`
file.** A fixed bug, Windows-only. All four config stores write to a `.tmp`
file and move it into place, and they made the move with `Path.rename` —
which, unlike `Path.replace`, cannot overwrite an existing target on Windows.
So the *second* save of any config failed: adding a second instrument, saving
a workflow set, or changing a template parameter. The failure was worse than
the traceback suggested, because the new content stayed stranded in the
`.tmp` file while the old content remained in place. `git pull` fixes it, and
the stale `.tmp` is picked up and consumed by the next save — nothing to
clean up by hand.

**`WinError 10013` binding a port, with nothing listening on it.** Hyper-V,
WSL2 and Docker Desktop reserve blocks of TCP ports at boot, and a bind
inside one fails while every "is this port free?" check says it is. See the
reservations with
`netsh interface ipv4 show excludedportrange protocol=tcp`. `labpilot app`
already handles it — it *binds* to test a port rather than connecting, and
picks another when the preferred one is unavailable. Only
`labpilot start --port` needs choosing by hand.

**An instrument is in the catalogue but will not connect.** Almost always a
vendor library that is not installed. The reason travels in the HTTP 502's
body, which the browser UI shows and the terminal does not — so `labpilot
probe <adapter>` is the quickest way to read it, and the server now logs it
as a `WARNING` with its traceback as well. A missing driver package is
reported as such rather than as a bad address, because every adapter imports
its SDK at connect time, not at import. [bring_up.md](bring_up.md) lists which
instrument needs which installer.

**A Mad City Labs stage will not connect, and `Madlib.dll` is installed.**
Check the word size. MCL ship a 32-bit and a 64-bit build, and loading the
wrong one into Python fails with `WinError 193`, whose own wording — "not a
valid Win32 application" — suggests a corrupt file rather than an
architecture mismatch. The adapter now searches
`C:\Program Files (x86)\Mad City Labs\…` as well, precisely so a 32-bit
install is *found* and reported as the wrong word size instead of as a
missing file, and the error names the interpreter's own word size. Either
install the matching build or run LabPilot under the Python that matches the
library you have.

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
