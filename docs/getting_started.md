# Getting Started

## Installation

```bash
pip install labpilot            # the framework, the server and the CLI
pip install "labpilot[app]"     # plus the Qt desktop app and its console
```

`labpilot` on its own runs every mock instrument, serves the API, and is
enough to write and run acquisition scripts. Driver libraries are extras:

| Extra | Adds |
|---|---|
| `app` | The Qt desktop shell, its windows and its console — `gui` + `console` |
| `gui` | PyQt6, pyqtgraph, pymodaq_gui |
| `console` | The native IPython console window (see [console.md](console.md)) |
| `pymeasure` | PyMeasure-backed instrument adapters |
| `pylablib` | pylablib-backed instrument adapters |
| `ni` | NI DAQ cards. No macOS build exists — NI ships DAQmx for Windows and Linux only |
| `ni-fpga` | NI R-Series FPGA cards, via nifpga (also needs the NI-RIO driver) |
| `oceanoptics` | Ocean Optics / Ocean Insight spectrometers, via seabreeze |
| `swabian` | The Swabian Pulse Streamer |
| `spincore` | The SpinCore PulseBlaster (also needs the vendor driver) |
| `full` | Everything that installs cleanly from PyPI on any platform |
| `dev` | pytest, ruff, mypy, build |

There is no `cli` extra: `labpilot start` and `labpilot list-adapters` are
argparse, so the command-line tool is in the base install.

Every adapter imports its driver inside the method that needs it, so a
missing extra costs a clear error when you connect *that* instrument and
nothing at all otherwise. `labpilot list-adapters` lists all of them either
way, because an adapter describes itself without its driver.

Working from a checkout instead:

```bash
pip install -e ".[dev,app]"
```

## Launching

**Everything together** (backend + front end + Manager window):

```bash
labpilot app
```

One command, any platform. It starts the backend, serves the front end,
opens the Manager window, and stops all of it together on Ctrl-C or when
you close the window.

| | |
|---|---|
| `labpilot app` | The whole app |
| `labpilot app --no-window` | Backend + front end only; prints a URL for your browser |
| `labpilot app --dev` | Front end from the Vite dev server, with hot reload |
| `labpilot app --build` | Rebuild the front end bundle first |
| `labpilot app --port 8765` | A specific backend port |

The front end comes from the **built** bundle when there is one, which
needs no Node installed. A fresh checkout has to build it once:

```bash
cd frontend && npm install && npm run build
```

Until you do, `labpilot app` falls back to the Vite dev server — same
result, but it needs npm.

Ports: `--port` is a preference, not a demand. If it cannot be bound the
launcher takes one the OS offers and prints which. That matters most on
Windows, where Hyper-V, WSL2 and Docker Desktop reserve blocks of TCP
ports at boot and a bind inside one fails with WinError 10013 while
nothing is listening there. To see the reserved ranges:

```
netsh interface ipv4 show excludedportrange protocol=tcp
```

`./launch.sh` predates this command and does the same thing for a
macOS/conda checkout only. Prefer `labpilot app`.

**Backend only** — useful for headless use, or driving LabPilot from a
script/console without the GUI:

```bash
labpilot start                       # http://localhost:8000
labpilot start --port 8765           # a different port
labpilot start --config-dir <path>   # a different config directory (default: ~/.labpilot)
labpilot list-adapters                # see what's connectable
labpilot list-adapters --tags camera  # filter by DeviceSchema tag
```

## Your first workflow

1. Start everything with `./launch.sh`.
2. In the Manager's **Devices** tab, connect a couple of mock instruments
   (no real hardware needed — LabPilot ships mock adapters for exactly
   this) — e.g. a mock XYZ stage and a mock detector.
3. In the **Workflows** tab, click **Templates…** and load `omniscan` (a
   generalized N-D actuator/detector scan — see
   [workflows.md](workflows.md)).
4. Bind its instrument roles to the two instruments you just connected.
5. Click **Execute** in the workflow window's toolbar. Watch the result
   view update live as the scan progresses.

From here:
- [instruments.md](instruments.md) covers connecting real hardware and
  writing your own adapter.
- [workflows.md](workflows.md) covers every built-in template and how to
  write your own.
- [console.md](console.md) covers driving all of this from a live IPython
  console instead of the GUI — the same `omniscan` run above, from code:

  ```python
  wf = lp.workflow('<the workflow id shown in the Workflows tab>')
  wf.set_param('AXIS_RANGES', {'x': [-2.0, 2.0, 40], 'y': [-2.0, 2.0, 40]})
  wf.run()
  result = wf.wait()
  ```
