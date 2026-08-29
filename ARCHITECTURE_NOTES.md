# Architecture Notes: Qudi, pyMoDAQ, PyMeasure

Research notes for LabPilot's own design, comparing three mature open-source
acquisition frameworks. Read directly from source (local checkouts for Qudi,
live GitHub fetches for pyMoDAQ/PyMeasure) — not summarized from
documentation or memory. Every claim below cites a real file/class/function
so it can be checked against the actual source.

Sources used:
- Qudi: local checkouts at `/Users/adrien/Documents/Qudi/qudi-core` and
  `/Users/adrien/Documents/Qudi/qudi-iqo-modules` (also this session's own
  earlier reading of `qudi-iqo-modules/src/qudi/gui/scanning/*` while
  building LabPilot's own scanner GUI).
- pyMoDAQ: fetched live from github.com/PyMoDAQ/PyMoDAQ (+ its
  `pymodaq_data`/`pymodaq_gui` companion packages).
- PyMeasure: fetched live from github.com/pymeasure/pymeasure.

---

## 1. Qudi (qudi-core + qudi-iqo-modules)

### 1.1 Instrument/hardware abstraction layer

Every loadable piece of Qudi — hardware, logic, or GUI — is a **module**:
`Base(QtCore.QObject, metaclass=ModuleMeta)` (`qudi-core/src/qudi/core/module.py`).
Two thin subclasses set one behavioral flag:
`LogicBase(Base): _threaded = True` and `GuiBase(Base): _threaded = False`
(hardware modules also subclass `Base` directly, `_threaded = False`).

Two declarative descriptors, both scanned by `ModuleMeta` at class-definition
time and re-applied by `Base.__init__` at instance-construction time:

- **`ConfigOption`** (`qudi-core/src/qudi/core/configoption.py`) — a class
  attribute like `_min_poll_interval = ConfigOption(name='min_poll_interval',
  default=None)`. Optionally takes a `checker`/`converter`/`constructor`
  callable. `missing='error'|'warn'|'info'|'nothing'` controls what happens
  if the config file omits it. This is qudi's config-injection mechanism —
  every configurable parameter a module needs is declared once, at the
  class level, self-documenting and validating.
- **`Connector`** (`qudi-core/src/qudi/core/connector.py`) — a class
  attribute like `_scanner = Connector(name='scanner',
  interface='ScanningProbeInterface')`. `interface` is checked as a
  **string against the target's MRO class names** (`connect()`:
  `bases = {cls.__name__ for cls in target.__class__.mro()}; if
  self.interface not in bases: raise RuntimeError(...)`) — a lightweight
  duck-typed interface check, not a strict Python ABC/Protocol
  `isinstance`. Once connected, calling the connector (`self._scanner()`)
  returns an `OverloadProxy` wrapping the target, restricted to just the
  declared interface's methods — the caller physically cannot reach
  methods outside the interface it declared it needs.

A hardware **interface** is just an ABC listing a handful of abstract
methods with no ConfigOptions/Connectors of its own — e.g.
`ScanningProbeInterface(Base)`
(`qudi-iqo-modules/src/qudi/interface/scanning_probe_interface.py`):
`get_constraints`, `reset`, `configure_scan`, `move_absolute`,
`move_relative`, `get_target`, `get_position`, `start_scan`, `stop_scan`,
`get_scan_data`, `emergency_stop` — eleven methods, full stop. A real
hardware module (or a `*_dummy.py` simulator — the simulated-vs-real
pattern is just "same interface, different module class, swapped in
config") implements these.

Capability *declaration* (as opposed to behavior) is a separate set of
small typed value objects in the same file: `ScannerAxis` (name, unit,
`value_range`, `step_range`, `resolution_range`, `frequency_range`, plus
`clip_value`/`clip_resolution`/`clip_frequency` helpers), `ScannerChannel`
(name, unit, numpy dtype), and `ScanConstraints` (bundles axes + channels +
a few capability flags like `backscan_configurable`,
`has_position_feedback`). `get_constraints()` returns one `ScanConstraints`
— the GUI/logic build all their controls (range spinbox bounds, resolution
limits, channel dropdowns) directly from this, never hardcoding numbers.

### 1.2 GUI ↔ logic communication

Confirmed directly in `qudi-core/src/qudi/core/modulemanager.py`'s
`ManagedModule.activate()`: activation **recursively activates every
required module first**, then calls `self._connect()` (wires `Connector`
attributes to real target instances), then — if
`self._instance.is_module_threaded` (true for every `LogicBase`) — pulls a
new `QThread` from `ThreadManager`, calls
`self._instance.moveToThread(thread)`, starts the thread, and invokes the
module's own state-machine `activate()` via
`QtCore.Qt.BlockingQueuedConnection`.

This is the whole mechanism: **every LogicBase module owns its own
QThread. GUI modules stay on the main thread. Cross-thread calls are
ordinary Qt signals/slots** — Qt auto-promotes a signal connection to a
queued (or blocking-queued) connection whenever sender and receiver live
in different threads, with zero extra plumbing from the module author.
Logic modules declare their own signals (e.g.
`ScanningProbeLogic.sigScanStateChanged = QtCore.Signal(bool, object,
object)`, `sigScannerTargetChanged`, `sigScanSettingsChanged` — confirmed
in `qudi-iqo-modules/src/qudi/logic/scanning_probe_logic.py`); the GUI
module (living on the main thread) connects slots to these and calls the
logic's plain Python methods directly — Qt's queued-connection machinery
makes both directions thread-safe without any manual locking, queue, or
serialization in ordinary use. (A separate, opt-in remote-module server —
`global.remote_modules_server` in the config, `force_remote_calls_by_value`
— exists for cross-*process*/cross-*machine* access via Pyro, but that's
additional, not how a normal same-process GUI↔logic call works.)

The layering is always Hardware → Logic → GUI: a GUI module's `Connector`s
point at Logic modules (never directly at hardware), and a Logic module's
`Connector`s point at hardware interfaces. This is exactly what
`default.cfg`'s `scanner_gui` entry shows (§1.4).

### 1.3 Scan data structure ↔ GUI mapping

`ScanData` (same file as the interface) is the scan data container. One
concrete, load-bearing fact, confirmed directly in its `__init__`:

```python
if not (0 < len(scan_axes) <= 2):
    raise ValueError('ScanData can only be used for 1D or 2D scans.')
```

**Qudi's own native scan representation is hard-capped at 1D or 2D.**
There is no N-dimensional `ScanData`. What looks like "many axes" support
in the GUI is qudi's own workaround, confirmed in
`gui/scanning/scannergui.py`'s `on_activate`:

```python
scans = list()
axes = tuple(scan_logic.scanner_axes)
for i, first_ax in enumerate(axes, 1):
    scans.append((first_ax,))                 # one 1D dock per axis
    for second_ax in axes[i:]:
        scans.append((first_ax, second_ax))   # one 2D dock per PAIR
for scan in scans:
    self._add_scan_dockwidget(scan)
```

Every possible axis pair (plus every single axis alone) gets its **own**
independent `ScanDockWidget`/`ScanData` instance, built once at GUI
start-up from the hardware's declared axes (`scan_logic.scanner_axes`) —
*not* one shared N-D array. Each dock can be started/stopped/zoomed/saved
completely independently of the others.

Inside one `ScanData`, `data` is `dict[channel_name -> np.ndarray]` — one
full-shape array **per channel**, pre-allocated NaN-filled by `new_scan()`
(`self._data = {ch.name: np.full(self._scan_resolution, np.nan,
dtype=ch.dtype) for ch in self._channels}`), filled in incrementally as
the scan progresses. Multi-channel is "several parallel same-shape arrays
in a dict," not "one array with an extra channel axis."

GUI mapping (already studied in depth earlier this session, re-confirmed
here): each `ScanDockWidget` wraps one `Scan2DWidget` (or `Scan1DWidget`),
which is a `[Toggle Scan | Save | Channel]` toolbar row over an
`ImageWidget` (a `PlotWidget` + a real `ColorBarWidget` beside it, not
inside it) with a `pg.ROI`-based crosshair
(`qudi.util.widgets.plotting.marker.InfiniteCrosshairRectangle` — two
`pg.InfiniteLine`s + a resizable, green/yellow-on-hover `pg.ROI` box) drawn
via the image widget's own "region selection" mechanism. A separate
`AxesControlDockWidget` (always visible) holds one row per axis:
resolution (forward/backward) | min/max range | slider+target — all in
one place, no split between "frequently used" and "rarely used" for this
particular dock. A truly infrequently-used settings dialog does exist,
but it's about **pixel scan frequency** (`ScannerSettingDialog` /
`scan_settings_dialog.py`, whose own docstring says "settings that do not
need to be accessed frequently") — a hardware-timing concept with no
equivalent in a point-by-point move-and-settle engine. A separate
`OptimizerDockWidget` shows a live small scan (typically along the fast
axis, refined progressively) with its own crosshair marking the best
position found so far, driven by `ScanningOptimizeLogic`.

### 1.4 Config-driven wiring

One YAML file. Confirmed directly from
`qudi-iqo-modules/src/qudi/default.cfg`:

```yaml
gui:
    scanner_gui:
        module.Class: 'scanning.scannergui.ScannerGui'
        options:
            image_axes_padding: 0.02
            default_position_unit_prefix: null
        connect:
            scanning_logic: scanning_probe_logic
            data_logic: scanning_data_logic
            optimize_logic: scanning_optimize_logic
```

Each top-level key (`gui:`, `logic:`, `hardware:`) is a module base; each
child key is a chosen **instance name**; `module.Class` is the dotted
class path to import; `options:` fills `ConfigOption`s; `connect:` maps
each `Connector` attribute name (by its declared `name=`, e.g.
`scanning_logic`) to another instance name declared elsewhere in the same
file (by string, resolved at activation time — see §1.2). Loading order
doesn't matter; `ManagedModule.activate()`'s recursive
"activate-my-required-modules-first" walk handles dependency order
automatically. A top-level `global:` section carries process-wide options
(stylesheet, default data directory, remote-module server, startup module
list) that aren't tied to any one module.

### 1.5 Save/export pipeline

`qudi-core/src/qudi/util/datastorage.py`. Three concrete backends, all
subclassing `DataStorageBase`: `TextDataStorage` (tab-delimited `.dat`,
configurable `comments`/`delimiter`), `CsvDataStorage(TextDataStorage)`
(same thing, comma-delimited `.csv`), and `NpyDataStorage` (binary
`.npy` + a companion metadata file). `save_data(data, *, metadata=None,
notes=None, nametag=None, timestamp=None, **kwargs)` is the common
signature — metadata/notes get written as commented header lines (text
formats) or a sidecar file (`.npy`). **No HDF5 or other structured
binary/container format ships in qudi-core** — plain text/CSV/NPY only.
(`daily_data_dirs: True` in `default.cfg` controls whether saves land
under a per-day subdirectory — the "how is it organized on disk" half of
config-driven data management.)

### 1.6 License

**Per-file headers are consistently LGPLv3**, confirmed by directly
reading the header comment in `module.py`, `connector.py`,
`configoption.py`, `scannergui.py`, and a hardware driver file — every one
says *"GNU **Lesser** General Public License... version 3... or (at your
option) any later version."* Both repos also ship a plain `LICENSE`
(GPLv3 text) *and* `LICENSE.LESSER` (LGPLv3 text) at the root — a
dual-license-file layout, but the operative per-file license (what
actually governs each source file you'd be looking at) is LGPLv3, not
GPLv3 as commonly assumed from the repo-level `LICENSE` file alone.
LGPLv3 is more permissive than GPLv3 for *linking*/*using* the code
unmodified, but copying **substantial original expression** (real code,
not just the architectural idea) into a differently-licensed project
still triggers LGPL obligations for that copied material. Since the ask
here is "understand and re-derive," not copy, this is a non-issue in
practice — flagging per the constraint anyway, and correcting the
GPLv3-only assumption for the record.

---

## 2. pyMoDAQ

*(Report from a dedicated research pass. PyMoDAQ is now a monorepo at
`github.com/PyMoDAQ/PyMoDAQ` containing four previously-separate
packages under `packages/`: `pymodaq` (control logic/GUI), `pymodaq_data`
(data model + HDF5), `pymodaq_gui` (Qt widgets/H5Saver GUI layer),
`pymodaq_utils` (config/logging/serialization). Paths below are relative
to `packages/<pkg>/src/<pkg>/…`, fetched at tag `5.1.13`; the `5.2.x` dev
branch is mid-refactor toward a new State/Experiment manager, noted
where relevant. Instrument drivers live in ~90 separate
`pymodaq_plugins_*` repos in the same GitHub org.)*

### 2.1 Instrument/hardware abstraction layer

Actuators subclass `DAQ_Move_base(QObject)`
(`pymodaq/control_modules/move_utility_classes.py:249`) — a
`move_done_signal = Signal(DataActuator)`, a `settings` `Parameter` tree
built from a class-level `params` list, and methods a plugin overrides:
`ini_stage`, `move_abs`, `move_rel`, `move_home`, `stop_motion`,
`get_actuator_value`, `commit_settings`. Detectors subclass
`DAQ_Viewer_base(QObject)`
(`pymodaq/control_modules/viewer_utility_classes.py:140`), exposing
`dte_signal = Signal(DataToExport)`, requiring `grab_data`,
`commit_settings`, `close`, `ini_detector`.

Plugin discovery is **entry-point based**, not a bespoke manager class:
`pymodaq/utils/daq_utils.py`'s `get_instrument_plugins()` reads Python
package entry points from groups `pymodaq.instruments` (current) and
`pymodaq.plugins` (legacy), each mapping a short name to a package like
`pymodaq_plugins_mock`, then imports `<package>.daq_move_plugins` /
`<package>.daq_viewer_plugins.plugins_{0D,1D,2D,ND}` and enumerates
files via `pkgutil.iter_modules`. Plugin packages don't hand-write these
entry points — a custom hatchling build hook generates them from a
`[features]` table in the plugin's own `pyproject.toml`.

Simulated hardware is a **first-class, separate plugin package**
(`pymodaq_plugins_mock`), not a stub: `DAQ_Move_Mock(DAQ_Move_base)` is
backed by `ActuatorWrapperWithTauMultiAxes`, a small physics simulator
modeling first-order relaxation dynamics — same real-plugin/interface,
swapped backing implementation, same pattern as qudi's `*_dummy.py`
modules and LabPilot's own `mock`/`test_fixtures` adapters.

### 2.2 GUI ↔ logic communication

**QThread + Qt signals, one hardware thread per control-module
instance** — directly analogous to qudi's per-LogicBase QThread, but
applied per *instrument* here rather than per *logic module*. In
`pymodaq/control_modules/daq_viewer.py`'s `init_hardware()`: a
`DAQ_Detector(...)` worker object is created, `moveToThread()`'d onto a
dedicated `QThread`, then wired both directions —
`self.command_hardware[ThreadCommand].connect(hardware.queue_command)`
(GUI → hardware) and `hardware.data_detector_sig[DataToExport].connect(
self.show_data)` (hardware → GUI). `DAQ_Move` mirrors this with
`DAQ_Move_Hardware(QObject)`. Concrete trace for a "Grab" click:
GUI button → `DAQ_Viewer.grab()` → emits a `ThreadCommand` → received by
`DAQ_Detector.queue_command` on the worker thread → plugin's
`grab_data()` runs → plugin emits `self.dte_signal` → re-emitted on
`data_detector_sig` → GUI-thread slot `show_data` → plotting widgets.

A genuine distributed path also exists:
`pymodaq/utils/tcp_ip/tcp_server_client.py`'s `TCPClient`/`TCPServer`
let a `DAQ_Move`/`DAQ_Viewer` on one machine drive/report to another over
sockets (preset files carry a per-module `tcpip` settings group). The
5.2.x branch is layering a newer LECO-based RPC protocol alongside this.
No multiprocessing anywhere — concurrency is strictly Qt's threading
model, same as qudi.

### 2.3 Scan data structure ↔ GUI mapping

The data model, `pymodaq_data/data.py`: `Axis(SerializableBase)` (linear
`scaling`/`offset` or explicit `data`, plus `label`/`units`/`index`);
`DataWithAxes(DataBase, SerializableBase)` — an ndarray plus a list of
`Axis` **and a `nav_indexes` tuple marking which axes are navigation
(scan) vs. signal axes** — this is pyMoDAQ's answer to "how many
dimensions can a scan have": genuinely N-D, with the nav/signal split
baked into the data object itself, not hard-capped like qudi's `ScanData`
(§1.3). `DataToExport(DataLowLevel, SerializableBase)` bags multiple
`DataWithAxes` together for export/plotting/saving.

Scan orchestration is `Scanner(QObject, ParameterManager)`
(`pymodaq/utils/scanner/scanner.py`) — it does not hardcode geometry,
delegating to a `scanner_factory.get(scan_type, scan_sub_type,
actuators=...)` returning a `ScannerBase` subclass (`Scan2DLinear`,
`Scan2DSpiral`, `Scan2DRandom`, plus sequential/tabular variants) — each
contributing its own settings-tree `params` for per-axis range/step
widgets. The `daq_scan` extension glues this to a running dashboard; the
2D image viewer/crosshair/ROI widgets are supplied separately by
`pymodaq_gui`'s viewer widgets consuming the resulting `DataWithAxes`. A
real, built-in **optimizer extension** exists too:
`pymodaq/extensions/bayesian/bayesian_optimization.py`'s
`BayesianOptimization(GenericOptimization)`, driven by an acquisition-
function factory, alongside a more generic `optimizers_base` framework.

### 2.4 Config-driven wiring

An **XML preset file** (not TOML, contrary to the initial assumption in
this brief — see below), produced/consumed via pyqtgraph's `Parameter`
serialization (`XML_file_to_parameter`/`parameter_to_xml_file`) and
managed by `PresetManager`
(`pymodaq/utils/managers/preset_manager.py`). A real shipped example
(`pymodaq/resources/preset_default.xml`):

```xml
<Moves type="groupmove" ...>
  <move00 type="group" title="Actuator 00">
    <name type="str">Xaxis</name>
    <init type="bool">1</init>
    <params type="group">
      <main_settings type="group">
        <move_type type="str" readonly="1">Mock</move_type>
        <module_name type="str" readonly="1">Xaxis</module_name>
        ...
```

Each `<move0N>`/`<det0N>` block names the logical module and records
which plugin (`move_type`/`DAQ_type`+`detector_type`) backs it, embedding
that plugin's full settings tree inline. `.toml` in this codebase is used
for *global app config* instead
(`pymodaq/resources/config_template.toml`, via `pymodaq_utils.config.Config`),
not per-instrument wiring — the TOML-preset assumption in this brief was
directionally right for where PyMoDAQ is *heading* (the `5.2.x` dev
branch is actively replacing this with a TOML-backed `StateManager`), but
not yet true of the shipped 5.1.x mechanism.

### 2.5 Save/export pipeline

A genuine two-layer HDF5 stack: `H5Backend` (raw PyTables/h5py wrapper —
groups/arrays/attributes) in `pymodaq_data/h5modules/backends.py`, and
`H5SaverLowLevel(H5Backend)` (`pymodaq_data/h5modules/saving.py`) adding
scan-aware save logic; `pymodaq_gui` layers `H5SaverBase` then
`H5Saver(H5SaverBase, QObject)` for Qt integration (progress signals,
file dialogs). On-disk grouping is **enum-driven**: `SaveType` (`scan`,
`detector`, `actuator`, `logger`, `optimizer`, `custom`) and `GroupType`
(`detector`, `actuator`, `data`, `ch`, `scan`, `data_dim`, ...). Per-module
group writers (`pymodaq/utils/h5modules/module_saving.py`):
`DetectorSaver`/`DetectorTimeSaver`/`DetectorEnlargeableSaver`/
`DetectorExtendedSaver`, `ActuatorSaver` (+ time/enlargeable variants),
and `ScanSaver` — which **nests detector/actuator subgroups per scan
step**, i.e. one HDF5 group per acquired point, containing that point's
full multi-channel reading. Export beyond native HDF5 goes through a
small plugin/factory system (`ExporterFactory`, keyed by file extension):
built-in `H5h5Exporter` (single-node `.h5`), `H5txtExporter` (`.txt`),
`H5npyExporter` (`.npy`), plus third-party-format exporters for HyperSpy
and FLIMJ files.

### 2.6 License

**MIT**, confirmed directly against the repo's `LICENSE` file and
GitHub's license API (`spdx_id: "MIT"`) — copyright Sébastien
Weber/CEMES. The `pymodaq_plugins_mock` and `pymodaq_plugins_template`
repos are likewise MIT. **This contradicts the CeCILL-B assumption in
the original brief** — no CeCILL-B text was found anywhere in the current
tree or subpackages. It's plausible an earlier pre-monorepo release
(1.x/2.x era) used CeCILL-B and the project later relicensed to MIT, but
that historical claim wasn't independently confirmed — flagged as
unconfirmed rather than assumed. Bottom line for reuse: **treat current
pyMoDAQ as MIT**, the least restrictive of the three; if a specific
older CeCILL-B release is what's actually being drawn from, verify that
separately before assuming MIT terms apply to it.

---

## 3. PyMeasure

*(Report from a dedicated research pass — github.com/pymeasure/pymeasure,
fetched live, current as of Aug 2026.)*

### 3.1 Instrument/hardware abstraction layer

`pymeasure/instruments/instrument.py`'s `Instrument(CommonBase)` is a thin
wrapper: `__init__(self, adapter, name, **kwargs)` accepts an `Adapter`
object, a raw VISA resource string, or an integer GPIB address (strings/
ints get auto-wrapped into a `VISAAdapter`). It exposes `write()`/
`read()`/`write_binary_values()`/`read_binary_values()`/`wait_for()` as
pass-throughs to the adapter.

The real declarative machinery lives one level up, in
`pymeasure/instruments/common_base.py`'s `CommonBase` (parent of both
`Instrument` and `Channel`): its `control()`/`measurement()`/`setting()`
static methods build a Python `property` whose getter/setter closures call
`self.values()`/`self.write()`, run an optional `get_process`/
`set_process`, and validate/map through `validator=`/`values=`. A real
driver body is therefore just a sequence of class attributes like
`voltage = Instrument.control("VOLT?", "VOLT %g", "...")` — no manual
getter/setter methods per parameter. `CommonBase` also implements a
**Channel** pattern (`ChannelCreator`/`MultiChannelCreator`,
`add_child()`) for multi-channel instruments, each channel getting the
same `control`/`setting`/`measurement` factories scoped to its own
command prefix.

**Adapters** (`pymeasure/adapters/`) decouple driver logic from transport:
an abstract `Adapter` base (`_write`/`_read`/`_write_bytes`/`_read_bytes`),
concretely implemented by `VISAAdapter` (GPIB/serial/TCP/USB via PyVISA,
"the workhorse of the library," can share one connection across several
instrument objects), `SerialAdapter` (direct pyserial), and
`PrologixAdapter` (Prologix GPIB-USB controller). A genuine
simulated/fake-transport pattern exists for testing:
`pymeasure/adapters/protocol.py`'s `ProtocolAdapter`, driven by a
`comm_pairs` list of expected `(sent, received)` tuples and asserted via
`pymeasure.test.expected_protocol()` — the direct analog of a fake-driver
test harness, though it's protocol/command-level, not a full simulated
instrument with realistic internal state.

### 3.2 GUI ↔ logic communication

`pymeasure/experiment/procedure.py`'s `Procedure` declares parameters as
class-level `Parameter` descriptors and implements `execute()` (the
measurement loop). Two methods are deliberately stubbed to raise
`NotImplementedError('should be monkey patched by a worker')`: `emit()`
and `should_stop()` — a `Procedure` is transport-agnostic by design.
`pymeasure/experiment/worker.py`'s `Worker` runs a `Procedure` and
communicates over a `monitor_queue` — a **multiprocessing/queue-based**
boundary, not direct Qt signal emission from inside the worker itself
(the `Worker` also runs a small TCP-style listener so procedures can run
fully out-of-process). `pymeasure/display/manager.py`'s `Manager` wraps
that queue in a `Monitor` QObject and connects real Qt signals
(`worker_running`, `worker_failed`, `progress`, `status`, `log`) to GUI
slots. So the full path is: `Procedure.emit()` (monkey-patched) →
multiprocessing queue → `Monitor` QObject → Qt signals → GUI. It's a
hybrid — queue for the actual data transport across a process boundary,
Qt signals only for the final same-thread GUI delivery. `ExperimentQueue`
+ `Manager.next()` implement simple sequential auto-advancing of queued
procedures, not a full scheduler.

### 3.3 Scan/measurement data structure ↔ GUI mapping

Confirmed: PyMeasure is fundamentally a **row-oriented parameter-sweep**
framework, not an N-D array/imaging framework.
`pymeasure/experiment/results.py`'s `Results` writes exclusively to
**CSV** (pandas-backed, `CHUNK_SIZE=1000`-row lazy loading so a live file
being appended by the `Worker` can be re-read incrementally).

Worth being precise rather than dismissive here, though: there **is** a
bolt-on 2D/image capability and a genuine crosshair.
`pymeasure/display/widgets/image_widget.py`'s `ImageWidget` lets a user
pick X/Y/Z columns from the same flat CSV-backed table and
`ResultsImage` (`pymeasure/display/curves.py`, a `pg.ImageItem` subclass)
rebuilds a 2D image by iterating `data.iterrows()` and regridding each row
into a pixel — a *post-hoc regrid of tabular rows*, not a native array
written into during acquisition. A real `Crosshairs` class
(`curves.py`) is wired into every `PlotFrame` (so both 1D `PlotWidget`
and, by inheritance, `ImageWidget`) via `sigCoordinatesChanged`-style
signal/slot, refreshed off the plot's own timer. There is **no** ROI/
box-select widget and **no** optimizer extension anywhere in
`pymeasure/display/widgets/`. The closest thing to multi-dimensional
scanning is `sequencer_widget.py`'s `SequencerWidget` — nested/
hierarchical parameter sweeps (a tree of parameter × sequence-expression
rows) — but each still lands in the same flat CSV `Results` model, run as
a sequence of independent 1D procedures rather than one N-D acquisition.

### 3.4 Config-driven wiring

**None.** Confirmed by reading the adapters/instruments code and the
tutorial docs directly: instrument instantiation is always explicit
Python — `sourcemeter = Keithley2400("GPIB::4")`, or with an explicit
adapter object, including context-manager form
`with Keithley2400("GPIB::4") as sourcemeter:`. No `.ini`/`.yaml`/`.toml`
loader or declarative role→driver registry exists anywhere in
`pymeasure/experiment/`. Wiring instruments to physical addresses is
100% imperative Python, left entirely to the user's own script — the
opposite end of the spectrum from qudi's YAML-driven module graph.

### 3.5 Save/export pipeline

CSV-only — no HDF5 or other binary/container format anywhere in
`results.py`. `Results.header()` produces a reconstructable text header:
a `# Procedure: <ClassName>` line, a `# Parameters:` block with one
`#     param_name: param_value` line per registered `Parameter`, then a
`# Data:` marker before the CSV column-header row.
`Results.parse_header()`/`Results.load()` symmetrically reconstruct a
full `Procedure` + `Results` object from a saved file (falling back to a
generic `UnknownProcedure` if the original class isn't importable) — a
clean, simple, fully text-based round trip.

### 3.6 License

**MIT** (confirmed: `LICENSE` at repo root, standard permissive text,
"Copyright (c) 2013-2026 PyMeasure Developers"). Adapting patterns,
naming, or structure carries essentially no legal risk beyond retaining
attribution if code were copied verbatim — flagged for completeness per
the constraint, but this is the least restrictive of the three by a wide
margin.

---

## 4. Comparison and what to borrow

### 4.1 Instrument abstraction

All three converge on the same shape: a base class with a handful of
abstract methods a driver subclasses, a declarative description of what
the device can do, and a swappable simulated backend behind the *same*
interface as the real one (qudi's `*_dummy.py`, pyMoDAQ's
`pymodaq_plugins_mock`, PyMeasure's `ProtocolAdapter` + `Instrument`
subclass). Three things each does noticeably better than a flat
`{name: dtype}` schema:

- **Qudi's `ScannerAxis`/`ScannerChannel`** carry real per-axis hardware
  limits (`value_range`, `step_range`, `resolution_range`,
  `frequency_range`) *and* clipping helpers, separate from whatever a
  given scan chooses to sweep.
- **PyMeasure's `CommonBase.control()`** is the cleanest *declarative
  property* pattern of the three — a driver body is a sequence of class
  attributes, no hand-written getters/setters at all.
- **PyMoDAQ's entry-point plugin discovery** is the most decoupled —
  installing a new instrument package is enough; no central registry file
  to edit.

**Borrow**: qudi's richer per-axis capability object (hardware
min/max/step, not just a bare tuple) — this directly unblocks a real
"Full Range" action and sensible default-filling in LabPilot's own Axis
Range Settings dialog. PyMeasure's declarative property factory is
worth studying for any *new* adapter code, but rewriting ~300 existing
adapters for a syntactic win isn't a good trade against "preserve what's
50-60% working."

### 4.2 GUI ↔ logic communication

Qudi and pyMoDAQ are the same pattern at different granularity: **one Qt
thread per long-lived module** (qudi: per Logic module; pyMoDAQ: per
instrument), Qt signals/slots doing the cross-thread marshaling
automatically, all in one process. PyMeasure instead runs each
measurement in a **separate process** via `multiprocessing`+queue
(`Worker`), with Qt signals only for the final same-process GUI hop —
trading a bit of latency for real crash isolation (a runaway procedure
can't take the GUI down with it).

**LabPilot does none of these — and that's a real, deliberate structural
difference worth being explicit about, not a gap to close.** The desktop
Qt windows and the FastAPI backend are **separate processes talking over
HTTP**, with the desktop side polling on a fixed `QTimer` interval
(`InstrumentPoller`/`WorkflowStatePoller`, ~200ms) rather than receiving
a push the instant new data exists. This is *more* decoupled than any of
the three references — it's what lets the same backend serve both the
native Qt windows and the React web frontend simultaneously — but it
puts a hard floor under how "instant" anything can feel: even a perfect
qudi-style crosshair is bounded by the poll interval, not by how fast the
hardware itself actually updates. Worth flagging as a known ceiling for
Phase 3, not something to silently work around.

### 4.3 Scan data structure ↔ GUI mapping

A real spread here. **Qudi's `ScanData` is hard-capped at 1D or 2D** — an
"N-axis scanner" in qudi's own GUI is actually *one dock per axis pair*,
each independently 1D/2D, never one N-D array. **PyMoDAQ's
`DataWithAxes` is genuinely N-D**, with a `nav_indexes` tuple baked into
the data object itself distinguishing scan axes from signal axes, and a
pluggable `Scanner`/`ScannerBase` factory supporting linear, spiral, and
random scan geometries, not just a rectangular raster. **PyMeasure has no
array-scan model at all** — row-oriented CSV with a post-hoc image
regrid bolted on.

LabPilot's own omniscan (built earlier this session) is, in spirit,
closest to pyMoDAQ's real N-D model — one flat array + axis names/
positions, reshape-and-project rather than pre-committing to a fixed
dimensionality — and goes a step further than *either* reference in one
specific way: **a non-0D detector's own axes (a spectrometer's
wavelength axis, a camera's row/col pixels) get appended as extra
dimensions alongside the actuator's scanned axes, auto-detected from the
bound instrument's schema.** Neither qudi (hard 1D/2D cap, single-channel-
per-array) nor pyMoDAQ's own scan extension does exactly this
combination natively — worth recognizing as already-good, not just gaps.

What LabPilot doesn't have that both references do: qudi's dedicated
optimizer dock+logic (LabPilot has a single re-scan-and-recenter
endpoint, deliberately kept minimal per earlier direction in this
project); pyMoDAQ's pluggable scan-geometry system (LabPilot only
rasters a rectangular grid); and — the most concrete, immediately
fixable one — **a real value-scale indicator**. Qudi's colorbar is a
genuine always-visible widget (beside the image, not embedded in it);
LabPilot's scanner GUI currently has *no* colorbar at all after the most
recent revision (removed per direct request, replaced with an "auto-
level" toggle that only controls auto-scaling behavior, not a value
reference the user can actually read).

### 4.4 Config-driven wiring

Qudi wires the *entire application graph* in one static YAML file,
resolved once at launch (`Connector`s point at other module instances by
name; activation order is derived automatically from the dependency
graph). PyMoDAQ's XML preset is comparable granularity but swappable at
runtime by loading a different preset file — each `<move0N>`/`<det0N>`
block names a logical role and embeds which plugin class + settings
back it. PyMeasure has no config layer at all — everything is imperative
Python.

**LabPilot splits this in two, and the split is itself the interesting
design point**: an instrument *set* (flat JSON list of which real
instruments exist + their connection params — this is the closer analog
to "what hardware is plugged in") is entirely separate from a workflow's
*role bindings* (`instrument_bindings` in that workflow's own metadata —
which instrument currently plays "actuator" vs "detector" for *this*
workflow specifically, rebindable at any time over REST without
restarting anything). This is more flexible than qudi's one-graph-per-
launch model — the same instrument set serves arbitrarily many
differently-role-configured workflows simultaneously — but it means
there's no single file that documents "what is this whole apparatus,"
the way qudi's config or pyMoDAQ's preset does. Worth naming as a
genuine trade-off in Phase 3, not obviously worth abandoning.

### 4.5 Save/export

Qudi: plain text/CSV/NPY only, rich reconstructable metadata headers, no
HDF5 in qudi-core itself. PyMoDAQ: a full HDF5 hierarchy — one group per
scan step nesting that step's detector/actuator readings — plus a small
pluggable exporter factory (`.h5`/`.txt`/`.npy`/third-party formats).
PyMeasure: CSV-only, with a clean symmetric header round-trip
(`Results.header()`/`Results.parse_header()`/`Results.load()`
reconstructing a full `Procedure`+`Results` from a saved file).

**LabPilot already has the right shape for the pyMoDAQ-style path and
isn't using it**: `core/storage/hdf5.py`'s `HDF5Writer` — subscribes to
the EventBus, writes chunked HDF5 — is fully built but never
instantiated anywhere in the workflow execution path. Right now the
scanner GUI's only "save" capability is a PNG snapshot of the current
view (added this session, matching qudi's Save button's *presence* but
not its *purpose* — qudi saves the actual numbers, LabPilot currently
saves a picture of them). This is the single most concrete, closest-to-
done gap identified in this whole study.

### 4.6 Licensing summary

| Framework | Assumed in brief | Actually confirmed |
|---|---|---|
| Qudi | GPLv3 | **LGPLv3 per-file** (every file header checked said "Lesser"); repo also ships a GPLv3 `LICENSE` alongside `LICENSE.LESSER` — dual-file, but the operative per-file license is LGPL |
| pyMoDAQ | CeCILL-B | **MIT** (current 5.x monorepo, confirmed via `LICENSE` + GitHub license API); CeCILL-B unconfirmed for any historical pre-monorepo release |
| PyMeasure | MIT | **MIT**, confirmed |

None of this blocks the stated goal (re-deriving understood patterns in
LabPilot's own code, not copying files) — copyright protects expression,
not architecture/ideas. It only matters if any *actual code* gets copied
verbatim, which Phase 3's plan should avoid entirely.
