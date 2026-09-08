"""Generic instrument-action-button component.

Renders one button per entry in `DeviceSchema.actions` — adapter methods
that aren't a `set_<key>` settable write (e.g. a microwave source's
`cw_on`/`off`, a pulse sequencer's `start`/`stop`). Schema-driven, like
SettingsTreeComponent: nothing in ui_blocks.toml needs to name the
individual actions, so any adapter that declares `actions` gets working
buttons for free, and an adapter that declares none makes this component
build nothing at all — safe to add to any block unconditionally.

An action that declares arguments gets a form instead of a bare button.
The form is generated from the action's `Parameter`s, so the same
declaration that makes the argument validate server-side also decides
which widget the user gets, what unit is shown beside it and what range
the spin box will accept — a limit is enforced in one place and displayed
everywhere.
"""

from __future__ import annotations

from typing import Any

import httpx
from components.base import UIComponent
from components.widgets import IconButton, dock
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

#: Actions whose name reads as a question rather than a command, for the
#: button label only.
_TITLE_OVERRIDES = {"cw_on": "CW On", "off": "Off"}


def _label(name: str) -> str:
    return _TITLE_OVERRIDES.get(name, name.replace("_", " ").title())


def _widget_for(param: dict[str, Any], initial: Any) -> QWidget:
    """One input widget for one declared argument.

    Branches on the canonical dtype, and on `choices` first — an
    enumerated argument is a combo box whatever its element type is.
    """
    choices = param.get("choices")
    if choices:
        widget = QComboBox()
        for choice in choices:
            widget.addItem(str(choice), choice)
        if initial is not None:
            index = widget.findData(initial)
            if index >= 0:
                widget.setCurrentIndex(index)
        return widget

    dtype = str(param.get("dtype") or "f8")
    unit = param.get("unit") or ""
    low, high = (param.get("limits") or (None, None))

    if dtype in ("bool",):
        widget = QCheckBox()
        widget.setChecked(bool(initial))
        return widget

    if dtype in ("i8", "int", "int32", "int64"):
        widget = QSpinBox()
        # Qt's int spin box is 32-bit; clamp rather than overflow.
        widget.setRange(
            int(low) if low is not None else -(2**31 - 1),
            int(high) if high is not None else 2**31 - 1,
        )
        if unit:
            widget.setSuffix(f" {unit}")
        if initial is not None:
            widget.setValue(int(initial))
        return widget

    if dtype in ("str", "string"):
        widget = QLineEdit()
        if initial is not None:
            widget.setText(str(initial))
        return widget

    widget = QDoubleSpinBox()
    widget.setDecimals(9)
    widget.setRange(
        float(low) if low is not None else -1e18,
        float(high) if high is not None else 1e18,
    )
    if unit:
        widget.setSuffix(f" {unit}")
    if initial is not None:
        widget.setValue(float(initial))
    return widget


def _value_of(widget: QWidget) -> Any:
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return widget.text()
    return None


class ArgumentDialog(QDialog):
    """A form for one action's declared arguments."""

    def __init__(self, action: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_label(action.get("name", "")))
        self._widgets: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setContentsMargins(12, 12, 12, 8)
        defaults = action.get("defaults") or {}

        for param in action.get("params") or ():
            name = param.get("name")
            if not name:
                continue
            widget = _widget_for(param, defaults.get(name))
            description = param.get("description") or ""
            if description:
                widget.setToolTip(description)
            self._widgets[name] = widget
            form.addRow(name.replace("_", " "), widget)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def arguments(self) -> dict[str, Any]:
        return {name: _value_of(w) for name, w in self._widgets.items()}


class ActionsComponent(UIComponent):
    component_type = "actions"
    default_params = {"dock_title": "Actions"}

    def build(self) -> None:
        ctx = self.ctx
        actions = _declared(ctx.schema)
        if not actions:
            return  # nothing declared — no dock

        window = self.window
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        for action in actions:
            name = action["name"]
            takes_args = bool(action.get("params"))
            btn = IconButton(_label(name) + ("…" if takes_args else ""))
            if action.get("description"):
                btn.setToolTip(action["description"])
            btn.clicked.connect(
                lambda _checked=False, a=action: self._invoke(a)
            )
            layout.addWidget(btn)
        layout.addStretch()

        d = dock(self.params["dock_title"], window)
        d.setWidget(content)
        d.setMaximumHeight(48 + 40 * len(actions))
        self.add_dock(d, "right")

    def _invoke(self, action: dict[str, Any]) -> None:
        arguments: dict[str, Any] = {}
        if action.get("params"):
            dialog = ArgumentDialog(action, self.window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            arguments = dialog.arguments()
        self._call(action["name"], arguments)

    def _call(self, name: str, arguments: dict[str, Any]) -> None:
        ctx = self.ctx
        try:
            result = ctx.client.call_action(ctx.instrument.id, name, arguments or None)
        except httpx.HTTPStatusError as e:
            ctx.set_status(f"{name} failed: {e.response.status_code} {e.response.text}")
            return
        except Exception as e:
            ctx.set_status(f"{name} failed: {e}")
            return
        # A negotiating command reports what it actually applied — worth
        # showing, since it is often not what was asked for.
        if isinstance(result, dict) and result:
            applied = ", ".join(f"{k}={v}" for k, v in result.items())
            ctx.set_status(f"{name}: {applied}")
        else:
            ctx.set_status(f"{name} called")


def _declared(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """The action records off a serialised schema.

    Tolerates the older plain-name list so a new desktop app still talks to
    an older backend.
    """
    actions = schema.get("actions") or []
    return [
        {"name": a, "params": [], "defaults": {}} if isinstance(a, str) else a
        for a in actions
    ]
