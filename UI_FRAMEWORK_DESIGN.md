# UI Framework Design (Phase 2)

Tier-3 UI component catalog across Qudi, pyMoDAQ, and PyMeasure, LabPilot's
own current tier-3 state, and a composition-system design building on both.
Companion to `ARCHITECTURE_NOTES.md` (hardware abstraction/GUI↔logic/save
pipeline) and `LOGIC_LIBRARY_NOTES.md` (tier-2 scanning/optimizer/acquisition
logic). Every claim cites a real file read directly — Qudi from the local
checkouts, PyMeasure from the installed `pymeasure` package (0.16.0), and
pyMoDAQ's **GUI layer** from the installed `pymodaq_gui`/`pymodaq_utils`/
`pymodaq_data` packages (5.2.9/5.2.7/5.2.9 — these three support packages
*are* pip-installed locally, unlike the core `pymodaq` package itself, which
`LOGIC_LIBRARY_NOTES.md` had to fetch from GitHub for the scanning/optimizer
extensions).

No code is copied verbatim anywhere in this document or planned from it.

---

## 1. LabPilot's own current tier-3 state (the baseline this design extends)

Before cataloging the three reference frameworks, it matters that LabPilot
**already has** a tier-3 component system for one half of its UI — the
composition design below is an *extension* of an existing, working pattern,
not something built from nothing.

- **`components/base.py`**: `UIComponent` (metaclass `ComponentMeta` —
  every subclass self-registers into `COMPONENT_REGISTRY[component_type]`
  by a `component_type` class attribute), constructed as `COMPONENT_REGISTRY
  [spec["type"]](window, ctx, **{k: v for k, v in spec.items() if k !=
  "type"})`, with `default_params` merged under whatever a block declares.
  `.build()` does the actual widget/dock construction.
- **`config/ui_blocks.toml`**: keyed by `(kind, dimensionality)` — e.g.
  `[detector."1D"]`, `[actuator."ND"]` — each a `blocks = [{type = "...",
  ...params}, ...]` list, read fresh every time an `InstrumentWindow` opens
  (no restart needed to change layout/defaults). Seven registered component
  types today: `toolbar`, `time_series`, `poll_rate`, `settings_tree`,
  `viewer` (dimensionality-parametrized: 1D spectrum / 2D image),
  `hyperspectral_viewer` (ND), `move_control`.
- **This is, independently, the same shape as pyMoDAQ's `ViewerFactory`/
  dimensionality-keyed dispatch (§2.1) and PyMeasure's declarative
  `widget_list` (§4.3)** — LabPilot converged on the same idea for
  per-*instrument* windows without having read either at the time.
- **The gap**: workflow-level UI (`workflow_window.py`, `components/
  workflow_result.py`, `components/axes_control.py` — all built this
  session) does **not** go through `UIComponent`/`COMPONENT_REGISTRY` at
  all. `_add_result_view` is a hand-written if/elif on `result_ui.get
  ("type")` (`"image2d"`/`"spectrum"`/`"ndscan"`); `_add_axes_control`/
  `_add_optimizer_dock` are hand-written methods on `WorkflowWindow`
  itself, not registered component classes a `RESULT_UI` block-list could
  declare declaratively. §5 below proposes closing this gap.

---

## 2. Component catalog by category

### 2.1 Plots & image viewers (0D / 1D / 2D / ND)

- **Qudi** (`qudi-core/src/qudi/util/widgets/plotting/`): a full custom
  pyqtgraph-based toolkit, not bare pyqtgraph — `PlotWidget`/`ImageWidget`
  (`plot_widget.py`/`image_widget.py`) each come as a *mixin stack*:
  `MouseTrackingMixin` (cursor position readout), `RubberbandZoomMixin`
  (drag-a-rectangle to zoom — **this is qudi's real "define the range by
  interacting with the plot" feature**, confirming a feature this project
  considered and set aside earlier this session), `DataSelectionMixin`
  (click/drag to select a region of the *data*, distinct from zoom) — each
  combinable independently, e.g. `RubberbandZoomSelectionPlotWidget
  (RubberbandZoomMixin, DataSelectionMixin, MouseTrackingMixin, PlotWidget)`.
  `InteractiveCurvesWidget` (`interactive_curve.py`, 734 lines) is the
  full 1D case: multiple named curves, a `PlotSelectorWidget` to toggle
  which are visible, a `CursorPositionLabel`. No dedicated N-D viewer in
  qudi-core/qudi-iqo-modules — confirms the earlier finding that qudi's own
  scanning stack tops out at 2D by design (`LOGIC_LIBRARY_NOTES.md` §1.1).
- **pyMoDAQ** (`pymodaq_gui/plotting/data_viewers/`): `Viewer0D`/`Viewer1D`/
  `Viewer2D`/`ViewerND`, each a real, separate class (345/858/1149/848
  lines respectively) — dispatched by a small, clean factory:
  `get_viewer_enum_from_axes(Naxes)` (0→Viewer0D, 1→Viewer1D, 2→Viewer2D,
  else→ViewerND) and `ViewerFactory.register('Viewer0D'/...)`. `ViewerND`
  (`viewerND.py`) is the most sophisticated single file found in this whole
  research pass (both phases): it splits an N-D array's axes into **"nav"
  axes** (which you scroll/click through — one slider/crosshair per nav
  axis) and **"signal" axes** (what's actually plotted, as a 0D/1D/2D view,
  at the currently-selected nav position) via a `BaseDataDisplayer` strategy
  with two concrete implementations — `UniformDataDisplayer` (nav axes form
  a regular grid) and `SpreadDataDisplayer` (irregular/scattered nav
  positions, using Delaunay triangulation to still render a coherent 2D nav
  map). This nav-axes/signal-axes split is *exactly* the same conceptual
  distinction LabPilot's own `NDScanResultView` makes between "actuator
  axes" (get their own 2D projection panels + crosshair) and "detector-
  internal axes" (registered but not plotted, per this session's explicit
  request) — direct confirmation this project's current design already
  independently matches the field's most sophisticated N-D viewer's core
  distinction, just without (yet) `ViewerND`'s own nav-axis slider/
  crosshair-driven single-slice display as an *alternative* to projection-
  averaging (see §5's open question).
  `ViewerDispatcher` (`viewer.py`) is the composition glue: given a
  heterogeneous `DataToExport` (N `DataWithAxes` items, each any
  dimensionality), it picks the right viewer type per item
  (`ViewersEnum.get_viewers_enum_from_data`), builds/reuses one dock per
  item, and only rebuilds a dock whose *viewer type* actually changed since
  last time (`update_viewers`'s `Nviewers_to_leave` walk) — avoiding needless
  dock churn frame to frame. This is the single clearest "factory/config-
  driven pattern for snapping components together...without bespoke code"
  reference found — see §5.
- **PyMeasure** (`pymeasure/display/widgets/`): `PlotWidget`/`ImageWidget`/
  `TableWidget` (curves.py's `ResultsCurve`/`ResultsImage`/`BufferCurve` are
  the underlying pyqtgraph items) — one `PlotFrame`/`ImageFrame` per curve/
  image, added/removed as `Procedure` runs are queued/completed
  (`TabWidget.new_curve`/`.load`/`.remove`, see §4.3). No ND viewer — matches
  PyMeasure's whole philosophy of one flat table of measured columns per
  run, not a multi-dimensional array.
- **LabPilot today**: `components/viewer.py` (1D spectrum / 2D image,
  dimensionality-parametrized — the *instrument-window* case),
  `components/hyperspectral_viewer.py` (ND, instrument-window case),
  `components/workflow_result.py`'s `Image2DResultView`/`SpectrumResultView`/
  `NDScanResultView` (the *workflow-window* case, built this session,
  modeled directly on qudi's `Scan2DWidget`/`ScanDockWidget`).

### 2.2 Axis / range controls

- **Qudi**: `axes_control_dockwidget.py` (per-axis live-position slider,
  always visible) + `scan_settings_dialog.py` (range/resolution/frequency,
  on-demand) — the exact split LabPilot's own `AxesControlWidget`/
  `AxisRangeSettingsDialog` were modeled on this session, before the most
  recent request merged Min/Max/Points back onto the always-visible row too
  (`axes_control.py`'s current docstring records this history). `DoubleSlider`
  (`util/widgets/slider.py`) is a *native* float-range `QSlider` — LabPilot's
  `AxisSliderRow` (`components/widgets.py`) instead wraps a plain integer
  `QSlider` with manual float-mapping math; qudi's native version is simpler
  at the cost of being qudi-specific code, not a strong enough reason alone
  to adopt but worth knowing it exists.
- **pyMoDAQ**: no single always-visible axes-control dock — range/step
  configuration lives in the `Scanner`'s own `ParameterTree`
  (`LOGIC_LIBRARY_NOTES.md` §1.2), and live jogging happens through each
  `DAQ_Move`'s own control panel (`control_modules/daq_move_ui/`, not
  re-read this pass — covered structurally in `ARCHITECTURE_NOTES.md`).
- **PyMeasure**: `inputs.py`'s `ScientificInput`/`VectorInput` are the
  closest analogs — plain per-parameter input widgets auto-generated from a
  `Procedure`'s declared `Parameter`s (`inputs_widget.py`), not a live-
  jogging slider at all (no notion of "current actuator position" exists
  in PyMeasure's model — see `LOGIC_LIBRARY_NOTES.md` §1.3).
- **`ScienDSpinBox`/`ScienSpinBox`** (qudi, `scientific_spinbox.py`, 1526
  lines) — SI-prefix-aware numeric entry (type `1.2u` or see `1.234 µm`
  auto-formatted) — a genuinely nicer atom than LabPilot's own
  `ProfessionalSpinBox` (a plain `QDoubleSpinBox`), worth adopting the
  *idea* of (not the qudi-specific implementation, LGPL) if LabPilot ever
  wants engineering-notation entry.

### 2.3 Live parameter trees / declarative settings forms

- **Qudi**: `parameter_editor.py`'s `ParameterEditor`/`ParameterEditorDialog`
  — generic form from a declarative spec, dialog variant for on-demand
  editing (the same on-demand-dialog idea as `scan_settings_dialog.py`,
  generalized). `literal_lineedit.py`'s `LiteralLineEdit`/`ListLineEdit`/
  `TupleLineEdit`/`SetLineEdit`/`DictLineEdit` — validated-while-typing
  widgets for exactly the "edit a non-primitive value as a Python literal"
  problem LabPilot's now-removed generic "Workflow Settings" tree solved
  with a bare string field + `ast.literal_eval` on submit; qudi's version
  validates live rather than only on commit — a nicer atom worth the idea,
  independent of that removed dock's fate.
- **pyMoDAQ**: `pymodaq_gui/managers/parameter_manager.py` (766 lines) —
  `ParameterManager` mixin, the base every `Scanner`/`ScannerBase`/
  `CustomApp` (§4.2) subclass gets its `self.settings`/`self.settings_tree`
  from; effectively pyMoDAQ's one universal settings-tree building block,
  reused at every tier (scanner config, per-extension config, per-viewer
  config) rather than a separate mechanism per context.
- **PyMeasure**: no unified tree widget — `inputs_widget.py`'s `InputsWidget`
  builds one labeled input row per declared `Parameter`
  (`StringInput`/`IntegerInput`/`BooleanInput`/`ListInput`/`ScientificInput`/
  `VectorInput`, `inputs.py`), reflecting the framework's per-parameter,
  not tree-structured, model.
- **LabPilot today**: `components/settings_tree.py` (`SettingsTreeComponent`
  — generates a pyqtgraph `ParameterTree` from a `DeviceSchema` at runtime,
  the instrument-window case) plus the now-removed generic workflow-params
  tree (§1's gap — no current tree-based surface for a workflow's own
  non-axis parameters).

### 2.4 Device / acquisition status panels

- **Qudi**: no single generic "status panel" widget found across
  `util/widgets/` — each `<name>gui.py` builds its own status labels/icons
  inline per module (matches `ARCHITECTURE_NOTES.md`'s earlier finding that
  qudi has no equivalent of a generic per-instrument status dock; LabPilot's
  own `StatusLabel` (`components/widgets.py`) is arguably already ahead of
  qudi here as a genuinely reusable atom).
  `loading_indicator.py`'s `CircleLoadingIndicator` — a busy/spinner
  widget, the one generic "something is happening" atom qudi does provide.
- **pyMoDAQ**: no dedicated status-panel class either — status is folded
  into each control module's own toolbar/settings tree (e.g. `DAQ_Move`'s
  own move-in-progress indicator, not re-read in detail this pass).
- **PyMeasure**: `estimator_widget.py`'s `EstimatorWidget` is the one
  standout, distinctive-to-PyMeasure concept — shows a *time estimate*
  before running, computed from `Procedure.get_estimates()` (Phase 1's
  finding): "this measurement will take approximately 4m 30s," refreshed
  live as parameters change. Nothing else in either other framework
  provides pre-run duration estimation as a first-class UI piece — worth
  flagging as a genuinely distinctive, adoptable idea (the estimate
  *source* — asking a workflow to estimate its own duration from its
  current parameters — is a tier-2 concept a LabPilot workflow template
  could optionally implement, surfaced by a small tier-3 widget).
- **LabPilot today**: `StatusLabel` (generic colored status text) and
  per-instrument connect/status already exist; no time-estimator anywhere.

### 2.5 ROI & crosshair tools

- **Qudi** (`plotting/marker.py`, 936 lines): `InfiniteCrosshair` (two
  perpendicular lines, no box), `InfiniteLine`, `LinearRegion` (the qudi-
  native equivalent of pyqtgraph's bare `LinearRegionItem`, integrated with
  the same mixin plot/view-box stack as §2.1), `Rectangle`, and
  `InfiniteCrosshairRectangle` (lines + resizable box — the exact class
  LabPilot's own `_Crosshair` was modeled on, already cited throughout
  `components/workflow_result.py`'s docstrings). `plotting/roi.py`'s
  `RectangleROI` is qudi's ROI-selector-for-scan-area case (feeds a scan
  range from a drawn rectangle, adjacent to `RubberbandZoomMixin` but
  distinct — persists as a *scan area selector*, not a one-shot zoom).
- **pyMoDAQ**: `managers/roi_manager.py` (662 lines, not read in detail this
  pass) — a generic multi-ROI manager (add/remove/name several ROIs on one
  viewer, e.g. multiple regions-of-interest on a camera image simultaneously)
  — a genuinely different use case from qudi's single-crosshair-per-panel
  model: *several independently named regions* rather than one position
  marker, worth noting as a capability LabPilot doesn't have any equivalent
  of yet (relevant if a future workflow wants "average over these three
  regions of the image," not just "one crosshair position").
- **PyMeasure** (`curves.py`): `Crosshairs` — a much simpler single
  crosshair (two `InfiniteLine`s, no resizable box, no move-actuator
  callback — PyMeasure has no live actuator to move, consistent with
  Phase 1's finding).
- **LabPilot today**: `_Crosshair`/`_ScanImagePanel.add_crosshair` — closely
  matches qudi's `InfiniteCrosshairRectangle` already (colors, default box
  size, drag-to-move-actuator semantics). No multi-named-ROI manager
  equivalent to pyMoDAQ's `ROIManager`.

### 2.6 Optimizer panels

- **Qudi** (`gui/scanning/optimizer_dockwidget.py`, read in full this pass):
  `OptimizerDockWidget` builds **one plot pane per sequence step**
  (`LOGIC_LIBRARY_NOTES.md` §2.1's `OptimizerScanSequence` — e.g. a 2D pane
  for `('x','y')` then a 1D pane for `('z',)`), each with a display-only
  (non-draggable — `set_selection_mutable(False)`) marker showing the
  fit-found optimum, plus a text summary label (`update_result_label`,
  formats every found axis:value pair with its fit σ). LabPilot's own
  Optimizer dock (`_ScanImagePanel` reused with `on_move=None`) is a
  *simplified* version of this — one fixed 2D grid pane, not one pane per
  sequence step — a direct, honest gap relative to qudi's real multi-step
  optimizer display, worth closing if/when LabPilot's optimizer logic
  itself grows a real N-D sequence (tier-2, `LOGIC_LIBRARY_NOTES.md` §2.1's
  finding) rather than today's single fixed-range grid.
- **pyMoDAQ**: no single dedicated optimizer *dock widget* class — the
  `GenericOptimization` extension (`LOGIC_LIBRARY_NOTES.md` §2.2) composes
  its display from the same `Viewer0D`/`Viewer1D`/`Viewer2D` building blocks
  as everything else (`do_live_plot`/`update_data_plot`, seen in the
  `optimizer.py` method listing but not read in detail this pass) — i.e.
  pyMoDAQ's optimizer UI is not a bespoke widget category at all, just
  another *consumer* of the generic viewer-dispatch system (§2.1). This is
  the more composition-system-consistent answer of the two, and a strong
  argument for LabPilot's own optimizer panel eventually being "just another
  `_ScanImagePanel`/`NDScanResultView` instance," which is in fact already
  exactly how LabPilot built it this session (reusing `_ScanImagePanel`
  rather than a bespoke class) — independently arriving at pyMoDAQ's answer.
- **PyMeasure**: none (`LOGIC_LIBRARY_NOTES.md` §2.3 — no optimizer logic,
  so no optimizer UI either).

### 2.7 Save / export controls

- **Qudi**: no dedicated save-dialog *widget* found in `util/widgets/` —
  save/export is a `SaveLogic` (tier-2) concern, triggered from each
  module's own toolbar action, writing via `qudi.util.datastorage`
  (`TextDataStorage`/`CsvDataStorage`/`NpyDataStorage` — cataloged already
  in `ARCHITECTURE_NOTES.md`'s save/export comparison). No colorbar-adjacent
  "export this view as an image" dialog beyond whatever pyqtgraph itself
  provides.
- **pyMoDAQ** (`pymodaq_gui/h5modules/`): `saving.py` (an `H5Saver`
  settings/status widget), `h5browser.py`/`browsing.py` (a full standalone
  HDF5 file browser — navigate groups/datasets, preview data, genuinely a
  bigger tool than a save dialog, closer to a small file-format-aware data
  explorer). The richest save/export UI of the three frameworks by a wide
  margin, consistent with pyMoDAQ's HDF5-native save pipeline
  (`ARCHITECTURE_NOTES.md`'s finding).
- **PyMeasure** (`results_dialog.py`): `ResultsDialog(QFileDialog)` — a
  `QFileDialog` subclass whose preview pane is one of the `TabWidget`-
  contract widgets (§4.3) in "preview mode," so opening a previous run's
  data file shows a live plot/table preview before you commit to loading it
  — a nice small idea (reusing the *same* plot/table widget class for both
  live display and file-preview, via `TabWidget.preview_widget`).
- **LabPilot today**: `components/hdf5_export.py` (`save_workflow_result_
  hdf5`, built this session — a purpose-built writer, deliberately not
  reusing the older event-model-mismatched `core/storage/hdf5.py`, see that
  module's own docstring) + `workflow_window.py`'s "Save All Scans (PNG)"/
  "Save Data (HDF5)…" menu actions. No HDF5 *browser* equivalent to
  pyMoDAQ's `h5browser.py` — a real, notable gap if LabPilot's saved data
  ever needs in-app inspection rather than opening in an external tool.

### 2.8 Logging consoles

- **Qudi** (`qudi-core/src/qudi/core/gui/main_gui/logwidget.py`): `LogWidget`
  — a `QTableView` (`LogTableWidget`) over a `QSortFilterProxyModel`
  (`LogFilterProxy`, filters by level: debug/info/warning/error), part of
  the *global* manager window, not a per-module/per-workflow dock — one
  log console for the whole running application.
- **pyMoDAQ**: no equivalent found in `pymodaq_gui` (logging goes through
  `pymodaq_utils.logger`, `set_logger`/`get_module_name`, seen throughout
  every file read in both phases — standard Python logging, no dedicated
  in-app viewer widget turned up in this pass).
  message boxes (`pymodaq_gui.messenger.messagebox`, seen used for user-
  facing warnings) are the closest thing, not a persistent console.
- **PyMeasure** (`display/widgets/log_widget.py`, `display/log.py`):
  `LogWidget` + `HTMLFormatter` (color-coded HTML log rendering) +
  `LogHandler` (a `logging.Handler` subclass feeding the widget) — same
  per-app-window console concept as qudi's, HTML-formatted instead of a
  table model.
- **LabPilot today**: `status_bar.showMessage(...)` (a single transient
  status-bar line per window, used pervasively) — no persistent, scrollable,
  filterable log console anywhere in the desktop app. A real, clean gap
  relative to *all three* reference frameworks, each of which has some form
  of this (global manager window in qudi/PyMeasure's case) — worth
  considering for a future pass, out of scope for the current scanner-
  workflow proving ground (Phase 4).

### 2.9 Results browser / history / table

- **Qudi**: `poi_manager` (`gui/poimanager/`, not read this pass) is the
  closest analog — a saved-points-of-interest manager, domain-specific
  rather than a generic run-history browser.
- **pyMoDAQ**: `pymodaq_gui/plotting/navigator.py` (not read in detail this
  pass, name suggests a saved-scan-history/navigation tool, consistent with
  its HDF5-native save model) + the `h5browser.py` above doubling as
  history browsing.
- **PyMeasure** (`display/browser.py`/`browser_widget.py`): `Browser`/
  `BrowserItem` — a `QTreeWidget` of every queued/running/finished
  `Procedure` run, one checkable row per run (toggle a run's curve
  visibility on/off in the plot without re-running it) — the cleanest,
  most directly "which of my past runs am I looking at right now" widget
  of the three. `table_widget.py`'s `ResultsTable`/`Table`/`PandasModelBy
  Row`/`PandasModelByColumn` — a raw-data table view, Pandas-backed,
  switchable row-major/column-major.
- **LabPilot today**: nothing — a workflow's "last completed run" is the
  only state kept (`_on_execution_state`'s `last_results` fallback); no
  browsable history of prior runs within a session. Out of scope for
  Phase 4's scanner proving ground, worth a note for later.

### 2.10 Fit / analysis widgets

- **Qudi** (`util/widgets/fitting.py`, 409 lines): `FitWidget` (pick a
  registered fit model, run it, show results) + `FitConfigurationWidget`/
  `FitConfigurationDialog`/`FitConfigurationListView` (manage a named set of
  fit-model configurations, reusable across different data — e.g. "my usual
  Lorentzian ODMR fit" saved once, applied to many runs). `odmr_fit_
  dockwidget.py` (39 lines — thin, just wires `FitWidget` into ODMR's own
  dock) confirms this is meant to be *the* reusable fit UI, not
  reimplemented per experiment type.
- **pyMoDAQ**: fitting is folded into specific extensions/plugins rather
  than a standalone generic widget (not surfaced as its own catalog entry
  in this pass's file list).
- **PyMeasure**: no fit widget — fitting, if needed, is user code operating
  on `Results` data directly.
- **LabPilot today**: an ad-hoc `_fit_peak` (Gaussian/Lorentzian) inside
  `components/viewer.py`, not a standalone reusable widget/dialog — qudi's
  `FitWidget`/`FitConfigurationDialog` split (generic runner + a separate,
  reusable named-configuration manager) is a materially nicer shape than
  LabPilot's current single inline helper, worth the *idea* for a future
  pass (not LGPL code, just the two-piece design).

### 2.11 Docking & window-composition infrastructure

- **Qudi**: `util/widgets/advanced_dockwidget.py`'s `AdvancedDockWidget`
  (40 lines — a small `QDockWidget` subclass, not read in full but short
  enough that its whole surface is visible from the class list; likely
  adds a close/restore convenience over bare `QDockWidget`, matching the
  pattern LabPilot's own `dock()` helper already provides). `collapsible.py`'s
  `CollapsibleWidget` — an expand/collapse section, useful for tucking away
  advanced/rarely-touched controls without a separate dialog (relevant to
  this session's earlier back-and-forth on where range/resolution editing
  should live — a collapsible section is a third option between "always
  visible" and "separate dialog" not yet considered).
- **pyMoDAQ** (`pymodaq_gui/utils/`): `dock.py`'s `DockArea`/`Dock` (built
  on `pyqtgraph.dockarea`, confirmed by the import in `viewer.py`) is
  pyMoDAQ's actual docking substrate — notably **not** Qt's native
  `QMainWindow.addDockWidget`/`QDockWidget` (which is what both qudi's and
  LabPilot's own windows use) but pyqtgraph's own dock-area implementation,
  which natively supports drag-out-to-separate-window
  ("poppable panels," Phase 4's own explicit requirement) as a built-in
  interaction, not something layered on afterward. `custom_app.py`'s
  `CustomApp(QObject, ActionManager, ParameterManager)` is the composition
  base every pyMoDAQ extension/GUI is built from — a **mixin + template-
  method** pattern: `setup_docks_and_widgets()`/`setup_menus_and_toolbars()`/
  `setup_actions()`/`connect_things()` are hook methods a new experiment-
  type GUI overrides, inheriting menu/toolbar/settings-tree/status-bar
  machinery for free rather than rewriting it per experiment (this is
  effectively pyMoDAQ's version of qudi's `GuiBase`, just built from
  composable mixins instead of a single base class hierarchy).
- **PyMeasure** (`display/windows/managed_window.py`): `ManagedWindowBase`
  — the third, most different composition philosophy: **pure constructor
  injection**, no subclassing hooks at all. You pass `widget_list=(plot_
  widget, table_widget, image_widget, ...)` (each already an instance
  implementing the small `TabWidget` contract — `new_curve`/`load`/`remove`/
  `set_color`/`preview_widget`/`clear_widget`, `widgets/tab_widget.py`) plus
  your `Procedure` subclass, and `ManagedWindowBase.__init__` builds: an
  auto-generated "Input Parameters" dock from that Procedure's declared
  `Parameter`s (`inputs_widget.py`), one `QDockWidget` per item in
  `widget_list`, an execution queue (`Manager`, Phase 1's finding), and (if
  present) Sequencer/Estimator docks. `ManagedWindow` (the common subclass)
  just pre-supplies a `PlotWidget`+`LogWidget` default `widget_list` so the
  common case needs zero subclassing at all — literally
  `ManagedWindow(procedure_class=MyExperiment).show()`.
- **LabPilot today**: plain `QMainWindow`+`QDockWidget` (matches qudi's own
  choice, not pyMoDAQ's pyqtgraph-dockarea choice) — Phase 4's "poppable
  into separate windows... secondary" requirement is achievable with plain
  Qt docks (`setFloating(True)` already exists as native `QDockWidget`
  behavior, used by this session's `_on_restore_default_view`) without
  needing pyqtgraph's dockarea, so no incompatibility to resolve, just
  worth knowing pyqtgraph's dockarea is the more purpose-built alternative
  if floating/popping ever needs to be more prominent than "secondary."

---

## 3. Composition-system comparison (the actual "factory or config-driven
pattern" question)

Three genuinely different philosophies for "snap components together into
a working GUI for a new experiment type without bespoke code":

| | Qudi | pyMoDAQ | PyMeasure |
|---|---|---|---|
| **Unit of composition** | A whole `<name>gui.py` `GuiBase` module + several hand-written `QDockWidget` subclasses per experiment type | A `CustomApp` subclass overriding template-method hooks (`setup_docks_and_widgets`, etc.) + generic `Viewer0D`/.../`ViewerND` dispatched by data dimensionality | A declarative `Procedure` subclass (parameters + measured columns) + a constructor-injected `widget_list` of already-built display widgets |
| **How a new experiment type is added** | Write a new `GuiBase` module + new dock widgets — the *most* bespoke code of the three, but the *most* control over exact layout/behavior | Subclass `CustomApp`, override hooks; viewer *type selection* (0D/1D/2D/ND) is automatic from data shape, but *layout*/composition is still hand-arranged in `setup_docks_and_widgets()` | Write one `Procedure` subclass; the *entire* GUI (params form + plot + table + log + queue) is generated with zero new UI code — least bespoke code of the three, least layout control |
| **Config-driven?** | Not for UI composition (`default.cfg` wires *modules*, i.e. tier-1/tier-2, not which UI widgets appear — `ARCHITECTURE_NOTES.md`'s config-driven-wiring finding was about module instantiation, not dock layout) | Partially — `Scanner`'s own settings are a `ParameterTree`, but which viewers appear is code (`ViewerDispatcher.add_viewer` calls), driven by data shape at runtime rather than a static config file | Not config-driven either — `widget_list` is Python-constructed, not read from a file; the "declarative" part is the `Procedure`'s `Parameter` class attributes, not a composition config |
| **Dimensionality-aware dispatch?** | No (2D ceiling, §2.1) | Yes — the central mechanism (`ViewerFactory`/`get_viewer_enum_from_axes`) | No (no ND concept at all) |

**LabPilot's own `ui_blocks.toml` (§1) is actually the most literally
*config-driven* of all four systems compared here** — none of the three
reference frameworks has an equivalent human-editable, hot-reloaded TOML/
YAML file mapping `(kind, dimensionality)` → a list of component blocks;
pyMoDAQ gets the closest with runtime dimensionality dispatch, but that
dispatch is Python code (`ViewerFactory`), not an editable config file the
way `ui_blocks.toml` is. This is worth being confident about rather than
under-selling: the instrument-window half of LabPilot's tier-3 is already
ahead of all three reference frameworks on the specific "config-driven, no
bespoke code" axis Phase 2 asked about — the design task is extending that
existing strength to workflow-level UI, not importing a pattern none of the
three frameworks actually has in this exact shape.

---

## 4. Design: extending `UIComponent`/`COMPONENT_REGISTRY` to workflow-level UI

This section is a design proposal only — no implementation in this phase,
per the phase constraints.

**Core idea**: treat a workflow's `RESULT_UI` declaration the same way
`ui_blocks.toml` already treats `(kind, dimensionality)` — as a spec that
resolves to a list of `{type, ...params}` blocks, built through the *same*
`COMPONENT_REGISTRY`, rather than the current hand-written if/elif in
`_add_result_view` plus separate hand-written `_add_axes_control`/
`_add_optimizer_dock` methods.

- **New registered component types**, alongside the existing seven:
  `scan_panel` (wraps today's `_ScanImagePanel` — one axis-pair projection,
  optionally with a crosshair), `ndscan_view` (wraps `NDScanResultView` —
  builds one `scan_panel` per actuator-axis-pair automatically, the
  "snap together without bespoke code" case pyMoDAQ's `ViewerDispatcher`
  models for heterogeneous `DataToExport`, applied here to a *single*
  N-D array's own axis pairs instead), `axes_control` (today's
  `AxesControlWidget`), `optimizer_panel` (today's reused `_ScanImagePanel`
  instance, per §2.6's finding that this is already the pattern pyMoDAQ
  itself converged on).
- **Dimensionality dispatch already has a template to follow**: pyMoDAQ's
  `get_viewer_enum_from_axes(Naxes)` (§2.1) is the direct model for how
  `RESULT_UI`'s declared axis count should select `scan_panel` (2 axes) vs.
  a plain curve dock (1 axis, today's `_build_panels`'s single-declared-axis
  fallback) vs. `ndscan_view` (3+ axes) — this project already does the
  0-vs-N-axis-count split ad hoc in `NDScanResultView._build_panels`;
  formalizing it as a registry lookup keyed by axis count (mirroring
  `ui_blocks.toml`'s dimensionality keys exactly) would let a *new*
  workflow template's `RESULT_UI` just declare its axes and get the right
  view automatically, the same promise `ui_blocks.toml` already delivers
  for instrument windows.
- **Open question, not resolved by this phase**: pyMoDAQ's `ViewerND` offers
  *two* ways to look at extra (detector-internal) axes — LabPilot's current
  choice (project/average over them, adjustable via the per-panel selectors
  this session merged in) versus `ViewerND`'s nav-axis slider/crosshair
  (pick one exact *slice* rather than averaging a range). Both are valid;
  LabPilot's current choice is arguably more useful for the ≤2D-actuator-
  scan case since it lets a range narrow toward zero-width (equivalent to
  slicing) while still defaulting to full-range averaging — worth
  revisiting only if a real workflow surfaces a case where exact-slice
  navigation is clearly better, not something to design further now.
- **What stays hand-written, deliberately**: `WorkflowWindow`'s Execute/
  Stop toolbar, the menu bar, and HDF5 save/export are workflow-*window*-
  level concerns that apply identically regardless of `RESULT_UI` shape —
  these don't need to become registry components, matching how `ui_blocks.
  toml` itself doesn't try to make the *window itself* declarative, only
  its per-(kind,dimensionality) content blocks.

This proposal is deliberately conservative — it extends an existing,
working mechanism (`COMPONENT_REGISTRY`) rather than introducing a second,
parallel composition system for workflows. Phase 3 (workflow composition —
tier-2 capabilities like scanning/optimizer/saving auto-wired into a
workflow) is a related but distinct question this document does not answer:
Phase 2 is only about *which UI pieces exist and how they snap together*,
not about *which tier-2 logic modules a workflow needs and how those get
wired in automatically* — that's explicitly Phase 3's job.

---

## 5. Licensing

- **Qudi**: every file read this pass (`plotting/*.py`, `scientific_
  spinbox.py`, `fitting.py`, `parameter_editor.py`, `literal_lineedit.py`,
  `logwidget.py`, `optimizer_dockwidget.py`, and the rest of `util/widgets/`)
  carries the same **LGPLv3** header confirmed in both prior notes files —
  no exceptions found in this pass either. Nothing copied verbatim; every
  description above is written independently from what was read.
- **pyMoDAQ**: `pymodaq_gui`/`pymodaq_utils`/`pymodaq_data` are separate
  PyPI packages from the core `pymodaq` package `LOGIC_LIBRARY_NOTES.md`
  fetched from GitHub, but part of the same repo/release train — confirmed
  **MIT** the same way (repo-level license, `PyMoDAQ/PyMoDAQ`).
- **PyMeasure**: confirmed **MIT** again — every file read this pass
  (`browser.py`, `sequencer_widget.py`, `managed_window.py`, `tab_widget.py`,
  etc.) carries the identical MIT header already seen in Phase 1's files.

MIT (pyMoDAQ, PyMeasure) permits more direct reuse than Qudi's LGPL if a
future phase ever wants to adapt a larger chunk of actual code rather than
just the pattern/shape — not exercised in this document, which describes
patterns only.
