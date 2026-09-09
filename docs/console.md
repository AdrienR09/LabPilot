# Console

The Manager has a **Console** toolbar button — a native IPython console
window, LabPilot's equivalent of Qudi's own embedded IPython console. It
opens a real, out-of-process IPython kernel in a native Qt widget
(`qtconsole`'s `RichJupyterWidget`), auto-connected to this running
session as `lp` — no `import` needed, no separate server to start.

## Why an API client, not direct object access

Instruments and the running `Session` are live objects owned by the
backend server process (open hardware handles, an asyncio event loop).
The console's kernel is a separate OS process and can't share those
objects directly — `lp` reaches them exactly the way the desktop app and
the web UI already do: over the backend's REST/WebSocket API. Writing an
instrument setting from the console moves the same real instrument the
Devices tab shows; a workflow you start from the console shows up as
`running` in the GUI, and vice versa.

## Opening it

Click **Console** in the Manager's toolbar. A new window opens with a
fresh IPython kernel — closing the window shuts that kernel down; opening
Console again starts a new one.

## The `lp` API

`lp[id]` returns a handle typed by the instrument's kind — `Motor`,
`Detector`, `Source` — carrying **the same methods a workflow template
gets** from `session.get(role)` (see [Scripting](scripting.md)). The
difference is only the transport: in a template the wrapper holds the
adapter and its methods are awaited; here each call is a REST round trip
and blocks, which is what an interactive prompt wants.

`lp[id]` raises straight away for an unknown id, with a suggestion. A
registered instrument's id carries a numeric suffix — `fake_apd_2`, not
`fake_apd` — so reaching for the adapter's name is the usual slip.

```python
lp.instruments                       # ['mock_xyz_stage_2', 'fake_apd_8', ...] every registered id
lp['fake_apd_8'].read()              # {'counts': 1023.4} — current readable values
lp['fake_apd_8'].schema              # parameters with dtypes, units, limits, roles, tags
lp['mock_xyz_stage_2'].write(x=1.0, y=0.5)   # set one or more settable values
lp['mock_xyz_stage_2'].connect()     # connect it if it isn't already
lp['mock_xyz_stage_2'].disconnect()

# Every device
inst.stage(); inst.unstage()         # bracket an acquisition
inst.call('cw_on')                   # invoke one of inst.actions
inst.call('configure', bin_width_s=1e-9, gates=50)   # with arguments; returns what
                                     # the hardware actually applied
inst.connected                       # bool
inst.actions                         # ['cw_on', 'off', ...] — the names
inst.action_specs                    # full records: each action's declared arguments,
                                     # their units and limits, and what it reports back
inst.parameters                      # full Parameter records: role, unit, limits, choices, tags

# Motors (kind="motor")
stage.axes                           # ['x', 'y', 'z'] — positions only, not settings like velocity
stage.move_abs(x=1.0, y=0.5)         # blocks until settled
stage.move_abs('x', 1.0)             # or move_abs(1.0) on a single-axis device
stage.move_rel(x=0.1)                # relative to where it is now
stage.get_position()                 # {'x': 1.0, ...}, or a float for a single-axis device

# Detectors (kind="detector" or "counter")
apd.read_value()                     # one scalar reading
apd.acquire_once()                   # stage -> read -> unstage
apd.set_integration_time(50.0)       # however this device spells it, in its own unit

lp.scan(over={'stage.x': (0, 10, 51)}, read='apd')   # a run, without writing a workflow
lp.runs                              # every saved run, newest first
lp.run('<id>')                       # a handle on a run already in flight

lp.workflows                         # ['641a113f-...', ...] every loaded workflow's id
wf = lp.workflow('641a113f-...')
wf.params                            # this workflow's own tunable parameters
wf.set_param('AXIS_RANGES', {'x': [-4.0, 4.0, 20], 'y': [-4.0, 4.0, 20]})
wf.script                            # the workflow's Python source, as text
wf.run()                             # starts execution, returns immediately
wf.state()                           # {'running': ..., 'progress': ..., 'last_results': ...}
wf.wait()                            # blocks until the current run finishes, returns final state
wf.stop()                            # cancel a running execution

lp.client                            # the underlying core.api_client.LabPilotClient,
                                      # for anything not wrapped above (see api_reference.md)
```

### Writing an acquisition loop

The point of the handles above is that a loop you type at the prompt is
the loop a template writes, minus the `await`:

```python
import numpy as np

apd = lp['fake_apd_8']
stage = lp['mock_xyz_stage_2']

apd.set_integration_time(20.0)
apd.stage()
try:
    trace = [(x, stage.move_abs(x=x), apd.read_value()) for x in np.linspace(0, 10, 51)]
finally:
    apd.unstage()
```

### Running a scan without writing one

You do not have to type the loop at all. `lp.scan(...)` starts a real run
on the server — the same `ScanPlan` a template builds, executed by the
same engine on the same worker thread:

```python
run = lp.scan(over={'mock_xyz_stage_2.x': (0, 10, 51)}, read='fake_apd_8')
run.progress                          # (points measured, points planned)
run.wait()                            # blocks until it finishes
run.result()['data']                  # the flat result, as a template returns it
```

Name each axis as `instrument.parameter`, or once with `using=`. Axes
vary in the order given, the first slowest:

```python
run = lp.scan(
    over={'x': (-5, 5, 101), 'y': (-5, 5, 101)},
    using='mock_xyz_stage_2',
    read='fake_apd_8',
    hold={'z': 1.2},                  # park the axes this scan is not sweeping
)
```

Because it is a run and not a console-side loop, it has the controls a
run has — and they mean what they say. `pause()` holds at a **point
boundary**, so the detector is never left staged mid-integration and the
stage is at a known position; `abort()` stops there too, tells the
actuators to stop, and keeps the points already measured:

```python
run.pause(); run.resume()
run.abort()                           # keeps what it measured
run.result()['data']                  # the partial scan, untaken points None
```

Every run is written to HDF5 and indexed as it finishes, whether it came
from here or from the Workflows tab:

```python
lp.runs[0]                            # the newest saved run
run.result().to_hdf5('scan.h5')       # or write a copy wherever you like
```

### One plan, both places

`lp.scan(...)` is a convenience over `lp.execute(plan)`, and a plan is an
ordinary object. The same one runs at the console and inside a template,
differing by the `await` and nothing else:

```python
from labpilot.core.run import ScanAxis, ScanPlan
plan = ScanPlan([ScanAxis('x', 'mock_xyz_stage_2', 0, 10, 51)], detector='fake_apd_8')

lp.execute(plan)                 # console, notebook
await session.execute(plan)      # inside a workflow template
```

Instruments live in the server process, so the plan is not shipped as an
object — its fields are, and the server rebuilds it. That is the same
boundary every other console call crosses: one API over two transports,
not two APIs.

Which plans can cross it is declared by the plans themselves
(`core/run/requests.py`), so `lp.execute` grows no branch per plan type.
`lp.runs`-visible today: `ScanPlan`, `TimeSeriesPlan` and
`PulsedMeasurementPlan`.

### Pulsed measurements

A sequence is pure data — no hardware, no connection, no server — so
`lp.pulse` runs in the console's own process and hands back an object you
can inspect and save before any pulser exists to play it:

```python
seq = lp.pulse.rabi(tau=(20e-9, 2e-6, 50), rabi_period=180e-9)
seq.points, seq.readouts(), seq.duration
lp.pulse.saved()                      # ~/.labpilot/sequences/
```

`tau=(start, stop, points)` is sugar over whichever pair of parameters the
generator declares — a linear sweep takes a step, a log-spaced T1 takes an
endpoint — and rig physics (`rabi_period`, `laser_length`, `mw_channel`)
is passed in the same argument list, because at a console that is what it
is.

Playing one is a run like any other:

```python
run = lp.pulsed(seq, pulser='pulse_streamer', counter='tt', sweeps=2000,
                channels={'laser': 'd_ch1', 'mw': 'a_ch1', 'gate': 'd_ch2'})
run.wait().result().to_hdf5('rabi.h5')
```

`channels` maps the sequence's symbolic channels onto this rig's physical
ones — the one genuinely rig-specific thing, which is why it lives with
the run rather than in the saved sequence file.

The result is 2-D, `(sweeps, tau)`: nothing moves between points, so the
axis the run iterates is accumulation and each row is the curve after that
many passes. The last row is the answer; the rest show whether it had
converged. See [pulsed.md](pulsed.md).

`result()` is the plain dict a template returns *and* a `Dataset`, so
`result()['shape']` works and so does `result().primary().unit`. The
HDF5 it writes carries units and axis coordinates as dimension scales,
which h5py, xarray and MATLAB all read.

Values are validated against the device's own limits before they reach
hardware, so an out-of-range setpoint raises here rather than being sent:

```python
>>> apd.set_integration_time(1e12)
HTTPStatusError: 422 ... 1000000000000.0 is outside the limits [1.0, 5000.0] ms
```

### Workflows

A typical session — run a scan and plot the result once it's done:

```python
wf = lp.workflow('641a113f-7c42-4872-9826-a636c8810cdf')
wf.set_param('AXIS_RANGES', {'x': [-2.0, 2.0, 40], 'y': [-2.0, 2.0, 40]})
wf.run()
result = wf.wait()

import numpy as np, matplotlib.pyplot as plt
data = np.array(result['last_results']['data']).reshape(result['last_results']['shape'])
plt.imshow(data)
```

## Requirements

The `console` extra (`pip install -e ".[console]"` — included in
`[full]`): `qtconsole` + `ipykernel`. If it's missing, the toolbar action
will fail to open with an error naming what to install.

## How it's wired (for reference)

`src/labpilot/ui/desktop/console_window.py`'s `ConsoleWindow` launches a real
`ipykernel` process (`QtKernelManager` with an explicit `kernel_cmd` — no
Jupyter server, no kernelspec registration needed) with its `IPYTHONDIR`
pointed at a small generated IPython profile whose `startup/00-labpilot.py`
constructs `lp = LabPilotSession()` (`core/notebook_api.py`) the moment
the kernel starts — the same auto-connect mechanism, just triggered by
IPython's own startup-file convention instead of anything console-window–
specific.
