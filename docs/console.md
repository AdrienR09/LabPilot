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

```python
lp.instruments                       # ['mock_xyz_stage_2', 'fake_apd_8', ...] every registered id
lp['fake_apd_8'].read()              # {'counts': 1023.4} — current readable values
lp['fake_apd_8'].schema              # readable/settable param names, dtypes, units, limits
lp['mock_xyz_stage_2'].write(x=1.0, y=0.5)   # set one or more settable values
lp['mock_xyz_stage_2'].connect()     # connect it if it isn't already

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
