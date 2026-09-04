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

        def _param_for(name: str):
            dtype = settable.get(name, "float64")
            if dtype == "json":
                # No generic editor for a structured value here — a
                # dedicated component (e.g. pulse_sequence_editor) owns
                # rendering/writing it instead. float(list-or-dict) would
                # otherwise crash the whole tree the moment a real value
                # is staged.
                return None
            unit = units.get(name, "")
            if dtype == "bool":
                return {"name": name, "type": "bool", "value": bool(current.get(name, False))}
            opts = {"name": name, "type": "float", "value": float(current.get(name, 0.0))}
            if unit:
                opts["suffix"] = f" {unit}"
            lim = limits.get(name)
            if lim:
                opts["limits"] = tuple(lim)
            return opts

        # Group names sharing a prefix before the first "_" (e.g. a
        # microwave source's cw_frequency/cw_power -> "cw",
        # scan_start/scan_stop/scan_power -> "scan") under one nested
        # parametertree group — purely a display grouping, no effect on
        # what gets written. A name with no shared prefix (the common
        # case — e.g. a spectrometer's lone integration_time_ms) renders
        # exactly as it always has.
        groups: dict[str, list[str]] = {}
        for name in names:
            prefix = name.split("_", 1)[0] if "_" in name else name
            groups.setdefault(prefix, []).append(name)

        children = []
        row_count = 0
        for prefix, group_names in groups.items():
            if len(group_names) > 1:
                sub = [p for n in group_names if (p := _param_for(n)) is not None]
                if sub:
                    children.append({"name": prefix, "type": "group", "children": sub, "expanded": True})
                    row_count += len(sub)
            else:
                p = _param_for(group_names[0])
                if p is not None:
                    children.append(p)
                    row_count += 1

        if not children:
            return  # every name was e.g. json-typed — nothing left to show

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
        d.setMaximumHeight(min(360, 40 + 34 * row_count))
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, d)
        self.dock_widget = d
