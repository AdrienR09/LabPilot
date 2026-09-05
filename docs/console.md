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
inst.connected                       # bool
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
