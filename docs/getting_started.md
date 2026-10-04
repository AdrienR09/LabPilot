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

One command, any platform. It starts the backend, settles the front end,
opens the Manager window, and stops all of it together on Ctrl-C or when
you close the window.

| | |
|---|---|
| `labpilot app` | The whole app |
| `labpilot app --no-window` | Backend + front end only; prints a URL for your browser |
| `labpilot app --dev` | Front end from the Vite dev server, with hot reload |
| `labpilot app --build` | Rebuild the front end bundle first |
| `labpilot app --port 8765` | A specific backend port |

The **window** needs the `app` extra, because the base install deliberately
ships no Qt — a headless server, a script or a notebook has no use for it:

```bash
pip install "labpilot[app]"     # or, from a checkout: pip install -e ".[app]"
```

`labpilot app` checks for those packages before it starts anything and names
the ones that are missing. Without them, `labpilot app --no-window` still
gives you the full UI in a browser.

### The front end takes care of itself

There is no separate front-end setup step. Where the UI comes from,
in order:

1. **An installed wheel carries it.** `pip install labpilot` gives you a
   working browser UI with no Node installed anywhere.
2. **From a checkout, the command builds it** — including running
   `npm install` first if `node_modules` is missing. That happens once,
   takes a few minutes, and every launch after it is immediate.
3. **`LABPILOT_FRONTEND`** points at a bundle built elsewhere, if you would
   rather copy one across than install Node on the machine.

If the sources are newer than the bundle, the launcher says so and leaves it
alone — rebuilding unasked would add half a minute to a launch you may have
expected to be instant. `--build` is how you ask; `--dev` skips the bundle
entirely and serves from Vite with hot reload.

A wheel built from a checkout that never ran `npm run build` has no bundled
UI. `scripts/verify_packaging.py` warns when that happens, and
`labpilot app` on such an install says what to do about it.

### Ports

`--port` is a preference, not a demand. If it cannot be bound the launcher
takes one the OS offers and prints which. That matters most on Windows,
where Hyper-V, WSL2 and Docker Desktop reserve blocks of TCP ports at boot
and a bind inside one fails with WinError 10013 while nothing is listening
there. To see the reserved ranges:

```
netsh interface ipv4 show excludedportrange protocol=tcp
```


### Installing Node, if you need it

Only needed to build the front end from a checkout — and never with admin
rights:

```bash
conda install -c conda-forge nodejs      # how this project's own Node is installed
```

Or unzip `node-v*-win-x64.zip` from [nodejs.org/dist](https://nodejs.org/dist/)
and add it to your user PATH.

**Backend only** — useful for headless use, or driving LabPilot from a
script/console without the GUI:

```bash
labpilot start                       # http://localhost:8000
labpilot start --port 8765           # a different port
labpilot start --config-dir <path>   # a different config directory (default: ~/.labpilot)
labpilot list-adapters                # see what's connectable
labpilot list-adapters --tags camera  # filter by DeviceSchema tag
```

> **Setting up a machine that is wired to instruments?**
> [bring_up.md](bring_up.md) is the ordered version of this: which
> vendor drivers each instrument needs, `labpilot rig-init` to declare
> the rig in one command, and `labpilot probe --all` to check the whole
> thing before anything moves.

## Your first real instrument

Before wiring anything into a measurement, ask the instrument to answer for
itself:

```bash
labpilot probe ocean_optics --offline            # what the adapter claims, no hardware
labpilot probe ocean_optics                      # connect, read once, check the claim
labpilot probe keithley_2400 --resource GPIB0::24::INSTR
labpilot probe mock_basic_detector_0d --json     # the same, for a script or a bug report
```

`probe` connects, prints the schema the adapter declares, prints it again once
the device has answered, reads **once**, and reports every place the hardware
disagrees with the declaration — a parameter declared readable that never comes
back, a scalar that reads as an array, a pixel count that is not what the model
table says, a position outside its own declared travel.

**It writes nothing and moves nothing**: only `connect`, `schema`, `read`,
`disconnect`. No setter, no action, no staging. That is what makes it safe to
point at a stage with a sample under the objective, and it is why probing is a
command of its own rather than a flag on something that drives hardware.

It exits 0 when the hardware agrees, 1 when it does not — so a lab machine can
keep the shipped schemas honest in CI — and 2 when it could not get far enough
to tell (unknown adapter, missing vendor package, nothing at that address). Most
adapters' schemas were written from a manual and have never met the instrument
they describe, so a first probe finding something is normal, not alarming.

For NI DAQ cards there is also `scripts/ni_probe.py`, which prints a card's real
channel inventory as a `models.toml` block to paste into your user override —
table data rather than a schema, so it stays a separate script.

## Your first workflow

1. Start everything with `labpilot app`.
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
