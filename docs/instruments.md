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
| `ni_daqmx` | `device` (e.g. `Dev1`), `model`, `channels` |
| `none` | — (mock/simulated devices) |

The "Connect Device" flow in the Devices tab renders whichever method you
pick as a form built from these fields.

## NI DAQ cards

Every NI DAQ card is one adapter, `ni_card` (and `mock_ni_card`, which is
the same configuration with a simulated specimen behind it). Which card it
is, and what is plugged into which terminal, are settings:

```python
from labpilot.instruments import create_adapter

card = create_adapter("ni_card", {
    "device": "Dev1",
    "model": "PCIe-6363",
    "channels": "x=ao0, y=ao1, apd=ctr0/pfi8, pd=ai0, shutter=do:port0/line0",
})
```

The channel names are the rig's, not the card's: `read()` comes back as
`{"apd": ..., "pd": ...}`, a workflow binds to `apd`, and moving the APD
to another PFI line is one character in a config file. The kind of each
channel follows from its terminal — `ai0` can only be an input, `ctr0/pfi8`
can only be a counter — except a digital line, which must say `do:` or
`di:` because guessing wrong there means a shutter that silently never
opens. The same wiring can also be given as a list of records
(`{"name": "x", "kind": "ao", "terminal": "ao0"}`), which is what a config
file or a script would normally use.

`src/labpilot/instruments/NI/models.toml` describes 51 models — X Series,
M Series, the low-cost USB boxes, the counter/timer cards and the S
Series — as ports and limits. It is what makes a card configurable with no
card present: qudi, pylablib, pyMoDAQ and Micro-Manager all ask NI-DAQmx
at run time and therefore cannot help you at a desk, and NI ships no DAQmx
for macOS at all. So the model is chosen from a table, the wiring is
validated against it, and errors name what the card actually has:

    'apd' counts edges on 'pfi99', which the 6363 does not have —
    it offers pfi0..pfi15 (16 of them)

The table is **not** authoritative. Connecting asks DAQmx what the card
really is and puts any disagreement in the reading's `warning` field —
visible in the instrument window and saved with every run; `python
scripts/ni_probe.py` prints a connected card's real inventory as a TOML
block, and `--check` compares it with the shipped table. Add or correct a
model in `~/.labpilot/config/ni_models.toml`, which is merged over the
packaged file entry by entry — a `[[card]]` there overrides only the
fields it names, so a later release's new models still arrive.

Both the model and the wiring are **settings**, not connection details:
open the card's window and `model` is a dropdown of every model in the
table, `channels` is an editable port table (`components/channel_table.py`,
which renders any record-table parameter). Changing either re-validates
the other before anything is applied — pick a PCI-6602 while an analog
output is wired and it says the 6602 has none, and the wiring stays as it
was. On a connected card the DAQmx tasks are rebuilt in place.

For a card the table does not list, set the model to `generic`: it states
no ports, so nothing is validated offline and DAQmx does the checking it
would have done anyway. Then run `ni_probe.py` and paste the block in to
get real checking back.

What a card can do follows from the model and the wiring rather than from
which adapter you picked: `hardware_scan` is claimed only when there is an
analog output to drive, something to read back, and outputs that can
follow a clock (a USB-6008's cannot, so it never claims it). Counter
outputs become `pulse_on`/`pulse_off` actions.

It is deliberately not a gated counter for pulsed work: an NI counter bins
on a sample clock it must be given, and nothing on the card produces a
33 MHz gate to slice a 3 µs readout into 30 ns bins. qudi does not
implement a fast counter on NI hardware either. Use a TimeTagger or a
FastComTec for that; see [pulsed.md](pulsed.md).

## NI R-Series FPGA cards

`ni_rseries_fpga` is the FPGA sibling of `ni_card`, and a genuinely
different instrument. An R-Series board is a user-programmable FPGA with
analog and digital I/O on it: what it *does* is whatever gateware you
compiled for it, so two labs' identical cards are two different devices.

**The bitfile is the instrument.** Compiling one needs LabVIEW FPGA and
the Xilinx toolchain and takes tens of minutes, so "convert the pulse
sequence into an FPGA program" cannot mean emitting one at run time — and
this adapter does not pretend otherwise. What it converts the sequence
into is **instructions**: one `(channel mask, ticks)` word per element,
streamed into the sequencer engine the bitfile already put on the card.
Exactly what a PulseBlaster or a PulseStreamer consumes, and never a
waveform.

qudi's own FPGA pulser confirms this is the right reading: it ships
pre-compiled images and *switches between them* to change the sample
rate — a 500 MHz `.bit` and a 950 MHz one, with nothing in between,
because those are the two someone compiled.

### Two ways to choose the image

Both first-class; neither is the other's fallback.

**Pinned in the configuration** — you compiled it, you know what it does:

```
resource   = RIO0
model      = 7852
bitfile    = ~/fpga/pulser_8ch_100MHz_7852R.lvbitx
channels   = DIO0, DIO1, DIO2, DIO3
tick_rate  = 100e6
```

`channels` is in **bit order**: position in that list is the bit this
adapter sets in the instruction word, so it must match the order your
gateware unpacks them in. It is the one setting here that silently
produces a working sequence on the wrong wires.

**Chosen by the measurement** — leave `bitfile` empty, and
`upload_sequence` picks from the library in
`~/.labpilot/config/ni_rseries.toml` the image whose engine can play what
this sequence asks for: enough channels, the right tick rate, a counter
if the run needs one. The narrowest fit wins. Still nothing is compiled;
the choice is among images the lab already built:

```toml
[[bitfile]]
name = "pulser8_100MHz"
path = "~/fpga/pulser_8ch_100MHz_7852R.lvbitx"
model = "7852"
tick_rate = 100e6
channels = ["DIO0", "DIO1", "DIO2", "DIO3",
            "DIO4", "DIO5", "DIO6", "DIO7"]
memory = 8192
counter = true
```

That library ships **empty**, which is not an omission: a bitfile is
built from a LabVIEW project and nobody can ship one for your rig.

### The contract with your gateware

The adapter and the LabVIEW VI have to agree on names, and there is no
standard to appeal to. The agreement is written down in
`instruments/NI/bitfiles.py` as `Gateware`, defaulted to the reference
VI's names, and every one is overridable — a lab with a working sequencer
VI renames four strings rather than editing Python:

| Name | Direction | What it carries |
|---|---|---|
| `Instructions` | host → target, U64 | ticks in bits 0–31, channel mask in 32–63 |
| `Instruction Count` | register | how many words were written |
| `Run` / `Loop` | registers | play; play repeatedly (what averaging needs) |
| `Counts` | target → host, U32 | one word per time bin, gate after gate |
| `Bin Ticks` / `Gates` / `Bins` / `Sweeps` / `Count` | registers | the counting half |

### A `.lvbitx` describes itself

It is XML with the bitstream base64'd inside, so the adapter reads a
bitfile's whole host interface **with no card present** — the same
problem the DAQmx model table solves by hand, except here the answer is
genuinely in a file we already have. Parsing is forgiving on purpose: NI
has changed that schema between LabVIEW versions, and an image this
cannot read is still one the driver may well load, so a failed parse
costs the offline checks and nothing else. Opening the card then
reconciles what the file claimed against what the session exposes, and
any disagreement lands in the instrument's `warning` — the same contract
`ni_card` has with its model table.

### Capabilities follow the gateware

Every image this adapter drives is a pulser, so `PulserMixin` is
inherited. The counter half is declared on the *schema* only when the
loaded bitfile actually has the counting registers — which is what lets
one card fill both roles of a pulsed measurement when its image does
both, and advertise only `pulser` when it does not. That is the same
reasoning that makes the DAQ card `generic`: what a device can do follows
from how it is configured, not from which class was instantiated.

The card table (`instruments/NI/rseries.toml`) is deliberately thin —
the bitfile decides which lines are driven and how fast, so the card only
bounds it — and follows the same rule as everywhere else here: a field
nobody was sure of is left out, and an absent field is never validated.
`model = "generic"` validates nothing at all.

## Ocean Optics spectrometers

The same shape, for the same reason. Every Ocean Optics / Ocean Insight
spectrometer is `ocean_optics` (and `mock_ocean_optics`), with the model
as a setting:

```python
spectrometer = create_adapter("ocean_optics", {
    "serial_number": "QEP01583",   # blank takes the first one found
    "model": "QE Pro",             # blank asks the device
})
```

Naming the model is what makes the instrument configurable before it is
plugged in: a QE Pro has 1044 pixels, an 18-bit ADC and cannot expose for
less than 8 ms, so `integration_time_ms=1` is refused by name — on a
laptop, at the point the acquisition is being written, rather than by a
driver error at the bench. `quantise_exposure()` answers the other
question ("what *would* I get?") and returns 8 ms with the reason.

`src/labpilot/instruments/OceanOptics/models.toml` covers 31 models —
Flame, Ocean HDX/FX/ST/SR/HR, QE Pro, QE65000, NIRQuest, Maya, USB2000+,
HR4000, Torus, Jaz, STS, Spark and the rest. The pixel counts, ADC full
scales, exposure limits and dark-pixel ranges are transcribed from
`python-seabreeze`'s own per-model classes (MIT), which carries them
because the USB protocol differs per model. Override or extend the table
in `~/.labpilot/config/ocean_models.toml`; the connected device wins over
both, and `reconcile()` reports any disagreement.

A model answers to every name it is known by — seabreeze reports `QEPRO`,
the box says `QE Pro`, and lookup ignores case, spaces and hyphens. A `+`
is not punctuation: `USB2000` and `USB2000+` are different instruments
with different ADCs.

Beyond what qudi's and pyMoDAQ's Ocean modules do (a serial number, an
exposure, `wavelengths()`/`intensities()`), the adapter adds saturation
reporting (a pixel at full scale carries no information, and a fit through
a flat-topped peak is confidently wrong), scan averaging, OceanView-style
boxcar smoothing, the electric-dark and nonlinearity corrections, trigger
mode, and a cooler setpoint on the cooled models. The spectrum comes back
as a `Dataset` whose `intensities` names `wavelengths` as its axis, so
plots and HDF5 files get the x-scale without being told.

## Siglent SSG microwave sources

The source an ODMR sweep steps. Siglent appears four other times in the
catalogue — two oscilloscopes and two bench power supplies — so this is the
first signal generator from them, and it is what unblocked `odmr_sweep` on
real hardware.

```python
source = create_adapter("siglent_ssg", {"host": "192.168.1.42"})
```

**The IP address on the instrument's own LAN screen is the whole
configuration.** It speaks SCPI on TCP port 5025, the standard raw-socket
interface, so there is nothing to install — no VISA runtime, no GPIB card,
no vendor SDK. A `resource=` string still works through pyvisa for a unit
reached over USBTMC instead (`instruments/_scpi.py`).

### It asks the instrument what it can do

A hand-entered frequency range is how a schema comes to disagree with its
hardware, and the SSG family spans 2.1 GHz to 6 GHz across models that
differ by one digit. So on connect the adapter asks `:FREQ? MIN`,
`:FREQ? MAX`, `:POW? MIN` and `:POW? MAX`, and what comes back becomes the
schema's limits — which `validate_write` then enforces. An out-of-range
setpoint is refused by numbers the instrument itself supplied, and the
parameter's description says where they came from.

That matters more than it sounds for NV work: **an SSG3021X stops at
2.1 GHz and so cannot reach the 2.87 GHz zero-field splitting at all.**
With the limits read from the instrument, that is a clear refusal at the
point the sweep is set up rather than a silent clamp and a flat spectrum.

`MODELS` in the adapter is only the fallback, for a unit that does not
answer those queries — a few answer `:FREQ? MAX` with the current setpoint
rather than an error, which is detected and rejected. The table is
transcribed from published specifications and has **not** been checked
against hardware. An unrecognised model gets a deliberately wide range
instead of a guess, because refusing a legitimate setpoint is the failure
that sends someone looking for a hardware fault.

`*IDN?` is checked for the model as well as the manufacturer: an SDS is an
oscilloscope and an SPD a power supply, a bench often has two of them on
one subnet, and `:FREQ` sent to a scope is accepted-looking nonsense.

### The sweep is stepped in software, deliberately

The SSG has an internal sweep generator. The adapter does not use it.
`reset_scan()`/`trigger_next()` step the CW frequency one setpoint at a
time, which is what `odmr_sweep` needs — it sets a frequency, reads the
detector, sets the next. Each setpoint is followed by `*OPC?`, which
returns only once the command has landed, so a point is never measured at
the previous point's frequency; `synchronise=False` drops that round trip
where throughput matters more.

What this costs: the dwell per point is on the host's clock, not the
instrument's. For CW ODMR, where the counter gate is far longer than a
socket write, that is immaterial. For a pulsed sequence where the
microwave step must land inside a gate, it is not — and that case belongs
to the pulser, which has the timing.

Not yet run against hardware. `labpilot probe siglent_ssg --param
host=192.168.1.42` is the first thing to run on it, and it is what turns
the paragraphs above into facts.

## Mad City Labs stages

The two halves of a coarse/fine positioner: millimetres of stepper travel
under microns of closed-loop piezo. MCL ship two separate libraries with
two separate APIs, which share their handle model, error codes and 1-based
axis numbering — so those live in `instruments/MadCityLabs/_madlib.py` and
the adapters differ only where the hardware does.

```python
fine = create_adapter("mcl_nano_drive", {})                  # microns, absolute
coarse = create_adapter("mcl_micro_drive", {"travel_mm": 25.4})
```

### The Nano-Drive says how far it goes

`MCL_GetCalibration(axis)` returns that axis's travel in microns and
`MCL_GetProductInfo` returns a bitmap of which axes physically exist. So a
100 µm XY stage declares `(0, 100)` on x and y and **no z at all**, rather
than offering a third control that silently fails and a scan axis a plan
will happily try to step.

That matters more here than on most instruments: a piezo's limits are its
whole safety story, since there is no mechanical slip to absorb an
over-travel command, and `validate_write` enforces exactly these numbers.

It is closed-loop, so a commanded position is read back from the stage's
own sensor and `move_and_settle` waits on that — the scan's next point is
not taken until the stage says it has arrived.

One trap, handled: `MCL_SingleReadN` returns a double that is either a
position or a negative error code. Travel starts at zero, so a negative
value cannot be a position — but carried into a dataset it would look like
a stage that had travelled backwards past its own home.

### The Micro-Drive's model is relative; ours is absolute

`MCL_MDMove(axis, velocity, distance)` moves a *distance*, and the
encoders are the only thing that knows where the stage is. So each move is
read-encoder, compute-delta, command, wait — and the delta is **measured
rather than remembered**, because a stepper that stalled or that someone
nudged by hand is at a position nothing in the process knows.

`travel_mm` is the one limit in either adapter that is a number someone
typed: `MCL_MDInformation` reports the encoder resolution, the step size
and the velocity bounds, but no library call reports the travel. The
default is 25.4 mm, MCL's common one-inch stage.

`MCL_MDStatus`'s limit bits are **active low** — a clear bit means that
limit is reached — so `at_limit` reports e.g. `"y reverse"`. Reading them
the obvious way round reports every axis as permanently jammed, which is
why the convention has its own test.

`stop` halts every axis, which on a stepper is the difference between an
abort and an abort that keeps travelling. `zero_encoders` is not a home:
nothing moves, and it is how a stage with no absolute reference gets an
origin.

### Verified, and not

Signatures, error codes, the packed `ProductInformation` layout and the
1-based axes were each checked against two independent open
implementations (ScopeFoundry's `HW_mcl_stage` and ZhuangLab's
`storm-control` for the Nano-Drive; `MCLMicroDrive` and MCL's own
documentation for the Micro-Drive). Both adapters deliberately do **not**
call `MCL_ReleaseAllHandles`, which both of those wrappers do on startup:
it releases the handle any other process or adapter holds, so two stages
cannot be used at once and a second window silently steals the first one's
stage.

ctypes against MCL's driver; no PyPI package, so no extra to install.
**Neither run against hardware.** `labpilot probe mcl_nano_drive` is what
settles the travel ranges and the axis count; for the Micro-Drive it also
confirms the axis count and the status-bit order.

## PicoHarp 300 as a gated counter

The photon counter for a pulsed NV rig, and the real instrument the whole
pulsed stack was waiting on.

```python
counter = create_adapter("picoharp_300", {"serial_number": "1041234"})
```

**CH0 takes the pulse sequence's gate line; CH1 takes the APD.** T3 mode
then gives, for every photon, which sync period it arrived in and how long
after that sync — which is exactly the `(gate, time_bin)` pair
`GatedCounterMixin` asks for, so the sequence's readouts become the
histogram's first axis with no arithmetic in between.

### The device does not histogram; the adapter does

Unlike the Time Tagger, whose `TimeDifferences` builds per-readout
histograms in hardware, the PicoHarp streams raw records and nothing else.
So the adapter reads the FiFo on a background thread and accumulates with
numpy. `PH_ReadFiFo` blocks for up to the device's 80 ms timeout, which is
why it is a thread rather than a coroutine.

One consequence to know: if the host cannot keep up, the device's FiFo
fills and records are **lost**, and no driver call raises. `PH_GetFlags`
is checked every pass and `fifo_overruns` is reported in the schema. A
trace taken while that number is climbing is missing photons and does not
look like it.

### Two deliberate omissions

**No gate pinning.** The Time Tagger has a second input that pins
histogram 0 to the start of the sequence, so one dropped gate shifts a
single sweep rather than rotating every later one. The PicoHarp has
markers that could serve, but the record `channel` field's meaning for
markers is the one part of the format the available documentation
contradicts itself about — one place says a marker is `0b1000`, another
`0b1111`, which is also the overflow value. Rather than guess, markers are
left disabled, so the only records that arrive are photons and overflows
and the decoding is exact. The cost is a property of the instrument, not
of the code: a lost sync edge rotates the gate axis for the rest of the
run. Keep the gate line clean, and prefer a Time Tagger for long
sequences.

**No PHR 800 router.** With one, record channels 1 to 3 carry the router's
extra inputs — a second claim on the same four bits. One detector on CH1
is the supported configuration.

### What the limits actually are

The bin width is a **ladder**, not a granularity: the device multiplies
its 4 ps base resolution by powers of two, giving 4, 8, 16 … 512 ps and
nothing between, which `counter_constraints()` states as `allowed` rather
than approximating with a step that would accept 12 ps. The base
resolution is re-read from the device on connect, so a unit that reports
otherwise wins over the constant.

`dtime` is 12 bits, so **no readout can hold more than 4096 bins** — and
at the coarsest 512 ps that caps the recorded window at 2.097 µs. A longer
request comes back adjusted, with the reason, rather than clamped:
`configure_gates` returns what was really set and the caller must use it.

### Verification, and what remains unverified

Function signatures come from PicoQuant's own `phlib.h`; the limits from
their `phdefin.h` values. The T3 bit layout and the 65536 wraparound were
confirmed against two independent sources — PicoQuant's own documentation
and `phconvert`'s `rtPicoHarp300T3` definition (`channel_bit=4,
time_bit=16, dtime_bit=12, WRAPAROUND=65536`), the reader most of the
field uses for `.ptu` files.

`decode_t3` is a pure function over 32-bit words and is tested exactly,
against synthetic streams whose histograms are known in advance. That is
the part worth the most: a sign error in the sync correction produces a
plausible histogram rather than an error, and the physics would be blamed
first.

Everything else is tested through a stand-in for `phlib`, because the real
library ships with PicoQuant's driver installation and there is no PyPI
package — so there is no extra to install, only their driver. **Not run
against hardware.** `labpilot probe picoharp_300` is the first thing to
run on it.

## The instrument catalog

306 instruments are catalogued across 95 manufacturers: mock/test-fixture
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

Also from the CLI: `labpilot list-adapters`, `labpilot list-adapters --tags camera`,
and `labpilot probe <adapter>` to check one adapter's declared schema against the
instrument itself — see [getting_started.md](getting_started.md#your-first-real-instrument).

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
