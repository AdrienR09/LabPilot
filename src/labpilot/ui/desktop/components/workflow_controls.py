"""Workflow control docks, selected from config rather than by an if/elif.

A workflow window's control dock — the axes table for a scan, the sweep
controls for an ODMR run — used to be chosen by a hand-written chain in
`workflow_window.py`:

    if isinstance(params.get("AXIS_RANGES"), dict) and ...:
        self._add_axes_control(...)
    elif all(k in params for k in ("SWEEP_START", "SWEEP_STOP", ...)):
        self._add_odmr_sweep_control(...)

which is why exactly two named workflow families had usable controls: a
third meant editing that chain, and a template that declared the same
parameters under a different name got nothing. Here each control is a
registered component in the "workflow" context, and `workflow_blocks.toml`
says which ones exist and what each needs a workflow to declare.

The selector is the workflow's own declared parameters. Selecting from the
`RunDescriptor` instead would be better — it is what the run actually does
rather than what its constants are named — but a descriptor only exists
once a plan has been described against live instruments, and a workflow is
a `.py` file with `run(session)` that need not build a plan at all. There
is no route that could answer "what would this workflow's descriptor be"
without running it, so that selector is not reachable for script templates
and is not pretended at here.

Each control's `build` delegates to the `WorkflowWindow` method that
already assembled that dock. The dispatch moved; the docks did not.
"""

from __future__ import annotations

from typing import Any

from labpilot.ui.desktop.components.base import ComponentMeta

__all__ = [
    "AxesControl", "PulseControl", "PulseEditorControl", "SweepControl",
    "WorkflowControl", "controls_for",
]


class WorkflowControl(metaclass=ComponentMeta):
    """One control dock a workflow window can be given."""

    #: Registered under ("workflow", component_type) — see base.ComponentMeta.
    context: str = "workflow"

    #: The `type` string `workflow_blocks.toml` names this control by.
    component_type: str = ""

    @staticmethod
    def applies(params: dict[str, Any], requires: list[str]) -> bool:
        """Whether this workflow declares what the control needs.

        Plain presence, not a type check: a parameter declared with the
        wrong shape is a broken template, and failing visibly where the
        control is built says so better than silently offering no controls
        at all — which is what the `isinstance` guards in the old chain did.
        """
        return all(name in params for name in requires)

    @staticmethod
    def build(window: Any, graph: dict, params: dict[str, Any]) -> None:
        """Attach this control's dock(s) to `window`."""
        raise NotImplementedError


class AxesControl(WorkflowControl):
    """The qudi-scanner-style per-axis range/resolution table, for an
    omniscan-family workflow's AXIS_RANGES/SCAN_AXES/HOLD_POSITIONS."""

    component_type = "axes_control"

    @staticmethod
    def build(window: Any, graph: dict, params: dict[str, Any]) -> None:
        window.build_axes_control(graph, params)


class SweepControl(WorkflowControl):
    """The Sweep Control and Fit docks for an odmr_sweep-family workflow —
    qudi's `OdmrScanControlDockWidget`/`OdmrCwControlDockWidget`/
    `OdmrFitDockWidget`."""

    component_type = "sweep_control"

    @staticmethod
    def build(window: Any, graph: dict, params: dict[str, Any]) -> None:
        window.build_sweep_control(graph, params)


class PulseEditorControl(WorkflowControl):
    """The generator + rig-profile dock for the free-standing pulse
    sequence editor (`workflow_templates/pulse_sequence_editor.py`).

    The only control here that binds no instrument, because the workflow
    it belongs to binds none: it edits parameters and nothing else, which
    is what lets a sequence be designed with no hardware present.
    """

    component_type = "pulse_editor"

    @staticmethod
    def build(window: Any, graph: dict, params: dict[str, Any]) -> None:
        window.build_pulse_editor(graph, params)


class PulseControl(WorkflowControl):
    """The measurement dock for `workflow_templates/pulsed_measurement.py`.

    The other half of `PulseEditorControl`: that one authors a sequence
    with no hardware bound, this one plays a saved one on the rig. Both
    are workflow controls rather than instrument blocks, because what they
    configure is the workflow's parameters — the pulser's own settings are
    its instrument window's business.
    """

    component_type = "pulse_control"

    @staticmethod
    def build(window: Any, graph: dict, params: dict[str, Any]) -> None:
        window.build_pulse_control(graph, params)


def controls_for(params: dict[str, Any], blocks: list[dict]) -> list[type]:
    """The controls this workflow's parameters qualify it for, in the order
    `workflow_blocks.toml` lists them.

    An unknown `type` is skipped rather than raised on: a control this
    build does not have must not stop a window opening, and
    `scripts/verify_ui_registry.py` is where a typo is meant to be caught.
    """
    from labpilot.ui.desktop.components.base import component_for

    chosen: list[type] = []
    for block in blocks:
        control = component_for("workflow", block.get("type", ""))
        if control is None:
            print(f"⚠️  workflow_blocks.toml names no such control {block.get('type')!r}")
            continue
        if control.applies(params, list(block.get("requires", ()))):
            chosen.append(control)
    return chosen
