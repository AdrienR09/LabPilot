"""Generic action-toolbar component.

Builds a QToolBar from a declared list of actions (each a plain dict from
ui_blocks.toml) plus one optional trailing status label. Every action
dispatches to a same-named handler already defined on the generic
`InstrumentWindow` (`on_start`, `on_snapshot`, `on_record`, ...) — this
component only assembles the QAction objects, it doesn't know what the
actions *do*, which is what makes one ToolbarComponent reusable across
every detector window instead of each hand-writing its own toolbar.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QLabel, QSizePolicy, QToolBar, QWidget

from labpilot.ui.desktop.components.base import UIComponent
from labpilot.ui.desktop.components.widgets import toggle_icon
from labpilot.ui.desktop.main import LabPilotStyle


class ToolbarComponent(UIComponent):
    component_type = "toolbar"
    default_params = {
        "title": "Controls",
        "actions": [],       # list of action specs, see _add_action
        "show_info_label": True,
        # Only set True by WorkflowWindow (multiple instruments' toolbars
        # otherwise look identical) — a single-instrument InstrumentWindow
        # only ever has the one toolbar, so it stays off there by default.
        "show_name_label": False,
    }

    def build(self) -> None:
        window = self.window
        ctx = self.ctx
        toolbar = QToolBar(self.params["title"], window)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        if self.params["show_name_label"]:
            name_label = QLabel(f" {ctx.instrument.name} ")
            name_label.setFont(QFont("", 11, QFont.Weight.Bold))
            toolbar.addWidget(name_label)
            toolbar.addSeparator()

        for spec in self.params["actions"]:
            self._add_action(window, ctx, toolbar, spec)

        if self.params["show_info_label"]:
            toolbar.addSeparator()
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            toolbar.addWidget(spacer)
            ctx.info_label = QLabel("")
            ctx.info_label.setProperty("class", "muted")
            toolbar.addWidget(ctx.info_label)

    @staticmethod
    def _add_action(window, ctx, toolbar: QToolBar, spec: dict) -> None:
        name = spec["name"]
        label = spec.get("label", name.replace("_", " ").title())
        checkable = spec.get("checkable", False)

        if checkable and "icon_off" in spec and "icon_on" in spec:
            icon = toggle_icon(spec["icon_off"], spec["icon_on"])
        elif spec.get("icon"):
            icon = LabPilotStyle.icon(spec["icon"])
        else:
            icon = LabPilotStyle.icon("")

        action = QAction(icon, label, window)
        if tip := spec.get("tooltip"):
            action.setToolTip(tip)

        handler = getattr(ctx, f"on_{name}", None)
        if handler is None:
            raise AttributeError(
                f"ToolbarComponent action {name!r} has no ctx.on_{name} handler"
            )

        if checkable:
            action.setCheckable(True)
            action.toggled.connect(handler)
        else:
            action.triggered.connect(handler)

        toolbar.addAction(action)
