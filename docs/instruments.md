# Instruments

Every instrument in LabPilot — real hardware or a mock — is reached
through the same interface, described by a `DeviceSchema`. This is what
lets the UI auto-generate a window per instrument, lets a workflow script
treat any detector/motor/source interchangeably, and lets you write one
new adapter and get a working UI/workflow integration for free.

## The `DeviceSchema` contract

```python
from labpilot.core.device.schema import DeviceSchema

schema = DeviceSchema(
    name="ocean_insight_usb2000",
    kind="detector",                                   # "detector" | "motor" | "source" | "counter" | "generic"
    readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
    settable={"integration_time_ms": "float64"},
    units={"wavelengths": "nm", "intensities": "counts"},
    limits={"integration_time_ms": (1.0, 60000.0)},
    trigger_modes=["software", "hardware"],
    tags=["spectroscopy", "VISA", "USB"],
)
```

| Field | Meaning |
|---|---|
| `name` | Unique device identifier |
| `kind` | Semantic category — `detector`, `motor`, `source`, `counter`, `generic` |
| `readable` | `{param_name: dtype}` for everything `read()` returns |
| `settable` | `{param_name: dtype}` for everything `write()` accepts |
| `units` | `{param_name: unit}` — used for display, not enforced |
| `limits` | `{param_name: (min, max)}` for settable parameters |
| `trigger_modes` | e.g. `["software", "hardware"]` |
| `tags` | Free-form, searchable (`adapter_registry.search(tags=[...])`) |

`DeviceSchema` is a frozen, `extra="forbid"` Pydantic model (`src/labpilot/core/device/schema.py`) — instances are immutable once created, and unknown fields are rejected rather than silently ignored.

### Parameters

Underneath, those four dicts are one tuple of `Parameter` objects
(`src/labpilot/core/device/parameter.py`). The dicts are computed views
over it, so the form above keeps working exactly as written — but a new
adapter should declare parameters directly and get more:

```python
from labpilot.core.device.parameter import INTEGRATION_TIME, Parameter, ParamRole

schema = DeviceSchema(
    name="ocean_insight_usb2000",
    kind="detector",
    parameters=(
        Parameter("wavelengths", shape=(None,), unit="nm", role=ParamRole.AXIS),
        Parameter("intensities", shape=(None,), unit="counts", axes=("wavelengths",)),
        Parameter("integration_time_ms", unit="ms", settable=True,
                  role=ParamRole.SETTING, limits=(1.0, 60000.0),
                  tags=frozenset({INTEGRATION_TIME})),
        Parameter("trigger_mode", dtype="str", settable=True,
                  role=ParamRole.SETTING, choices=("software", "hardware")),
    ),
    tags=["spectroscopy", "VISA", "USB"],
)
```

| Field | Meaning |
|---|---|
| `dtype` / `shape` | Element type and array shape — `shape=(None,)` is a 1-D array of runtime length, replacing the opaque `"ndarray1d"` |
| `role` | `VALUE` (a measurement), `AXIS` (coordinates indexing another parameter), `POSITION` (a commandable axis), `SETTING`, `STATUS` |
| `limits` / `choices` | **Enforced** on every write, including one-sided limits like `(0.0, None)` |
| `axes` | Names of the `AXIS` parameters that index this one |
| `tags` | Cross-vendor marks — `INTEGRATION_TIME` is how a caller asks for "the integration time" whatever this device calls it |
| `unit`, `description` | Display and tooltips |

Ask the schema rather than pattern-matching on names:

```python
schema.integration_time            # the Parameter tagged INTEGRATION_TIME, or None
schema.position_axes               # ('x', 'y', 'z') — commandable axes, not settings
schema.find(role=ParamRole.AXIS)   # every declared axis
schema.require("voltage").limits   # (-210.0, 210.0)
```

Writes are validated against the parameter before they reach hardware:
an unknown name, a read-only parameter, a value of the wrong type, out of
range, or not among the choices all raise a `ParameterError` subclass
(`src/labpilot/core/errors.py`), which the REST layer reports as HTTP 422.

### Structured parameters

A setpoint that isn't a scalar — a pulse table, an AWG channel map, an NI
task's channel list — is described rather than escaped. Declaring `fields`
makes a parameter a **record**; `shape=(None,)` makes it a table of them:

```python
Parameter("sequence", shape=(None,), settable=True, fields=(
    Parameter("duration_ns", unit="ns", limits=(8.0, None), settable=True),
    Parameter("channel", dtype="i8", limits=(0, 23), settable=True),
    Parameter("level", dtype="str", choices=("low", "high"), settable=True),
))
```

Fields are `Parameter`s, so they carry their own units, limits and
choices, and a limit on a field is enforced on **every row** by the same
code that enforces a scalar setpoint's. A missing field, an undeclared key
or an out-of-range value is rejected with the field named. The settings
tree renders a single record as a group of its own fields; a table is left
to a dedicated component.

`dtype="json"` still exists and still validates nothing — it is the escape
hatch, no longer the only door.

### Actions

An action is a command that isn't a parameter write. A bare name means a
zero-argument one; declaring `params` gives it typed arguments:

```python
from labpilot.core.device.action import Action

actions = [
    "cw_on", "off",                                   # zero-argument
    Action(
        name="configure",
        params=(Parameter("bin_width_s", unit="s", limits=(1e-12, 1.0), settable=True),
                Parameter("gates", dtype="i8", limits=(1, None), settable=True)),
        returns=(Parameter("bin_width_s", unit="s"),),
        defaults={"gates": 1},
    ),
]
```

Arguments validate before the call leaves the caller, and the return value
is what the hardware *actually* applied — see Constraints below. From the
console:

```python
actual = counter.call("configure", bin_width_s=1e-9, gates=50)
```

### Constraints

`Parameter.validate` asks "is this legal?" and raises. `Constraints.quantise`
asks "what will the hardware really do?" and never raises — it clips, snaps
and reports:

```python
from labpilot.core.device.constraints import ScalarConstraint, scalars_from

constraints = scalars_from([
    ScalarConstraint("bin_width_s", allowed=(1e-9, 2e-9, 4e-9), unit="s"),
    ScalarConstraint("duration_ns", bounds=(8.0, 1e6), step=8.0, unit="ns"),
])
result = constraints.quantise({"bin_width_s": 1.4e-9})
result["bin_width_s"]   # 1e-9
result.report()         # "bin_width_s: asked 1.4e-09, got 1e-09 (nearest of 3 supported value(s))"
```

Use it in a `configure` action and return `result.values`, so a silently
ignored request never happens.

### Capabilities

A contract beyond read/write is declared by a mixin and composed onto the
schema:

```python
from labpilot.core.device.capabilities import HARDWARE_SCAN

class HardwareScanMixin:
    CAPABILITY = HARDWARE_SCAN
```

`capabilities_of()` collects these off the MRO, so a device satisfying two
contracts reports both and its wrapper is composed from both. Capabilities
serialise, which is what lets `ui_blocks.toml` select a window with
`[capability.<name>]` instead of putting every `kind="generic"` device in
one bucket.

## Connecting an instrument

**From the Manager:**

1. Open the **Devices** tab.
2. Pick an instrument from the catalog (filterable by manufacturer, type,
   dimensionality).
3. Choose a connection method if the instrument supports more than one,
   and fill in its parameters (see [Connection methods](#connection-methods)
   below).
4. Click **Connect**.

Once connected, an instrument gets a row in the Devices tab with its live
readable values, and a native Qt window (auto-generated from its schema)
for detailed control.

**From code** (a script, the console, or any REST client):

```python
lp['mock_xyz_stage_2'].connect()
lp['mock_xyz_stage_2'].read()                    # {'x': 0.0, 'y': 0.0, 'z': 0.0, 'moving': False}
lp['mock_xyz_stage_2'].write(x=1.0, y=0.5)
lp['mock_xyz_stage_2'].schema                    # the live DeviceSchema, as a dict
```

See [console.md](console.md) for what `lp` is, or
[api_reference.md](api_reference.md) for the underlying REST calls.

## Connection methods

An instrument can support more than one way of being reached — VISA,
serial/COM, TCP/IP, USB (by serial number), or none (mocks/fixtures).
`InstrumentMetadata.connection_types` (`src/labpilot/instruments/catalog.py`) lists
which methods a catalog entry supports; `src/labpilot/instruments/connections.py`
defines each method's own parameter fields:

| Method | Fields |
|---|---|
| `visa` | `resource` (e.g. `GPIB::1`) |
| `serial` | `port` (e.g. `COM3`), `baudrate`, `timeout` |
| `tcp` | `host`, `port` |
| `usb_serial_number` | `serial_number` |
| `none` | — (mock/simulated devices) |

The "Connect Device" flow in the Devices tab renders whichever method you
pick as a form built from these fields.

## The instrument catalog

301 instruments are catalogued across 95 manufacturers: mock/test-fixture
devices (for development without real hardware), PyMeasure-backed
adapters (hand-written and auto-generated from every class in the
installed `pymeasure` library), and pylablib-backed adapters. `catalog.py`
adds the manufacturer/model/dimensionality metadata the UI needs
(`InstrumentType`: `detector_0d/1d/2d/nd`, `actuator_0d/1d/nd`, `source`,
`generic`) on top of what `DeviceSchema` itself describes — every catalog
entry corresponds to a real, registered adapter.

```python
from labpilot.instruments import adapter_registry, INSTRUMENT_CATALOG
from labpilot.instruments.catalog import get_instruments_by_type, get_instruments_by_tag, InstrumentType

adapter_registry.list()                              # {key: AdapterClass} — everything registered
adapter_registry.search(tags=["camera"])               # filter by DeviceSchema tags
adapter_registry.list_with_schemas()                    # {key: DeviceSchema} for every adapter

INSTRUMENT_CATALOG                                    # full list[InstrumentMetadata]
get_instruments_by_type(InstrumentType.DETECTOR_1D)     # spectrometers, waveform digitizers, ...
get_instruments_by_tag("spectroscopy")
```

Also from the CLI: `labpilot list-adapters`, `labpilot list-adapters --tags camera`.

## Instantiating an adapter directly

Most of the time you'll go through the Devices tab or the dashboard API
(below), but an adapter can be created directly too:

```python
from labpilot.instruments.factory import create_adapter

adapter = create_adapter("mock_spectrometer", {}, name="spec1")
adapter = create_adapter("keithley_2400", {"resource": "GPIB::24"})
await adapter.connect()
data = await adapter.read()
```

`create_adapter` inspects the target adapter class's `__init__` signature
and only passes through the `connection_params` keys it actually accepts
— extra keys are ignored, not errors, so the same connection-params dict
can be reused across adapters needing different subsets.

## Writing a new adapter

Every adapter subclasses `AdapterBase` (`src/labpilot/instruments/_base.py`),
which handles the async/sync boundary for you: every hardware call you
implement is a plain **synchronous** method, run in a thread pool via
`anyio.to_thread.run_sync()` so it never blocks the server's event loop.

```python
from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.core.device.schema import DeviceSchema

class Keithley2400Adapter(AdapterBase):
    def __init__(self, resource: str):
        super().__init__()
        self._resource = resource
        self._instrument = None

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name="keithley_2400",
            kind="source",
            readable={"voltage": "float64", "current": "float64"},
            settable={"voltage": "float64"},
            units={"voltage": "V", "current": "A"},
            limits={"voltage": (-210.0, 210.0)},
            tags=["Keithley", "SMU", "VISA"],
        )

    def _connect_sync(self) -> None:
        self._instrument = Keithley2400(self._resource)

    def _disconnect_sync(self) -> None:
        if self._instrument:
            self._instrument.shutdown()

    def _read_sync(self) -> dict:
        return {
            "voltage": float(self._instrument.voltage),
            "current": float(self._instrument.current),
        }

    async def set_voltage(self, value: float) -> None:
        await self._to_thread(lambda: setattr(self._instrument, "source_voltage", value))
```

Required overrides: `schema` (property), `_connect_sync`, `_disconnect_sync`,
`_read_sync`. Optional: `_stage_sync`/`_unstage_sync` (setup/teardown
around acquisition — default no-op), `_self_test_sync` (default: a plain
read).

**Writing settable values**: `AdapterBase.write(values)`'s default
implementation dispatches each key in `values` to a same-named
`set_<key>(value)` coroutine on your adapter — a schema declaring
`settable={"voltage": ...}` needs an `async def set_voltage(self, value)`.
If your adapter's underlying library has a settings API that doesn't fit
this one-setter-per-key shape, override `write()` entirely instead.

Register it:

```python
adapter_registry.register("keithley_2400", Keithley2400Adapter)
```

...and add a matching entry to `instruments/catalog.py` so it shows up in
the Devices tab's catalog browser, following the existing entries'
pattern (there's a `_pymeasure`/`_mock`/`_fixture` helper per backend —
see the top of that file).

## Shipping adapters in your own package

An adapter does not have to live in this repository. Any installed
package can advertise adapters through the `labpilot.adapters` entry-point
group, and LabPilot imports them at startup alongside its own:

```toml
# your package's pyproject.toml
[project.entry-points."labpilot.adapters"]
acme = "acme_labpilot"            # a module, imported for its register() side effects
# or
acme = "acme_labpilot:register"   # a callable, invoked with no arguments
```

Either form works; point at a module if one module registers everything,
at a callable if you have several. Your adapters then behave like any
other — `adapter_registry.get("acme_x100")`, tag search, the instrument
browser, the auto-generated UI.

Plugins load *after* the built-in adapters, so a plugin may subclass them,
and a key collision names the plugin rather than the built-in. A plugin
that fails to import is recorded in `labpilot.instruments.DISCOVERY_FAILURES`
and reported on stderr; it never prevents the application from starting.

`src/labpilot/instruments/` is organized by manufacturer, then instrument type
(`<Manufacturer>/<type>.py`), not by which library backs the adapter. See
[src/labpilot/instruments/README.md](../src/labpilot/instruments/README.md) for coverage
notes.
