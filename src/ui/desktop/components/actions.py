"""Generic instrument-action-button component.

Renders one button per name in `DeviceSchema.actions` — zero-argument
adapter methods that aren't a `set_<key>` settable write (e.g. a
microwave source's `cw_on`/`off`, a pulse sequencer's `start`/`stop`).
Schema-driven, like SettingsTreeComponent: nothing in ui_blocks.toml
needs to name the individual actions, so any adapter that declares
`actions` gets working buttons for free, and an adapter that declares
none makes this component build nothing at all — safe to add to any
block unconditionally.
"""

from __future__ import annotations

import httpx
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from components.base import UIComponent
from components.widgets import IconButton, dock
from PyQt6.QtCore import Qt


class ActionsComponent(UIComponent):
    component_type = "actions"
    default_params = {"dock_title": "Actions"}

    def build(self) -> None:
        ctx = self.ctx
        actions = ctx.schema.get("actions", [])
        if not actions:
            return  # nothing declared — no dock

        window = self.window
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        for name in actions:
            btn = IconButton(name.replace("_", " ").title())
            btn.clicked.connect(lambda _checked=False, n=name: self._call(n))
            layout.addWidget(btn)
        layout.addStretch()

        d = dock(self.params["dock_title"], window)
        d.setWidget(content)
        d.setMaximumHeight(48 + 40 * len(actions))
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, d)

    def _call(self, name: str) -> None:
        ctx = self.ctx
        try:
            ctx.client.call_action(ctx.instrument.id, name)
            ctx.set_status(f"{name} called")
        except httpx.HTTPStatusError as e:
            ctx.set_status(f"{name} failed: {e.response.status_code} {e.response.text}")
        except Exception as e:
            ctx.set_status(f"{name} failed: {e}")
