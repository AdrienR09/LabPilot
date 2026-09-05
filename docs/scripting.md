# Scripting

`session.get(role)` (see [Workflows](workflows.md#instrument-roles)) returns
a **kind-typed wrapper** — `Motor`, `Detector`, `Source`, `Scanner`, or
`GenericInstrument` (`src/labpilot/core/device/kinds.py`), chosen from the bound
instrument's own `schema.kind` (see [Instruments](instruments.md)). This is
what lets a script call `actuator.move_abs(x=1.0, y=2.0)` /
`await detector.read_value()` — the same method names regardless of which
manufacturer's adapter is actually bound — instead of hand-writing generic
`write({...})`/`read()` dict calls against every instrument. Every wrapper
still exposes that same `.read()`/`.write()`/`.schema`/`.stage()`/
`.unstage()` surface too (plus `__getattr__` passthrough for anything
adapter-specific), so this is purely additive — existing scripts that only
ever used the raw dict calls keep working with zero changes.

`for` loops, `if`/`else`, `while` — ordinary Python. `run(session)` is a
plain `async def`; nothing about control flow is special here, only the
objects you call methods on.

## `Motor` (`kind="motor"`)

```python
actuator = session.get("xy_actuator")
actuator.axes                              # -> ["x", "y"] (or ["position"] for a single-axis stage)
await actuator.get_position()              # -> {"x": 1.0, "y": 2.0} (or a plain float if there's one axis)
await actuator.get_position("x")           # -> 1.0
await actuator.move_abs(x=1.0, y=2.0)      # blocks until settled; moves only the axes given
await actuator.move_rel(x=0.5)             # delta from the current position
```

A genuinely single-axis motor (e.g. a grating position, or `MockMotor`'s
`"position"`) takes a bare value instead of naming the axis:

```python
grating = session.get("grating")
grating.axes                    # -> ["position"]
await grating.move_abs(12.5)    # -> 12.5
await grating.get_position()    # -> 12.5 (a float, not a dict — there's only one axis)
```

`move_abs("x", 1.0)` (axis name + value as two positional args) also works,
equivalent to `move_abs(x=1.0)`. Calling the single-value form on a
multi-axis motor raises `TypeError` naming the real axes, rather than
guessing which one you meant. `tolerance`/`max_polls` keyword arguments
(defaults `0.02`/`5000`) control the settle-wait, same as
`core.device.motion.move_and_settle` always has.

A motor with no continuous axis at all (e.g. a plain two-state switch,
`readable=settable={"state": "bool"}`) has `axes == []` — `get_position()`
returns `{}`, and `move_abs()` raises a clear `TypeError` rather than
guessing; use `.write({"state": True})`/`.read()` directly for that case.

## `Detector` (`kind="detector"` or `"counter"`)

```python
detector = session.get("detector")
value = await detector.read_value()          # one scalar — the first readable key by default
value = await detector.read_value("counts")  # or name the key explicitly
await detector.set_integration_time(50.0)    # ms — looks up whichever settable key names it
data = await detector.acquire_once()         # stage() -> read() -> unstage(), for one reading
```

`read_value()` raises `ValueError` if that key isn't actually scalar (a
1D/2D/ND detector) — use `.read()` directly and index into the array
yourself in that case; `core.workflow_templates._common.detector_axes`
already handles an arbitrary-rank detector reading generically, the same
helper every built-in template with a non-scalar detector uses.

`acquire_once()` is for a single one-shot reading — not appropriate around
a whole averaged-sweep loop that needs to stay staged across many reads
(see `odmr_sweep.py`, which calls `stage()`/`unstage()` manually around its
whole sweep instead).

## `Source` (`kind="source"`)

Deliberately thin beyond passthrough — there's no generalizable
`enable()`/`disable()`: some real sources use a zero-arg `schema.actions`
method (`cw_on()`/`off()`) instead of a settable on/off key, some have no
on/off concept at all (just a numeric output). The real control surface
stays `.write({...})` for settable values, plus whichever action names
`.actions` lists (reachable directly as a method, via passthrough):

```python
source = session.get("source")
source.actions                    # -> ["cw_on", "scan_on", "off", "reset_scan", "trigger_next"]
await source.write({"cw_frequency": 2.87e9})
await source.cw_on()              # a schema.actions method, called directly (passthrough)
```

## `Scanner` (`kind="generic"`, hardware-timed)

A hardware-timed scanner (an NI DAQ card, or the mock equivalent) — a
different control shape entirely from move+read, since the device clocks
its own position waveform and detector readback together:

```python
scanner = session.get("scanner")
await scanner.configure_scan(["x", "y"], {"x": (0.0, 50.0), "y": (0.0, 50.0)}, {"x": 200, "y": 200}, 5000.0)
await scanner.start_scan()
chunk = await scanner.get_scan_data()   # poll until chunk["done"]
await scanner.stop_scan()
```

In practice you won't call these directly — `core.workflow.capabilities`'s
`HardwareTimedScanCapability` (used by `omniscan.py`'s `scanner` role) already
drives this whole poll loop for you.

## `GenericInstrument` and escape hatches

A `kind="generic"` device that isn't a hardware-timed scanner (e.g. a pulse
sequencer) wraps as `GenericInstrument` — passthrough only, no extra
methods. `session.get_raw(role)` returns the literal unwrapped adapter, for
the rare case you need its own identity or an attribute the wrapper doesn't
already forward.

## `RESULT_UI` — typed alternative to the dict

Every `RESULT_UI` shape (see
[Workflows → RESULT_UI](workflows.md#result_ui--live-result-rendering)) has
a matching dataclass in `core.workflow.result_types`, importable in a
template and used in place of the raw dict:

```python
from labpilot.core.workflow.result_types import ImageResult

RESULT_UI = ImageResult(
    value="image", x="x_positions", y="y_positions", value_label="Counts",
    crosshair_role="xy_actuator", crosshair_x_axis="x", crosshair_y_axis="y",
)
```

is exactly equivalent to:

```python
RESULT_UI = {
    "type": "image2d", "value_key": "image", "x_key": "x_positions", "y_key": "y_positions",
    "value_label": "Counts",
    "crosshair": {"role": "xy_actuator", "x_axis": "x", "y_axis": "y"},
}
```

Field -> dict-key mapping, one dataclass per `RESULT_UI["type"]`:

| Dataclass | Fields | Maps to |
|---|---|---|
| `ImageResult` | `value`, `x`, `y`, `value_label`, `crosshair_role`, `crosshair_x_axis`, `crosshair_y_axis` | `value_key`, `x_key`, `y_key`, `value_label`, `crosshair.role/x_axis/y_axis` |
| `SpectrumResult` | `x`, `y`, `x_label`, `y_label`, `fit_x`, `fit_y`, `fit_center` | `x_key`, `y_key`, `x_label`, `y_label`, `fit_x_key`, `fit_y_key`, `fit_center_key` |
| `OdmrResult` | `x`, `y`, `matrix`, `repeat`, `x_label`, `y_label`, `fit_x`, `fit_y`, `fit_center` | `x_key`, `y_key`, `matrix_key`, `repeat_key`, ..., `fit_*_key` |
| `NDScanResult` | `value`, `shape`, `axis_names`, `axis_positions`, `actuator_axis_count`, `value_label`, `crosshair_role` | `value_key`, `shape_key`, `axis_names_key`, `axis_positions_key`, `actuator_axis_count_key`, `value_label`, `crosshair.role` |

The one advantage over the raw dict, beyond not having to remember each
`*_key` suffix: a typo'd field name (`ImageResult(vlaue=...)`) or a missing
required one raises a clear error when the workflow is loaded/bound,
instead of the dict form's failure mode — a mismatched `*_key` string just
renders an empty panel, since nothing validates it against what your script
actually emits. **The raw dict form is still fully supported and requires
no migration** — most built-in templates still use it; both forms are read
by the exact same `RESULT_VIEW_REGISTRY`-dispatched rendering code
(`components/workflow_result.py`), so there's no behavioral difference,
only how much gets checked before the workflow ever runs.

## Worked example

`generic_2d_scan.py`'s per-pixel loop, before and after:

```python
# Before — generic dict read/write
actuator = session.get(ACTUATOR_ID)
detector = session.get(DETECTOR_ID)
value_key = next(iter(detector.schema.readable.keys()))
...
await move_and_settle(actuator, {"x": x, "y": y}, SETTLE_TOLERANCE, MAX_SETTLE_POLLS)
data = await detector.read()
image[i][j] = float(data[value_key])
```

```python
# After — kind-typed
actuator = session.get(ACTUATOR_ID)   # Motor
detector = session.get(DETECTOR_ID)   # Detector
...
await actuator.move_abs(x=x, y=y, tolerance=SETTLE_TOLERANCE, max_polls=MAX_SETTLE_POLLS)
image[i][j] = await detector.read_value()
```

Not every template benefits equally: `odmr_sweep.py`'s source-sweep logic
(which settable key is "the swept axis" vs. "the power setpoint") stays
manual `source.write({...})` — genuinely instrument-specific business
logic a generic wrapper can't honestly guess — while its detector read
does simplify the same way (`read_value()`). `omniscan.py` doesn't change
at all: it already delegates to `ScanCapability`/`HardwareTimedScanCapability`
(`core/workflow/capabilities.py`), which call the same generic
`.read()/.write()/.schema` surface the wrapper already passes through
unchanged.
