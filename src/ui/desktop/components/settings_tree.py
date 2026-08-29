"""Per-instrument config-parameter settings dock (tier 3 of the two-tier
parameter system: type-level acquisition defaults come from ui_blocks.toml
via each component's own default_params; this component instead generates
its parameters at runtime from the connected instrument's own DeviceSchema
— e.g. a spectrometer's `integration_time_ms`, a camera's `exposure_ms`/
`gain`). Behavior unchanged from the original `_build_settings_dock`
function, just relocated into the component system.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from pyqtgraph.parametertree import Parameter, ParameterTree

from components.base import UIComponent
from components.widgets import dock
from components.schema_utils import main_config_names


class SettingsTreeComponent(UIComponent):
    component_type = "settings_tree"
    default_params = {"dock_title": "Settings"}

    def build(self) -> None:
        window = self.window
        ctx = self.ctx
        schema = ctx.schema
        names = main_config_names(ctx.instrument.kind, ctx.instrument.dimensionality, schema)
        if not names:
            return  # instrument declares no config-only params — nothing to show

        settable = schema.get("settable", {})
        units = schema.get("units", {})
        limits = schema.get("limits", {})

        current: dict = {}
        try:
            inst = ctx.client.get_instrument(ctx.instrument.id)
            if inst:
                current = inst.get("custom_settings", {}) or {}
        except Exception:
            pass

        children = []
        for name in names:
            dtype = settable.get(name, "float64")
            unit = units.get(name, "")
            if dtype == "bool":
                children.append({"name": name, "type": "bool", "value": bool(current.get(name, False))})
            else:
                opts = {"name": name, "type": "float", "value": float(current.get(name, 0.0))}
                if unit:
                    opts["suffix"] = f" {unit}"
                lim = limits.get(name)
                if lim:
                    opts["limits"] = tuple(lim)
                children.append(opts)

        params = Parameter.create(name="settings", type="group", children=children)

        def _on_change(_param, changes):
            for changed_param, change_type, value in changes:
                if change_type != "value":
                    continue
                try:
                    ctx.client.write(ctx.instrument.id, {changed_param.name(): value})
                except Exception as e:
                    print(f"[InstrumentWindow] Failed to write {changed_param.name()}: {e}")

        params.sigTreeStateChanged.connect(_on_change)

        tree = ParameterTree(showHeader=False)
        tree.setParameters(params, showTop=False)

        d = dock(self.params["dock_title"], window)
        d.setWidget(tree)
        # A handful of parameter rows doesn't need to fill the whole dock
        # area — cap it to roughly its actual content height instead of
        # letting the surrounding QMainWindow stretch it to fill whatever
        # space is available.
        d.setMaximumHeight(min(360, 40 + 34 * len(children)))
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, d)
        self.dock_widget = d
