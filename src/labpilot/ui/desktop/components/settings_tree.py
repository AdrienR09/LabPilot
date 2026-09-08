"""Per-instrument config-parameter settings dock (tier 3 of the two-tier
parameter system: type-level acquisition defaults come from ui_blocks.toml
via each component's own default_params; this component instead generates
its parameters at runtime from the connected instrument's own DeviceSchema
— e.g. a spectrometer's `integration_time_ms`, a camera's `exposure_ms`/
`gain`). Behavior unchanged from the original `_build_settings_dock`
function, just relocated into the component system.
"""

from __future__ import annotations

from components.base import UIComponent
from components.schema_utils import main_config_names
from components.widgets import dock
from pyqtgraph.parametertree import Parameter, ParameterTree


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
        # The rich records, keyed by name. Everything below prefers these
        # and falls back to the flat views, so an older backend — or a
        # parameter the schema somehow omits — still renders as before.
        declared = {
            p["name"]: p for p in (schema.get("parameters") or []) if p.get("name")
        }

        current: dict = {}
        try:
            inst = ctx.client.get_instrument(ctx.instrument.id)
            if inst:
                current = inst.get("custom_settings", {}) or {}
        except Exception:
            pass

        def _leaf(name: str, param: dict, value):
            """One editable row, from a declared `Parameter`.

            Choices come first: an enumerated setting is a dropdown
            whatever its element type is, and rendering it as a free
            numeric field is how an invalid value gets typed in the first
            place.
            """
            unit = (param.get("unit") if param else None) or units.get(name, "")
            dtype = str((param.get("dtype") if param else None)
                        or settable.get(name, "float64"))
            lim = (param.get("limits") if param else None) or limits.get(name)
            choices = param.get("choices") if param else None

            if choices:
                return {"name": name, "type": "list", "limits": list(choices),
                        "value": value if value in choices else choices[0]}

            if dtype in ("bool",):
                return {"name": name, "type": "bool", "value": bool(value or False)}

            if dtype in ("str", "string"):
                return {"name": name, "type": "str", "value": "" if value is None else str(value)}

            if dtype in ("i8", "int", "int32", "int64"):
                opts = {"name": name, "type": "int", "value": int(value or 0)}
            else:
                opts = {"name": name, "type": "float", "value": float(value or 0.0)}
            if unit:
                opts["suffix"] = f" {unit}"
            if lim:
                low, high = lim
                # pyqtgraph wants a pair; an open side stays open.
                opts["limits"] = (
                    float("-inf") if low is None else low,
                    float("inf") if high is None else high,
                )
            return opts

        def _param_for(name: str):
            param = declared.get(name)
            fields = (param or {}).get("fields") or []

            if fields:
                if list((param or {}).get("shape") or []):
                    # A *table* of records — rows a tree can't add or
                    # reorder. A dedicated component owns those.
                    return None
                # One structured value: a real group whose children are the
                # record's own fields, each carrying its own unit, limits
                # and choices. Marked as a record so a change to any child
                # writes the whole structure, not the bare field.
                staged = current.get(name) or {}
                children = [
                    _leaf(f["name"], f, staged.get(f["name"]))
                    for f in fields if f.get("name")
                ]
                if not children:
                    return None
                return {"name": name, "type": "group", "children": children,
                        "expanded": True, "record": name}

            dtype = str((param or {}).get("dtype") or settable.get(name, "float64"))
            if dtype == "json":
                # Structure this module cannot see into — the old escape
                # hatch. A dedicated component (e.g. pulse_sequence_editor)
                # owns rendering it; float(list-or-dict) would otherwise
                # crash the whole tree the moment a real value is staged.
                return None

            return _leaf(name, param, current.get(name))

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
                # A record's field is not itself a settable parameter: the
                # device accepts the whole structure, so editing one field
                # writes the record with that field replaced. The prefix
                # groups above are display-only and have no `record` opt,
                # so their children keep writing themselves.
                parent = changed_param.parent()
                record = parent.opts.get("record") if parent is not None else None
                if record:
                    name = record
                    payload = {c.name(): c.value() for c in parent.children()}
                else:
                    name = changed_param.name()
                    payload = value
                try:
                    ctx.client.write(ctx.instrument.id, {name: payload}, persist=True)
                except Exception as e:
                    print(f"[InstrumentWindow] Failed to write {name}: {e}")

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
        self.add_dock(d, "right")
        self.dock_widget = d
