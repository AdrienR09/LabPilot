"""Auto-generated native UI for a workflow.

One native `QMainWindow` showing this workflow's own UI only — the
Execute/Stop toolbar and (if the script declares one) its `RESULT_UI`
live/last-result view — not each referenced instrument's own per-kind
window (toolbar/viewer/settings_tree/move_control docks). Those already
exist as their own `InstrumentWindow`s (instrument_window.py), reachable
from the Instruments tab; duplicating them here just to show live data a
workflow doesn't otherwise expose was redundant chrome, not something this
window needs to own.

An `InstrumentContext` (schema, poller) is still built per referenced
instrument — not for any visible display, and its poller is never
started here: the crosshair/Axes Control positions this window shows are
the *target* (commanded) position, not a live actuator read-back (see
NDScanResultView's class docstring), so nothing in this window needs
faster-than-report_progress live data anymore. What's still needed from
each context is just its schema (units, hardware limits) and its
presence in `instrument_contexts` as confirmation the referenced role
actually resolved to a known instrument.

Which instruments this workflow references comes from the workflow
itself:
- A structured (node-based) workflow: every node's `device_refs` (see
  core/workflow/nodes.py — every node kind populates this).
- A script-only workflow (AI/hand-written via write_workflow_script, no
  nodes): statically scanned from the script's `session.get("...")` calls
  — `ast.parse` only, the script is never imported/executed just to build
  this window.
"""

from __future__ import annotations

# Pin the Qt binding before qtpy is imported by anything — the rule,
# and why it matters, live in labpilot/ui/qt_api.py.
import labpilot.ui.qt_api  # noqa: F401 — imported for its side effect

# isort: split

import ast
import warnings
from typing import Any, Optional

import numpy as np
from pymodaq_data.data import DataIndexWarning
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QStatusBar,
    QToolBar,
    QWidget,
)

warnings.filterwarnings("ignore", category=DataIndexWarning)

# Pure backend modules — no session, no hardware, no Qt. This process
# reaches *state* only over HTTP, which is why `backend_client` exists;
# a rule against importing backend *code* was a different claim, and the
# copies it produced (an axis decomposition, an optimizer axis list, two
# AST readers, two curve fits) each had to be kept in step with an
# original by hand. See core/workflow/scan_params.py.
from backend_client import (
    AsyncWriter,
    BackendClient,
    OptimizePoller,
    WorkflowStatePoller,
)
from block_config import load_workflow_blocks
from components.axes_control import (
    AxesControlWidget,
    AxisRangeSettingsDialog,
    OptimizerSettingsDialog,
)
from components.base import InstrumentContext, component_for
from components.hdf5_export import save_workflow_result_hdf5
from components.odmr_control import (
    OdmrFitControlWidget,
    OdmrSweepControlWidget,
    evaluate_dip,
    fit_dip,
)
from components.schema_utils import fetch_schema, pick_1d_series, primary_key
from components.widgets import StatusLabel, dock
from components.workflow_controls import controls_for
from components.workflow_result import (
    Image2DResultView,
    NDScanResultView,
    OdmrResultView,
    OdmrResultViewAdapter,
    _OptimizerCurvePanel,
    _ScanImagePanel,
)
from main import DashboardInstrument, LabPilotStyle

from labpilot.core.run.plans import decompose
from labpilot.core.workflow.instrument_roles import (
    read_required_instruments,
    read_result_ui,
)
from labpilot.core.workflow.scan_params import resolve_scan_axes

__all__ = ["WorkflowWindow"]


def _scan_session_get_roles(tree: ast.Module) -> list[str]:
    """Role/instrument-id strings passed to `session.get(...)` calls in
    this script, in first-seen order.

    Every template in core/workflow_templates/ writes this as
    `SCANNER_ID = "xy_actuator"` ... `session.get(SCANNER_ID)` — a literal
    string one level of indirection away through a module-level constant,
    not `session.get("xy_actuator")` directly — so a plain "is this arg a
    string literal" check never matches anything real. This resolves that
    one level of indirection (a simple `NAME = "literal"` assignment) in
    addition to a literal passed directly."""
    constants: dict[str, str] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            constants[stmt.targets[0].id] = stmt.value.value

    found: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "session"
            and node.args
        ):
            continue
        arg = node.args[0]
        role: Optional[str] = None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            role = arg.value
        elif isinstance(arg, ast.Name) and arg.id in constants:
            role = constants[arg.id]
        if role and role not in seen:
            seen.add(role)
            found.append(role)
    return found


def _referenced_instrument_ids(graph: dict[str, Any], script_text: Optional[str]) -> list[str]:
    """Instrument ids this workflow touches, in first-seen order.

    For a role-based template (core/workflow_templates/), the script-scan
    below finds *role* names ("xy_actuator"), not real instrument ids —
    resolved through `graph["metadata"]["instrument_bindings"]` (see
    core/workflow/instrument_roles.py) before being returned. An unbound
    role has no entry to resolve to and is silently dropped here; the
    caller reports which roles are still unbound separately (see
    WorkflowWindow.__init__)."""
    ids: list[str] = []
    seen: set[str] = set()

    def _add(name: Optional[str]) -> None:
        if name and name not in seen:
            seen.add(name)
            ids.append(name)

    for node in graph.get("nodes", {}).values():
        for ref in node.get("device_refs", []) or []:
            _add(ref)

    if not ids and script_text:
        try:
            tree = ast.parse(script_text)
        except SyntaxError:
            return ids
        for role in _scan_session_get_roles(tree):
            _add(role)

    bindings = graph.get("metadata", {}).get("instrument_bindings")
    if bindings:
        resolved: list[str] = []
        resolved_seen: set[str] = set()
        for name in ids:
            real = bindings.get(name, name)
            if real and real not in resolved_seen:
                resolved_seen.add(real)
                resolved.append(real)
        return resolved
    return ids


def _unbound_roles(graph: dict[str, Any], script_text: Optional[str]) -> list[str]:
    """Role names this script declares (session.get("...") calls) that
    have no entry, or a null entry, in instrument_bindings — used to warn
    that some docks are missing rather than silently showing fewer than
    expected. A role declared `"optional": True` (e.g. omniscan.py's
    "scanner" role — an alternative to its "actuator"/"detector" pair)
    is excluded here even when unbound, since leaving it unbound is
    normal/expected for that role, not a missing-binding problem."""
    bindings = graph.get("metadata", {}).get("instrument_bindings")
    if not bindings or not script_text:
        return []
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return []
    required = read_required_instruments(script_text)
    return [
        role for role in _scan_session_get_roles(tree)
        if role in bindings and not bindings.get(role) and not required.get(role, {}).get("optional")
    ]


def _result_ui(script_text: Optional[str]) -> dict:
    """This template's `RESULT_UI` declaration, or {} if it has none.

    `read_result_ui` itself, not a copy of it. This process re-parsed the
    script text it had already fetched, on the rule that "the desktop app
    talks to the backend only over HTTP, so it never imports a backend
    module" — but the rule is about *state*, not about code: instruments
    and the running session are live objects in another process and can
    only be reached over HTTP, while a function that turns script text
    into a dict is neither. This module already imported
    `core.workflow.result_types` for the hard half of exactly this parse.
    """
    if not script_text:
        return {}
    return read_result_ui(script_text)


class WorkflowWindow(QMainWindow):
    """Combined window for every instrument referenced by `workflow_id`."""

    def __init__(self, workflow_id: str, client: BackendClient, parent=None) -> None:
        super().__init__(parent)
        self.workflow_id = workflow_id
        self.client = client
        # Every instrument write triggered by a live drag (crosshair,
        # axes-control slider, optimizer-fit sync) goes through this
        # instead of self.client.write() directly — see AsyncWriter's own
        # docstring for why a direct call there was the actual cause of
        # "the slider and crosshair... should move synchronously" not
        # working (a blocking HTTP call on the GUI thread, once per
        # ~30ms-debounced drag tick).
        self._writer = AsyncWriter(client.base_url)
        self._writer.errorOccurred.connect(lambda msg: self.status_bar.showMessage(f"Write failed: {msg}"))
        self.instrument_contexts: dict[str, InstrumentContext] = {}
        self.axes_control: Optional[AxesControlWidget] = None
        self._axes_control_actuator_id: Optional[str] = None
        self._axes_control_dock: Optional[QDockWidget] = None
        # This workflow's AXIS_RANGES (see _add_params_dock), if it's an
        # omniscan-family workflow — needed by _add_result_view to build
        # NDScanResultView's panels/docks eagerly (qudi's own scanner GUI
        # builds every scan dock from the hardware's declared axes before
        # any scan has run; see that class's docstring for why this
        # matters), not lazily from the first frame's data.
        self._omniscan_axis_ranges: Optional[dict] = None
        # The optimizer's axes, in the order the server sweeps them.
        self._scan_axes: list[str] = []
        self._omniscan_hold_positions: Optional[dict] = None
        # ODMR sweep/fit docks (see _add_odmr_sweep_control) — only built
        # for a workflow whose params match odmr_sweep.py's shape.
        self.odmr_sweep_control: Optional[OdmrSweepControlWidget] = None
        self.odmr_fit_control: Optional[OdmrFitControlWidget] = None
        self._odmr_sweep_control_dock: Optional[QDockWidget] = None
        self._odmr_fit_control_dock: Optional[QDockWidget] = None
        # Latest data the "odmr" result view is showing — read by the Fit
        # dock's on-demand client-side re-fit (see _add_odmr_sweep_control).
        self._last_odmr_x: Optional[list] = None
        self._last_odmr_y: Optional[list] = None
        # OptimizerDockWidget state (see _add_optimizer_dock/_on_toggle_optimize)
        # — empty for any workflow with no optimizer capability declared
        # (see read_capabilities's RESULT_UI["crosshair"] fallback,
        # core/workflow/instrument_roles.py). One pane per step of the
        # optimize sequence (qudi's own OptimizerDockWidget,
        # UI_FRAMEWORK_DESIGN.md §2.6), keyed by that step's axes tuple —
        # e.g. {("x","y"): <_ScanImagePanel>, ("z",): <_OptimizerCurvePanel>}.
        self._result_dock: Optional[QDockWidget] = None
        self.optimizer_panels: dict[tuple, object] = {}
        self.optimizer_sequence: list[tuple] = []
        self._optimize_poller: Optional[OptimizePoller] = None
        self._optimize_action: Optional[QAction] = None
        self._optimizer_panel_has_data: dict[tuple, bool] = {}
        self._optimizer_result_label: Optional[QLabel] = None
        # Last fit position already pushed to the main crosshair/actuator
        # per step (see _on_optimize_state) — skips redundant re-writes on
        # every ~150ms optimize-poll tick once a step's fit has settled.
        self._optimizer_synced_fit: dict[tuple, tuple] = {}
        # OptimizerSettingsDialog's last commit (see _open_optimizer_settings) —
        # None selected_axes means "every axis in optimizer_sequence" (today's
        # default, unchanged); points defaults per-axis to 5 when absent.
        self._optimizer_selected_axes: Optional[list[str]] = None
        self._optimizer_points: dict[str, int] = {}
        # session_manager.py's get_window_state() reads window.instrument
        # for any registered window (instrument or workflow alike) — None
        # here makes its getattr(..., default) calls fall back cleanly
        # rather than raising AttributeError.
        self.instrument = None

        graph = client.get_workflow(workflow_id)
        script_text = client.get_workflow_script(workflow_id)
        instrument_ids = _referenced_instrument_ids(graph, script_text)
        result_ui = _result_ui(script_text)

        self.setDockNestingEnabled(True)
        central = QWidget()
        central.setFixedSize(1, 1)
        self.setCentralWidget(central)
        central.hide()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.setWindowTitle(f"qudi: {graph.get('name', workflow_id)} (Workflow)")
        self.resize(1400, 900)

        self._build_workflow_toolbar(has_crosshair=bool(result_ui.get("crosshair")))
        self._add_params_dock(graph)

        unbound = _unbound_roles(graph, script_text)
        if not instrument_ids and not unbound:
            self.status_bar.showMessage(
                "This workflow references no known instruments — nothing to show"
            )
        elif unbound:
            self.status_bar.showMessage(
                f"Unbound role(s): {', '.join(unbound)} — bind them via the "
                f"flowchart before running this workflow."
            )

        for instrument_id in instrument_ids:
            self._add_instrument(instrument_id)

        self.result_view = None
        self._result_view_adapter: Optional[type] = None
        # Kept so a template that declares no RESULT_UI can still get a
        # view once its first data arrives — see _ensure_result_view.
        self._graph = graph
        self._declared_result_ui = bool(result_ui)
        if result_ui:
            self._add_result_view(result_ui)
            crosshair = result_ui.get("crosshair")
            if crosshair and self.result_view is not None:
                self._wire_crosshair(graph, crosshair)
                self._add_optimizer_dock(crosshair)
        self._build_menu_bar()

        self._state_poller = WorkflowStatePoller(client.base_url, workflow_id)
        self._state_poller.stateReady.connect(self._on_execution_state)
        self._state_poller.errorOccurred.connect(
            lambda msg: self.status_bar.showMessage(f"Status poll failed: {msg}")
        )
        self._state_poller.start()

    # ---- workflow-level toolbar (Execute/Stop/status) ----

    def _build_workflow_toolbar(self, has_crosshair: bool = False) -> None:
        toolbar = QToolBar("Workflow", self)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        execute_action = QAction(LabPilotStyle.icon("media-playback-start"), "Execute", self)
        execute_action.setToolTip("Run this workflow now.")
        execute_action.triggered.connect(self._on_execute)
        toolbar.addAction(execute_action)
        self._execute_action = execute_action

        stop_action = QAction(LabPilotStyle.icon("media-playback-stop"), "Stop", self)
        stop_action.setToolTip("Stop this workflow if it's running.")
        stop_action.triggered.connect(self._on_stop)
        stop_action.setEnabled(False)
        toolbar.addAction(stop_action)
        self._stop_action = stop_action

        # Replaces the per-panel Save buttons _ScanImagePanel used to have
        # (one qudi-style button duplicated on every axis-pair panel) —
        # one toolbar action exports every scan panel's image at once
        # (see _on_save_all). Only meaningful once a scan panel exists.
        save_action = QAction(LabPilotStyle.icon("document-save"), "Save", self)
        save_action.setToolTip("Save every scan panel's image as PNG.")
        save_action.triggered.connect(self._on_save_all)
        toolbar.addAction(save_action)

        # Only meaningful when RESULT_UI declares a crosshair (qudi's own
        # scanning_optimize_logic.py/OptimizerDockWidget pattern: a quick
        # re-scan-and-recenter around the current position, on demand) —
        # hidden entirely otherwise rather than shown disabled, since most
        # workflows have no meaningful "position" to optimize around at
        # all. Checkable, like qudi's own action_optimize_position — it
        # mirrors (and drives, same as the OptimizerDockWidget's own
        # button — see _add_optimizer_dock/_on_toggle_optimize) whether an
        # optimize run is currently in progress, not a one-shot button.
        self._optimize_action = None
        if has_crosshair:
            toolbar.addSeparator()
            optimize_action = QAction(LabPilotStyle.icon("zoom-fit-best"), "Optimize", self)
            optimize_action.setCheckable(True)
            optimize_action.setToolTip("Start/stop optimizing on the local maximum around the current position.")
            optimize_action.toggled.connect(self._on_toggle_optimize)
            toolbar.addAction(optimize_action)
            self._optimize_action = optimize_action

        toolbar.addSeparator()
        self.status_label = StatusLabel("Idle", LabPilotStyle.TEXT_MUTED, center=False)
        toolbar.addWidget(self.status_label)

    def _on_execute(self) -> None:
        try:
            self.client.execute_workflow(self.workflow_id)
            self.status_bar.showMessage("Workflow execution started")
        except Exception as e:
            self.status_bar.showMessage(f"Execute failed: {e}")

    def _on_stop(self) -> None:
        try:
            self.client.stop_workflow(self.workflow_id)
            self.status_bar.showMessage("Workflow stop requested")
        except Exception as e:
            self.status_bar.showMessage(f"Stop failed: {e}")

    # ---- optimizer dock (qudi's scanning_optimize_logic.py/OptimizerDockWidget) ----

    def _add_optimizer_dock(self, crosshair: dict) -> None:
        """A small, always-visible dock showing a live-updating re-scan
        sequence around the actuator's current position, one pane per
        step (any number of axes — see `_build_optimizer_panel`), each
        with its own (display-only — see `add_crosshair(on_move=None)`)
        marker on the fit-found center, refined as the background
        optimize task (see server.py's /optimize/start,
        core/run/plans.py's `OptimizePlan`) reports
        more of each step — qudi's real `OptimizerDockWidget`, not the
        single blocking call this used to be, and not limited to its
        fixed 2-axis/0D-detector shape either. Reuses `_ScanImagePanel`/
        `_OptimizerCurvePanel` (the same qudi-style panes every scan panel
        already is) rather than building parallel widgets from scratch.

        Placed at the BOTTOM of the LEFT dock area, directly below the
        scan-panel tab group — "keeping the optimizer on the bottom
        left". For an NDScanResultView, that placement already happened
        inside `_add_result_view` (see `_build_optimizer_panel` and
        `NDScanResultView`'s `extra_dock_below`) — splitting against one
        of its panels here, after they're all already tabbed together,
        would just tab this dock in with them instead of splitting it
        below (empirically, Qt only splits cleanly against an untabbed
        dock — splitting against a dock that's already part of a 3-way
        tab group tabs the new one in too). For an Image2DResultView's
        single, untabbed "Result" dock this restriction doesn't apply, so
        it's built and split right here."""
        if isinstance(self.result_view, NDScanResultView):
            return
        d = self._build_optimizer_panel(crosshair)
        if self._result_dock is not None:
            self.splitDockWidget(self._result_dock, d, Qt.Orientation.Vertical)
        else:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, d)

    def _resolve_optimizer_axes(self, crosshair: dict) -> list[str]:
        """Which actuator axes the optimizer runs over.

        Resolved by `core/workflow/scan_params.py`'s `resolve_scan_axes` —
        the same call the server makes — when this workflow declares a
        grid (see `_add_params_dock`); a workflow that declares none
        (a template declaring a fixed X_POSITIONS/Y_POSITIONS pair rather
        than a grid) falls back to the crosshair's own x_axis/y_axis pair.

        This used to be a hand-kept copy of the server's rule, on the
        grounds that the two "need to agree" and could not share code
        across the process boundary. They are separate processes but one
        installed package, and the rule is a pure function of the
        parameters — so they now agree by construction instead of by
        assertion.
        """
        if self._scan_axes:
            return list(self._scan_axes)
        return [crosshair.get("x_axis", "x"), crosshair.get("y_axis", "y")]

    def _build_optimizer_panel(self, crosshair: dict) -> QDockWidget:
        """Builds `self.optimizer_panels` (one per step of the optimize
        sequence, qudi's own `OptimizerDockWidget`'s row-of-panes layout —
        `UI_FRAMEWORK_DESIGN.md` §2.6) + a single QDockWidget containing
        all of them, without placing that dock — split out from
        `_add_optimizer_dock` so an NDScanResultView can request this dock
        BEFORE its own panels exist, letting it split against its first
        panel while that panel is still untabbed (see `_add_result_view`'s
        ndscan branch).

        A 2-axis step gets a `_ScanImagePanel` with no crosshair of its
        own at all — qudi's optimizer dock only ever overlays a marker on
        its OWN separate fine-scan plot (optimizer_dockwidget.py's
        `set_2d_position`), never a second one on the same plot as the
        live scanner target; this pane showed one anyway (a magenta,
        boxless marker at the fit center) and it could visibly disagree
        with the main panel's green crosshair — confusing, and not what
        qudi does. `_on_optimize_state` still moves the REAL target (and
        so the one green crosshair) to the fit center via
        `_sync_optimized_position`; this pane just shows the image. A
        leftover single-axis step (an odd axis count, e.g. qudi's own
        3-axis confocal case) gets a `_OptimizerCurvePanel` instead."""
        axes = self._resolve_optimizer_axes(crosshair)
        self.optimizer_sequence = decompose(axes)
        # Only called once _result_ui_spec is set (_add_result_view's
        # first line) — for both the early (ndscan) and late (image2d)
        # call sites.
        value_label = self._result_ui_spec.get("value_label", "Value")

        container = QWidget()
        grid = QGridLayout(container)
        self.optimizer_panels = {}
        self._optimizer_panel_has_data = {}
        for col, step_axes in enumerate(self.optimizer_sequence):
            if len(step_axes) == 2:
                panel = _ScanImagePanel(
                    x_label=step_axes[0], y_label=step_axes[1], channel_label=value_label,
                )
            else:
                panel = _OptimizerCurvePanel(axis_label=step_axes[0])
            grid.addWidget(panel, 0, col)
            self.optimizer_panels[step_axes] = panel

        self._optimizer_result_label = QLabel("")
        grid.addWidget(self._optimizer_result_label, 1, 0, 1, max(len(self.optimizer_sequence), 1))

        d = dock("Optimizer", self)
        d.setWidget(container)
        return d

    def _on_toggle_optimize(self, checked: bool) -> None:
        """Handler for the toolbar's checkable Optimize action — starts/
        stops a background task (an N-step sequence, one step per pane —
        see `_build_optimizer_panel`); _on_optimize_state keeps the
        toolbar action's checked-state in sync with what's actually
        running, including when it finishes on its own."""
        if checked:
            self._optimizer_panel_has_data = {}
            self._optimizer_synced_fit = {}
            # Every 2-axis step's search range comes from the MAIN scan
            # panel's own crosshair box for that same axis pair (see
            # class docstring's _build_optimizer_panel note — the
            # Optimizer dock's own panes are boxless; there's exactly one
            # resizable box per axis pair, on the panel the user is
            # actually looking at and dragging, not a separate hidden one
            # here). A step with no corresponding main panel (shouldn't
            # normally happen for an omniscan-style workflow, since every
            # 2-axis step comes from the same actuator axes the main scan
            # panels are already built from) falls back to the server's
            # own AXIS_RANGES-fraction default. A leftover single-axis
            # step has no box concept at all (a plain range around the
            # current position) and always uses that same server default.
            # Known limitation, not solved here: if OptimizerSettingsDialog
            # excludes an axis in a way that changes how the REMAINING
            # ones pair up (e.g. keeping x/z but dropping y, out of an
            # original x/y/z sequence), the server recomputes a genuinely
            # different step decomposition than the one these panes were
            # originally built from (`optimizer_sequence`/`optimizer_panels`
            # are fixed at dock-build time) — that step's pane silently
            # doesn't update (`_on_optimize_state`'s panel lookup just
            # finds nothing) rather than showing wrong data. Dropping only
            # trailing axes (e.g. x/y/z -> x/y) stays correctly aligned.
            ranges_override: dict[str, float] = {}
            if isinstance(self.result_view, NDScanResultView):
                for step_axes in self.optimizer_sequence:
                    if len(step_axes) != 2:
                        continue
                    main_panel = self.result_view.panels.get(step_axes)
                    if main_panel is None:
                        continue
                    size = main_panel.crosshair_box_size()
                    if size is not None:
                        ranges_override[step_axes[0]] = size[0]
                        ranges_override[step_axes[1]] = size[1]
            try:
                self.client.start_optimize(
                    self.workflow_id,
                    axes=self._optimizer_selected_axes,
                    ranges=ranges_override,
                    points_per_axis=dict(self._optimizer_points) if self._optimizer_points else None,
                )
            except Exception as e:
                self.status_bar.showMessage(f"Failed to start optimize: {e}")
                self._sync_optimize_toggles(False)
                return
            self.status_bar.showMessage("Optimizing…")
            if self._optimize_poller is None:
                self._optimize_poller = OptimizePoller(self.client.base_url, self.workflow_id)
                self._optimize_poller.stateReady.connect(self._on_optimize_state)
                self._optimize_poller.errorOccurred.connect(
                    lambda msg: self.status_bar.showMessage(f"Optimize poll failed: {msg}")
                )
                self._optimize_poller.start()
        else:
            try:
                self.client.stop_optimize(self.workflow_id)
                self.status_bar.showMessage("Optimize stopped")
            except Exception as e:
                self.status_bar.showMessage(f"Failed to stop optimize: {e}")

    def _sync_optimize_toggles(self, running: bool) -> None:
        if self._optimize_action is not None:
            self._optimize_action.blockSignals(True)
            self._optimize_action.setChecked(running)
            self._optimize_action.blockSignals(False)

    def _on_optimize_state(self, state: dict) -> None:
        """`state["progress"]`/`["last_result"]` are `{"sequence": [...],
        "steps": {step_index: {...}}}` (server.py's `_run_optimize`) — one
        entry per sequence step, each routed to that step's own pane by
        its `step_axes` (a 2-axis step's `_ScanImagePanel`, a 1-axis
        step's `_OptimizerCurvePanel` — see `_build_optimizer_panel`)."""
        running = bool(state.get("running"))
        self._sync_optimize_toggles(running)

        if state.get("error"):
            self.status_bar.showMessage(f"Optimize failed: {state['error']}")

        source = state.get("progress") if running else state.get("last_result")
        steps = (source or {}).get("steps") or {}
        best_parts: list[str] = []
        for step_data in steps.values():
            step_axes = tuple(step_data.get("step_axes") or ())
            panel = self.optimizer_panels.get(step_axes)
            if panel is None:
                continue
            positions = step_data.get("positions")
            values = step_data.get("values")
            fit = step_data.get("fit")

            if len(step_axes) == 2 and isinstance(panel, _ScanImagePanel):
                if values and positions:
                    x_positions, y_positions = positions
                    array = np.array(
                        [np.nan if v is None else float(v) for v in values], dtype=float
                    ).reshape(len(x_positions), len(y_positions))
                    first = not self._optimizer_panel_has_data.get(step_axes, False)
                    self._optimizer_panel_has_data[step_axes] = True
                    panel.set_image(array, first_frame=first)
                    panel.set_extent(x_positions, y_positions)
                if fit is not None:
                    best_parts.append(f"{step_axes[0]}={fit['center_x']:.4g}, {step_axes[1]}={fit['center_y']:.4g}")
                    self._sync_optimized_position(
                        step_axes, {step_axes[0]: fit["center_x"], step_axes[1]: fit["center_y"]}
                    )
            elif isinstance(panel, _OptimizerCurvePanel):
                if values and positions:
                    clean_values = [np.nan if v is None else float(v) for v in values]
                    panel.set_data(positions[0], clean_values)
                if fit is not None:
                    panel.set_fit_center(fit["center"])
                    best_parts.append(f"{step_axes[0]}={fit['center']:.4g}")
                    self._sync_optimized_position(step_axes, {step_axes[0]: fit["center"]})

        if best_parts and self._optimizer_result_label is not None:
            self._optimizer_result_label.setText(" | ".join(best_parts))

        if not running and self._optimize_poller is not None:
            # Finished (or was stopped) — no need to keep polling a
            # settled result.
            self._optimize_poller.stop()
            self._optimize_poller = None

    def _sync_optimized_position(self, step_axes: tuple, target: dict[str, float]) -> None:
        """Once a step's fit is available, moves the main crosshair (and
        the real actuator) to match it — the one green crosshair on the
        main scan panel is the only place a fit result gets shown as a
        position now (see _build_optimizer_panel: the optimizer dock's
        own panes used to duplicate this with a second, magenta marker
        that could visibly disagree with this one — removed). Idempotent
        per exact fit value (see _optimizer_synced_fit) so this doesn't
        re-write the same target on every ~150ms optimize-poll tick once
        a step has settled — only when the fit actually changes."""
        key = tuple(round(v, 9) for v in target.values())
        if self._optimizer_synced_fit.get(step_axes) == key:
            return
        self._optimizer_synced_fit[step_axes] = key
        if self.result_view is not None:
            self.result_view.set_position(target)
        if self.axes_control is not None:
            for axis, value in target.items():
                self.axes_control.set_target(axis, value)
        if self._axes_control_actuator_id:
            self._writer.write(self._axes_control_actuator_id, target)

    # ---- menu bar (File/View, matching qudi's ConfocalMainWindow) ----

    def _build_menu_bar(self) -> None:
        """File/View/Settings menus matching qudi's own menu bar (read
        from `gui/scanning/ui_scannergui.ui`). Execute/Stop stays a
        toolbar action here rather than moving entirely onto each scan
        panel's own Toggle Scan button the way qudi does it: not every
        LabPilot workflow has a scan-type RESULT_UI at all (qudi's whole
        GUI IS the scanner; this framework runs arbitrary workflows), so
        a general "run this workflow" action has to exist regardless of
        whether any scan panel exists. Called last, after every dock
        already exists, so the View menu lists all of them.

        The Settings menu doesn't mirror qudi's own two dialogs (Scanner
        Settings/Optimizer Settings) — nothing here corresponds to them —
        but follows the same pattern qudi uses: something that affects
        display but doesn't need to be permanently visible belongs behind
        a menu action, not a permanent sidebar widget (a
        `pg.HistogramLUTWidget` colorbar was tried directly on each scan
        panel in an earlier pass and dropped for exactly this reason)."""
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        save_all_action = QAction("Save All Scans (Images)", self)
        save_all_action.setToolTip("Export each scan panel's current view as a PNG image.")
        save_all_action.triggered.connect(self._on_save_all)
        file_menu.addAction(save_all_action)
        if self.result_view is not None:
            save_data_action = QAction("Save Data (HDF5)…", self)
            save_data_action.setToolTip(
                "Save this workflow's last completed result as real data (.h5), not a picture of it."
            )
            save_data_action.triggered.connect(self._on_save_data_hdf5)
            file_menu.addAction(save_data_action)
        file_menu.addSeparator()
        close_action = QAction("Close Window", self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        view_menu = menu_bar.addMenu("&View")
        for d in self.findChildren(QDockWidget):
            action = QAction(d.windowTitle(), self)
            action.setCheckable(True)
            action.setChecked(d.isVisible())
            action.toggled.connect(d.setVisible)
            # Tabbed docks: switching tabs makes Qt fire visibilityChanged
            # (True/False) on the newly-front/backgrounded dock as part of
            # the tab switch itself, not a real show/hide. Without
            # blockSignals here, syncing that into action.setChecked(False)
            # would re-emit toggled(False) -> d.setVisible(False) on the
            # dock Qt just tab-switched away from, which actually removes
            # it from the tab group instead of just backgrounding it — the
            # dock "disappearing" on a click was this feedback loop, not a
            # real close.
            def _sync_checked(visible: bool, action: QAction = action) -> None:
                action.blockSignals(True)
                action.setChecked(visible)
                action.blockSignals(False)
            d.visibilityChanged.connect(_sync_checked)
            view_menu.addAction(action)
        view_menu.addSeparator()
        restore_action = QAction("Restore Default View", self)
        restore_action.triggered.connect(self._on_restore_default_view)
        view_menu.addAction(restore_action)

        settings_menu = menu_bar.addMenu("&Settings")
        auto_level_action = QAction("Auto-Level Scan Images", self)
        auto_level_action.setCheckable(True)
        auto_level_action.setChecked(True)
        auto_level_action.setToolTip(
            "Rescale each scan panel's colors to its own data every frame. "
            "Uncheck to freeze levels at whatever they currently are."
        )
        auto_level_action.toggled.connect(self._on_auto_level_toggled)
        settings_menu.addAction(auto_level_action)

        # Only meaningful for an omniscan-family workflow (one with an
        # Axes Control dock at all) — qudi's own "Scanner Settings" menu
        # entry, generalized to this engine's actual infrequently-edited
        # settings (range/resolution) instead of pixel scan frequency.
        if self.axes_control is not None:
            settings_menu.addSeparator()
            axis_range_action = QAction("Axis Range Settings…", self)
            axis_range_action.triggered.connect(self._open_axis_range_settings)
            settings_menu.addAction(axis_range_action)

        # Only meaningful for a workflow with an optimizer capability at
        # all (see optimizer_sequence, built once _build_optimizer_panel
        # runs) — "a window that you can open where you can select the
        # range and the axis you want to optimize".
        if self.optimizer_sequence:
            optimizer_settings_action = QAction("Optimizer Settings…", self)
            optimizer_settings_action.triggered.connect(self._open_optimizer_settings)
            settings_menu.addAction(optimizer_settings_action)

    def _on_auto_level_toggled(self, checked: bool) -> None:
        if self.result_view is not None:
            self.result_view.set_auto_level(checked)

    def _on_save_data_hdf5(self) -> None:
        """Saves this workflow's last completed result as a real .h5 file
        (see components/hdf5_export.py) — re-fetches execution_state
        fresh rather than relying on whatever the live poller last saw,
        so this reflects the true last-completed run even if triggered
        right after a run finishes."""
        try:
            state = self.client.get_workflow_execution_state(self.workflow_id)
        except Exception as e:
            self.status_bar.showMessage(f"Could not load workflow state: {e}")
            return
        results = state.get("last_results")
        if not results:
            self.status_bar.showMessage("No completed result to save yet")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save workflow data", "", "HDF5 (*.h5)")
        if not path:
            return

        try:
            graph = self.client.get_workflow(self.workflow_id)
            workflow_name = graph.get("name", self.workflow_id)
            instrument_bindings = graph.get("metadata", {}).get("instrument_bindings", {})
            save_workflow_result_hdf5(
                path, self.workflow_id, workflow_name, self._result_ui_spec, results, instrument_bindings
            )
            self.status_bar.showMessage(f"Saved data to {path}")
        except Exception as e:
            self.status_bar.showMessage(f"Failed to save data: {e}")

    def _all_scan_panels(self) -> list[tuple[str, Any]]:
        if isinstance(self.result_view, Image2DResultView):
            return [("scan", self.result_view.panel)]
        if isinstance(self.result_view, NDScanResultView):
            return [(f"{i}-{j}", panel) for (i, j), panel in self.result_view.panels.items()]
        return []

    def _on_save_all(self) -> None:
        panels = self._all_scan_panels()
        if not panels:
            self.status_bar.showMessage("No scan panels to save")
            return
        directory = QFileDialog.getExistingDirectory(self, "Save all scan images to…")
        if not directory:
            return
        from pathlib import Path
        saved = 0
        for name, panel in panels:
            try:
                panel.save_image_as_png(str(Path(directory) / f"{name}.png"))
                saved += 1
            except Exception as e:
                self.status_bar.showMessage(f"Failed to save {name}: {e}")
                return
        self.status_bar.showMessage(f"Saved {saved} scan image(s) to {directory}")

    def _on_restore_default_view(self) -> None:
        """Simplified relative to qudi's own restore_default_view (which
        re-derives exact split ratios/tab groupings from scratch) — just
        un-floats and re-shows every dock, since our dock set is dynamic
        (built from this workflow's own params/result type) rather than a
        fixed layout this window could fully recompute from config."""
        for d in self.findChildren(QDockWidget):
            d.setFloating(False)
            d.setVisible(True)

    # ---- workflow-level settings (genuinely specific to THIS workflow) ----

    def _add_params_dock(self, graph: dict) -> None:
        """This workflow's own tunable parameters — top-level UPPERCASE
        constants its own script declares (e.g. omniscan.py's
        AXIS_RANGES/SCAN_AXES/SETTLE_TOLERANCE), read via
        core/workflow/instrument_roles.py's read_workflow_params. A
        parallel surface to SettingsTreeComponent's per-instrument
        DeviceSchema-driven tree (InstrumentWindow), but this one edits
        the *workflow script's own* constants, not any instrument's
        settings — genuinely specific to this workflow, not a generic
        per-instrument-kind form. A no-op if this workflow declares none.

        An omniscan-family workflow's AXIS_RANGES/SCAN_AXES/HOLD_POSITIONS
        (see core/workflow_templates/omniscan.py) get a dedicated
        qudi-scanner-style axes-control table instead (see
        _add_axes_control) — editing a per-axis range/resolution as one
        raw Python-literal string in a generic tree was exactly the
        "basic, not handy" UI this replaces. Anything else a workflow
        declares (e.g. SETTLE_TOLERANCE) has no dock of its own now —
        removed on request; not surfaced anywhere else at the moment.
        """
        try:
            params = self.client.get_workflow_params(self.workflow_id)
        except Exception as e:
            self.status_bar.showMessage(f"Could not load workflow parameters: {e}")
            return
        if not params:
            return

        for control in controls_for(params, load_workflow_blocks()):
            control.build(self, graph, dict(params))

    def build_axes_control(self, graph: dict, params: dict) -> None:
        """The per-axis range/resolution table, for an omniscan-family
        workflow. Selected by `workflow_blocks.toml`'s `axes_control`
        block; see components/workflow_controls.py."""
        axis_ranges = params.get("AXIS_RANGES")
        scan_axes = params.get("SCAN_AXES")
        if not isinstance(axis_ranges, dict) or not isinstance(scan_axes, list):
            self.status_bar.showMessage(
                "This workflow declares AXIS_RANGES/SCAN_AXES in a shape the "
                "axes table cannot read"
            )
            return
        hold_positions = params.get("HOLD_POSITIONS", {})
        if not isinstance(hold_positions, dict):
            hold_positions = {}

        # AXIS_RANGES is authored generically in the script (e.g. x/y/z)
        # but the actuator actually bound to the "actuator" role may only
        # have some of those axes (e.g. mock_xy_stage_3 has no z) — show
        # only rows the bound instrument can actually move, not every
        # axis the template happens to declare.
        actuator_id = graph.get("metadata", {}).get("instrument_bindings", {}).get("actuator")
        actuator_schema: dict = {}
        if actuator_id:
            actuator_schema = fetch_schema(self.client, actuator_id)
            available = set(actuator_schema.get("settable", {}).keys())
            axis_ranges = {k: v for k, v in axis_ranges.items() if k in available}
            scan_axes = [a for a in scan_axes if a in available]
            hold_positions = {k: v for k, v in hold_positions.items() if k in available}

        if not axis_ranges:
            return
        self._omniscan_axis_ranges = axis_ranges
        self._omniscan_hold_positions = hold_positions
        # The optimizer's axes come from the shared rule, not from this
        # table's row order: `axis_ranges` is a dict keyed however the
        # template happened to author it, while the server sweeps in
        # SCAN_AXES order. Reading the panes' axis list off the dict meant
        # the two could pair axes differently and a step's results could
        # land in the wrong pane. See core/workflow/scan_params.py.
        self._scan_axes = resolve_scan_axes(
            {"AXIS_RANGES": axis_ranges, "SCAN_AXES": scan_axes}, actuator_schema
        )[0]
        self._add_axes_control(
            actuator_id, axis_ranges, scan_axes, hold_positions, actuator_schema
        )

    def build_sweep_control(self, graph: dict, params: dict) -> None:
        """The Sweep Control and Fit docks, for an odmr_sweep-family
        workflow. Selected by `workflow_blocks.toml`'s `sweep_control`
        block; see components/workflow_controls.py."""
        self._add_odmr_sweep_control(graph, params)

    def _add_odmr_sweep_control(self, graph: dict, params: dict) -> None:
        """odmr_sweep.py-family workflow: a Sweep Control dock (range/
        power/averages + a CW park mini-section) and a Fit dock — qudi's
        `OdmrScanControlDockWidget`/`OdmrCwControlDockWidget`/
        `OdmrFitDockWidget`, see components/odmr_control.py. Dumb-view
        widgets; every signal is wired here to the actual PUT/write/
        action call, same separation `_add_axes_control` already uses."""
        source_id = graph.get("metadata", {}).get("instrument_bindings", {}).get("source")

        def _set_param(name: str, value) -> None:
            try:
                self.client.set_workflow_param(self.workflow_id, name, value)
                self.status_bar.showMessage(f"{name} set to {value}")
            except Exception as e:
                self.status_bar.showMessage(f"Failed to update {name}: {e}")

        sweep = OdmrSweepControlWidget(
            params.get("SWEEP_START", 2.82e9), params.get("SWEEP_STOP", 2.86e9),
            params.get("SWEEP_POINTS", 21), params.get("SWEEP_POWER", -10.0),
            params.get("AVERAGES", 5), has_cw=bool(source_id),
        )
        sweep.sigStartChanged.connect(lambda v: _set_param("SWEEP_START", v))
        sweep.sigStopChanged.connect(lambda v: _set_param("SWEEP_STOP", v))
        sweep.sigPointsChanged.connect(lambda v: _set_param("SWEEP_POINTS", v))
        sweep.sigPowerChanged.connect(lambda v: _set_param("SWEEP_POWER", v))
        sweep.sigAveragesChanged.connect(lambda v: _set_param("AVERAGES", v))

        def _cw_write(values: dict) -> None:
            if not source_id:
                return
            self._writer.write(source_id, values)

        def _cw_action(name: str) -> None:
            if not source_id:
                return
            try:
                self.client.call_action(source_id, name)
                self.status_bar.showMessage(f"MW source: {name}")
            except Exception as e:
                self.status_bar.showMessage(f"CW {name} failed: {e}")

        if source_id:
            source_schema = fetch_schema(self.client, source_id)
            settable = source_schema.get("settable", {})
            cw_freq_key = next((k for k, dt in settable.items() if dt != "bool" and "power" not in k.lower()), None)
            cw_power_key = next((k for k, dt in settable.items() if "power" in k.lower()), None)
            sweep.sigCwFrequencyChanged.connect(
                lambda v: _cw_write({cw_freq_key: v}) if cw_freq_key else None
            )
            sweep.sigCwPowerChanged.connect(
                lambda v: _cw_write({cw_power_key: v}) if cw_power_key else None
            )
            sweep.sigCwOnRequested.connect(lambda: _cw_action("cw_on"))
            sweep.sigCwOffRequested.connect(lambda: _cw_action("off"))

        self.odmr_sweep_control = sweep
        d = dock("Sweep Control", self)
        d.setWidget(sweep)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, d)
        self._odmr_sweep_control_dock = d

        fit_widget = OdmrFitControlWidget(params.get("FIT_SHAPE", "lorentzian"))
        fit_widget.sigShapeChanged.connect(lambda shape: _set_param("FIT_SHAPE", shape))

        def _on_fit_requested(shape: str) -> None:
            if not self._last_odmr_x or not self._last_odmr_y:
                fit_widget.set_result_text("No data to fit yet")
                return
            result = fit_dip(self._last_odmr_x, self._last_odmr_y, shape)
            if result is None:
                fit_widget.set_result_text("Fit did not converge")
                if isinstance(self.result_view, OdmrResultView):
                    self.result_view.clear_fit()
                return
            fit_widget.set_result_text(
                f"Center: {result['center']:.6g}\n"
                f"Amplitude: {result['amplitude']:.6g}\n"
                f"FWHM: {result['fwhm']:.6g}\n"
                f"Baseline: {result['baseline']:.6g}"
            )
            if isinstance(self.result_view, OdmrResultView):
                curve_x = np.linspace(min(self._last_odmr_x), max(self._last_odmr_x), 200).tolist()
                curve_y = evaluate_dip(result, curve_x, shape)
                self.result_view.set_fit(curve_x, curve_y, result["center"])

        fit_widget.sigFitRequested.connect(_on_fit_requested)

        self.odmr_fit_control = fit_widget
        fit_dock = dock("Fit", self)
        fit_dock.setWidget(fit_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, fit_dock)
        self._odmr_fit_control_dock = fit_dock

    def _add_axes_control(
        self, actuator_id: Optional[str], axis_ranges: dict, scan_axes: list,
        hold_positions: dict, schema: dict,
    ) -> None:
        """Slim, always-visible "Axes Control" dock (see
        components/axes_control.py's `AxesControlWidget`) — one row per
        axis, target on the left of the slider and Min/Max/Points on the
        right (per explicit request: "the current target position
        should be on the left side of the sliders... the scanning range
        min/max + number of points should be on the right side"),
        committing straight to AXIS_RANGES (see `_on_range_changed`/
        `_on_points_changed` below). Which-axes-scan still only lives in
        the on-demand `AxisRangeSettingsDialog` (Settings menu → "Axis
        Range Settings…", see `_open_axis_range_settings`) — that
        dialog's Min/Max/Points duplicate what's editable here, just also
        reachable when setting up cold rather than eyeballing a live view.

        The target slider writes a live actuator move, debounced the
        same way the map crosshair's drag is. Locked while the workflow
        is running (see _on_execution_state). Shows the *target*
        (commanded) position, not a live actuator read-back — there is
        no live-position polling wired into this widget (see
        components/workflow_result.py's NDScanResultView docstring for
        the same design applied to the crosshair)."""
        units = schema.get("units", {}) if actuator_id else {}

        def _on_move(axis: str, value: float) -> None:
            if not actuator_id:
                return
            # Bidirectional link with the scan panels' own crosshair (the
            # opposite direction of NDScanResultView's own
            # on_position_changed callback below) — both display the same
            # commanded target, so dragging this slider should move the
            # crosshair too, not just write hardware. Done BEFORE the
            # write (which is fire-and-forget via AsyncWriter, not
            # awaited) so the crosshair updates instantly regardless of
            # how long the write takes — see AsyncWriter's docstring.
            if isinstance(self.result_view, NDScanResultView):
                self.result_view.set_position({axis: value})
            self._writer.write(actuator_id, {axis: value})

        def _on_hold_changed(new_hold_positions: dict) -> None:
            self._omniscan_hold_positions = new_hold_positions
            try:
                self.client.set_workflow_param(self.workflow_id, "HOLD_POSITIONS", new_hold_positions)
            except Exception as e:
                self.status_bar.showMessage(f"Failed to update hold position: {e}")

        def _on_range_changed(axis: str, lo: float, hi: float) -> None:
            ranges = dict(self._omniscan_axis_ranges or {})
            _lo0, _hi0, n = ranges.get(axis, (lo, hi, 100))
            ranges[axis] = (lo, hi, n)
            try:
                self.client.set_workflow_param(self.workflow_id, "AXIS_RANGES", ranges)
                self._omniscan_axis_ranges = ranges
                self.status_bar.showMessage(f"{axis} range set to ({lo:.4g}, {hi:.4g})")
            except Exception as e:
                self.status_bar.showMessage(f"Failed to update {axis} range: {e}")

        def _on_points_changed(axis: str, n: int) -> None:
            ranges = dict(self._omniscan_axis_ranges or {})
            lo, hi, _n0 = ranges.get(axis, (0.0, 1.0, n))
            ranges[axis] = (lo, hi, n)
            try:
                self.client.set_workflow_param(self.workflow_id, "AXIS_RANGES", ranges)
                self._omniscan_axis_ranges = ranges
                self.status_bar.showMessage(f"{axis} resolution set to {n} points")
            except Exception as e:
                self.status_bar.showMessage(f"Failed to update {axis} resolution: {e}")

        self.axes_control = AxesControlWidget(
            axis_ranges, scan_axes, hold_positions, units, _on_move, _on_hold_changed,
            _on_range_changed, _on_points_changed,
        )
        self._axes_control_actuator_id = actuator_id

        d = dock("Axes Control", self)
        d.setWidget(self.axes_control)
        d.setMaximumHeight(min(200, 40 + 34 * len(axis_ranges)))
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, d)
        self._axes_control_dock = d

    def _open_axis_range_settings(self) -> None:
        """Opens AxisRangeSettingsDialog (Settings menu), fresh each time
        — re-fetches this workflow's current AXIS_RANGES/SCAN_AXES/
        HOLD_POSITIONS rather than reusing whatever _add_params_dock saw
        at window-construction time, so it reflects the latest state even
        if changed elsewhere (the flowchart, another window) since. A
        no-op if this workflow isn't an omniscan-family one (no
        AXIS_RANGES/SCAN_AXES to configure) or has no bound actuator."""
        try:
            params = self.client.get_workflow_params(self.workflow_id)
        except Exception as e:
            self.status_bar.showMessage(f"Could not load workflow parameters: {e}")
            return
        axis_ranges = params.get("AXIS_RANGES")
        scan_axes = params.get("SCAN_AXES")
        if not isinstance(axis_ranges, dict) or not isinstance(scan_axes, list):
            self.status_bar.showMessage("This workflow has no AXIS_RANGES/SCAN_AXES to configure")
            return
        hold_positions = params.get("HOLD_POSITIONS", {})
        if not isinstance(hold_positions, dict):
            hold_positions = {}

        graph = self.client.get_workflow(self.workflow_id)
        actuator_id = graph.get("metadata", {}).get("instrument_bindings", {}).get("actuator")
        units: dict = {}
        hardware_limits: dict = {}
        if actuator_id:
            schema = fetch_schema(self.client, actuator_id)
            available = set(schema.get("settable", {}).keys())
            axis_ranges = {k: v for k, v in axis_ranges.items() if k in available}
            scan_axes = [a for a in scan_axes if a in available]
            hold_positions = {k: v for k, v in hold_positions.items() if k in available}
            units = schema.get("units", {})
            # DeviceSchema.limits already carries the actuator's own real
            # hardware min/max per settable key (e.g. {"x": (-5.0, 5.0)})
            # — previously unused here; backs the dialog's "Full Range"
            # button (see ARCHITECTURE_NOTES.md §4.1).
            hardware_limits = {
                k: tuple(v) for k, v in schema.get("limits", {}).items() if k in available
            }

        if not axis_ranges:
            self.status_bar.showMessage("No axes available to configure on the bound actuator")
            return

        def _on_change(new_scan_axes: list, new_axis_ranges: dict, new_hold_positions: dict) -> None:
            try:
                self.client.set_workflow_param(self.workflow_id, "AXIS_RANGES", new_axis_ranges)
                self.client.set_workflow_param(self.workflow_id, "SCAN_AXES", new_scan_axes)
                self.client.set_workflow_param(self.workflow_id, "HOLD_POSITIONS", new_hold_positions)
                self.status_bar.showMessage(f"Scan axes updated: {', '.join(new_scan_axes) or 'none'}")
            except Exception as e:
                self.status_bar.showMessage(f"Failed to update scan axes: {e}")
                return
            # Keep the caches Axes Control's own row edits read from (see
            # _add_axes_control's _on_range_changed/_on_points_changed)
            # fresh, since this dialog can also change them.
            self._omniscan_axis_ranges = new_axis_ranges
            self._omniscan_hold_positions = new_hold_positions
            if self.axes_control is not None:
                self.axes_control.set_scanning_axes(new_scan_axes)
                for name, (lo, hi, n) in new_axis_ranges.items():
                    self.axes_control.set_range(name, lo, hi)
                    self.axes_control.set_points(name, n)

        dialog = AxisRangeSettingsDialog(
            axis_ranges, scan_axes, hold_positions, units, _on_change,
            parent=self, hardware_limits=hardware_limits,
        )
        dialog.exec()

    def _open_optimizer_settings(self) -> None:
        """Opens OptimizerSettingsDialog (Settings menu) — "a window that
        you can open where you can select the range and the axis you
        want to optimize... whether you want to optimize along one
        dimension or multiple dimensions". Pre-filled from
        `optimizer_sequence`'s full flat axis list, each axis's current
        crosshair-box range (`NDScanResultView.axis_box_full_width` — "of
        course these values are updated... from the green rectangle"),
        and this window's own last-committed selection/points. A no-op
        if this workflow has no optimizer capability (no menu action
        exists at all then, see _build_menu_bar)."""
        axis_names = [axis for step in self.optimizer_sequence for axis in step]
        if not axis_names or self.result_view is None:
            return
        selected_axes = self._optimizer_selected_axes if self._optimizer_selected_axes is not None else axis_names
        ranges = {}
        for name in axis_names:
            width = self.result_view.axis_box_full_width(name)
            if width is not None:
                ranges[name] = width
        units: dict = {}
        if self._axes_control_actuator_id:
            schema = fetch_schema(self.client, self._axes_control_actuator_id)
            units = schema.get("units", {})

        def _on_change(new_selected_axes: list, new_ranges: dict, new_points: dict) -> None:
            self._optimizer_selected_axes = new_selected_axes
            self._optimizer_points = new_points
            for name, width in new_ranges.items():
                self.result_view.set_axis_box_full_width(name, width)
            self.status_bar.showMessage(
                f"Optimizer axes updated: {', '.join(new_selected_axes) or 'none'}"
            )

        dialog = OptimizerSettingsDialog(
            axis_names, selected_axes, ranges, dict(self._optimizer_points), units, _on_change, parent=self,
        )
        dialog.exec()

    # ---- live/last result view ----

    def _add_result_view(self, result_ui: dict) -> None:
        """Builds `self.result_view` from `result_ui["type"]` via
        the registry's "result" context (components/workflow_result.py) — one
        adapter class per type, auto-registered there, replacing what used
        to be a hardcoded if/elif chain here. Adding a 5th result kind
        means adding one adapter subclass in that module, not editing this
        method at all."""
        self._result_ui_spec = result_ui
        adapter_cls = component_for("result", result_ui.get("type") or "")
        if adapter_cls is None:
            return
        view = adapter_cls.build(self, result_ui)
        if view is None:
            return
        self.result_view = view
        self._result_view_adapter = adapter_cls
        if adapter_cls.manages_own_docks:
            # NDScanResultView isn't a single QWidget to embed in one
            # generic dock — it manages its own QDockWidget per axis-pair
            # directly on this window, built eagerly from AXIS_RANGES (see
            # its class docstring), qudi's own one-dock-per-scan-pane
            # structure rather than one shared canvas.
            return
        d = dock("Result", self)
        d.setWidget(self.result_view)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, d)
        self._result_dock = d

    def _on_execution_state(self, state: dict) -> None:
        running = state.get("running")
        last_status = state.get("last_status")
        # The engine already rejects a second /execute for the same
        # workflow_id server-side, but leaving the action clickable anyway
        # invites exactly the repeated-click pattern seen when a run looks
        # stalled (see _resync_live_data's docstring) — each stray click
        # still round-trips a rejected request while the real run continues.
        self._execute_action.setEnabled(not running)
        self._stop_action.setEnabled(bool(running))
        if running:
            self.status_label.set_status("● Running", LabPilotStyle.PRIMARY)
        elif last_status == "completed":
            self.status_label.set_status("✓ Completed", LabPilotStyle.SUCCESS)
        elif last_status in ("failed", "error"):
            self.status_label.set_status("✗ Failed", LabPilotStyle.DANGER)
        elif last_status == "cancelled":
            self.status_label.set_status("Cancelled", LabPilotStyle.TEXT_MUTED)
        else:
            self.status_label.set_status("Idle", LabPilotStyle.TEXT_MUTED)

        if self.odmr_sweep_control is not None:
            self.odmr_sweep_control.set_locked(bool(running))

        if self.axes_control is not None:
            self.axes_control.set_locked(bool(running))
        if self._axes_control_dock is not None:
            # Hidden (not just disabled) while running — dragging/typing a
            # target the scan itself is about to drive past is confusing,
            # and the dock's real estate is more useful showing scan
            # progress while a run is active.
            self._axes_control_dock.setVisible(not running)

        # While running: the in-progress frame. Once finished: fall back to
        # the last completed run's full result, so the view doesn't go
        # blank the moment the poller's live-progress entry stops updating.
        source = state.get("progress") if running else (state.get("last_results") or {})
        if self.result_view is None:
            self._ensure_result_view(source)
        if self.result_view is None:
            return
        if source and self._result_view_adapter is not None:
            self._result_view_adapter.update(self.result_view, self._result_ui_spec, source)
            if self._result_view_adapter is OdmrResultViewAdapter:
                # Cached for the Fit dock's on-demand client-side re-fit
                # (see _add_odmr_sweep_control) — always the same data the
                # view is currently showing. The only window-owned side
                # effect that isn't purely "update this widget," so it
                # stays here rather than inside the adapter.
                self._last_odmr_x = source.get(self._result_ui_spec.get("x_key"))
                self._last_odmr_y = source.get(self._result_ui_spec.get("y_key"))

        # After update_data() — an NDScanResultView's panels (and their
        # crosshairs) are only built lazily on the first frame, so toggling
        # visibility has to happen after that build, not before, or a
        # crosshair created mid-run would default to visible. Always
        # applied (even when `source` was empty this tick — e.g. a
        # finished run with no last_results — so the crosshair can't get
        # stuck hidden). Disappears while a scan is actively running —
        # dragging a live position marker while the scan itself is driving
        # the actuator around would fight the scan's own moves, matching
        # qudi's own scanner GUI (crosshair only active once idle).
        if running:
            self.result_view.hide_crosshair()
        else:
            self.result_view.show_crosshair()

    def _ensure_result_view(self, source: dict | None) -> None:
        """Build a result view from the data, for a template that declares
        no `RESULT_UI`.

        Such a template used to get no result view at all — the window
        opened with the toolbar and the parameter dock and nothing to look
        at, because the view is chosen from the script's static text
        before any data exists. `core/workflow/view.py::pick_view` chooses
        from the result itself, which is only possible now that a result
        describes itself; it can therefore only run once the first frame
        arrives, which is what this is.

        A declared `RESULT_UI` always wins and is never overridden here.
        """
        if self._declared_result_ui or not source:
            return
        from labpilot.core.workflow.view import pick_view

        spec = pick_view(source)
        if not spec:
            return
        self._add_result_view(spec)
        crosshair = spec.get("crosshair")
        if crosshair and self.result_view is not None:
            self._wire_crosshair(self._graph, crosshair)
            self._add_optimizer_dock(crosshair)

    def _wire_crosshair(self, graph: dict[str, Any], crosshair: dict) -> None:
        """Attaches a crosshair (see Image2DResultView.add_crosshair /
        NDScanResultView.add_crosshair) to the result view, click/drag-
        moving the actuator bound to `crosshair["role"]` — a no-op if that
        role isn't bound to a known instrument.

        Deliberately does NOT poll and forward the actuator's live
        position into the crosshair (an earlier pass here did, via
        `_PositionSync`/`_CrosshairSync`) — the crosshair shows the
        *target* (commanded) position, not a live read-back, so it only
        ever moves from user drag/click here, never on its own, including
        while a scan is running (see NDScanResultView's class docstring)."""
        role = crosshair.get("role")
        bindings = graph.get("metadata", {}).get("instrument_bindings", {})
        actuator_id = bindings.get(role) if role else None
        if not actuator_id or actuator_id not in self.instrument_contexts:
            return

        if isinstance(self.result_view, NDScanResultView):
            self.result_view.add_crosshair(
                on_move=lambda changes: self._writer.write(actuator_id, changes)
            )
        else:
            x_axis = crosshair.get("x_axis", "x")
            y_axis = crosshair.get("y_axis", "y")
            self.result_view.add_crosshair(
                on_move=lambda x, y: self._writer.write(actuator_id, {x_axis: x, y_axis: y})
            )

    # ---- per-instrument context (no visible UI — see module docstring) ----

    def _add_instrument(self, instrument_id: str) -> None:
        """Builds this instrument's InstrumentContext only — no
        toolbar/viewer/settings_tree/move_control docks (those belong to
        this instrument's own InstrumentWindow, reachable from the
        Instruments tab, not duplicated here). Polling is NOT started by
        default; only a feature that actually needs this instrument's live
        data (currently just _wire_crosshair) starts it."""
        try:
            inst_data = self.client.get_instrument(instrument_id)
        except Exception as e:
            self.status_bar.showMessage(f"Could not fetch {instrument_id}: {e}")
            return
        if inst_data is None:
            self.status_bar.showMessage(f"Instrument '{instrument_id}' not found — skipping")
            return

        instrument = DashboardInstrument(
            id=inst_data["id"], name=inst_data["name"], adapter_type=inst_data["adapter_type"],
            kind=inst_data["kind"], dimensionality=inst_data["dimensionality"],
            connected=inst_data["connected"], status=inst_data.get("status", "idle"),
            tags=inst_data.get("tags", []),
        )

        schema = fetch_schema(self.client, instrument.id)
        if instrument.kind == "detector" and instrument.dimensionality == "1D":
            value_key, axis_key = pick_1d_series(schema)
        else:
            value_key, axis_key = primary_key(schema), None
        units = schema.get("units", {}).get(value_key, "") if value_key else ""
        axis_units = schema.get("units", {}).get(axis_key, "") if axis_key else ""

        ctx = InstrumentContext(
            instrument, self.client, schema, value_key, axis_key, units, axis_units,
            status_callback=self.status_bar.showMessage,
        )
        self.instrument_contexts[instrument_id] = ctx

    def closeEvent(self, event) -> None:
        self._state_poller.stop()
        if self._optimize_poller is not None:
            self._optimize_poller.stop()
        if isinstance(self.result_view, NDScanResultView):
            self.result_view.stop()
        for ctx in self.instrument_contexts.values():
            ctx.stop_polling()
        self._writer.stop()
        super().closeEvent(event)
