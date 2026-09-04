# Getting Started

## Installation

```bash
# Core + every optional extra (instrument drivers, Qt GUI, CLI, console)
pip install -e ".[full]"
```

Individual extras, if you don't need everything:

| Extra | Adds |
|---|---|
| `pymeasure` | PyMeasure-backed instrument adapters |
| `pylablib` | pylablib-backed instrument adapters |
| `gui` | PyQt6 desktop shell + native instrument windows |
| `cli` | `labpilot` command-line tool |
| `console` | The native IPython console window (see [console.md](console.md)) |
| `dev` | pytest, ruff, mypy |

## Launching

**Everything together** (backend + React dev server + Qt Manager window):

```bash
./launch.sh
```

This activates the `labpilot-dev` conda environment, clears any leftover
process on ports 3000/8000 from a previous run, and starts the backend,
the Vite dev server, and the Manager window together.

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
