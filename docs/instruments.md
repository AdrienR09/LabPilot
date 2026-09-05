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

262 instruments are catalogued across 80 manufacturers: mock/test-fixture
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

`src/labpilot/instruments/` is organized by manufacturer, then instrument type
(`<Manufacturer>/<type>.py`), not by which library backs the adapter. See
[src/labpilot/instruments/README.md](../src/labpilot/instruments/README.md) for coverage
notes.
