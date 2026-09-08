"""The component registry — one registry, for every kind of UI block.

`instruments/_base.py` already has a registry (`AdapterRegistry`), but it's
a plain instance with an explicit `.register(key, cls)` call site per
adapter module. This is deliberately different: `ComponentMeta` registers
every concrete component class automatically at class-definition time,
keyed by its `component_type` — defining a component class *is*
registering it, no separate call needed anywhere. That's what lets
`ui_blocks.toml` reference component types by name and have
`instrument_window.py` look them up generically.

There were briefly two of these. Workflow result views got their own
`RESULT_VIEW_REGISTRY` and their own metaclass, on the reasoning that a
result view has no per-instrument `InstrumentContext` to hang off — "a
real structural difference, not just a naming one". The difference is
real, and it is a difference of *shape*, which a base class expresses;
what it is not is a reason for a second registry, because the question a
registry answers — "which class does this `type` string in a config file
mean?" — is the same question in both cases, and a config format cannot
say "must name a registered component type" while there are two places
that could be.

So the key carries a **context**: `("instrument", "viewer")` and
`("result", "image2d")` live in one table. `UIComponent` and
`ResultViewAdapter` (components/workflow_result.py) are two shapes
registered through one mechanism.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

#: Every registered component, by (context, component_type).
REGISTRY: dict[tuple[str, str], type] = {}


def component_for(context: str, component_type: str) -> Optional[type]:
    """The class a config file's `type` names, or None if nothing claims it."""
    return REGISTRY.get((context, component_type))


def components_in(context: str) -> dict[str, type]:
    """Every component registered for one context, by type name."""
    return {
        component_type: cls
        for (registered, component_type), cls in REGISTRY.items()
        if registered == context
    }


class InstrumentContext:
    """Per-instrument state and acquisition behavior.

    `InstrumentWindow` used to just BE this (one QMainWindow == one
    instrument, so `self.schema`, `self.value_key`, `self.poller`, etc. all
    lived directly on the window and components read them off
    `self.window`). A workflow's combined window (`workflow_window.py`)
    hosts *several* instruments in one shared `QMainWindow`, so this state
    has to live somewhere per-instrument instead — `UIComponent` now takes
    both `window` (the shared Qt widget parent — addDockWidget/addToolBar/
    the one shared status bar) and `ctx` (this class — schema, client,
    value_key, poller, ...). `InstrumentWindow` builds exactly one of these
    for itself; `WorkflowWindow` builds one per referenced instrument.
    """

    def __init__(
        self,
        instrument: Any,
        client: Any,
        schema: dict,
        value_key: Optional[str],
        axis_key: Optional[str],
        units: str,
        axis_units: str,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.instrument = instrument
        self.client = client
        self.schema = schema
        self.value_key = value_key
        self.axis_key = axis_key
        self.units = units
        self.axis_units = axis_units
        self._status_callback = status_callback or (lambda _msg: None)

        self.poll_interval = 200
        self.poller = None  # InstrumentPoller, set by start_polling()
        self.is_recording = False
        self.recorded_data: dict = {"x": [], "y": []}
        self.info_label = None  # created by ToolbarComponent, if present
        self.axes: list[str] = []  # populated by MoveControlComponent
        self.viewer = None  # convenience back-reference, set by ViewerComponent

        # Components bound to this instrument, for on_data() dispatch —
        # populated by whichever window builds this context (InstrumentWindow
        # or WorkflowWindow), one entry per block spec for this instrument.
        self.components: list["UIComponent"] = []

    def set_status(self, message: str) -> None:
        self._status_callback(message)

    def set_info(self, text: str) -> None:
        if self.info_label is not None:
            self.info_label.setText(text)

    # ---- polling lifecycle ----

    def start_polling(self) -> None:
        if self.poller is not None:
            return
        from backend_client import InstrumentPoller

        self.poller = InstrumentPoller(self.client.base_url, self.instrument.id, self.poll_interval)
        self.poller.dataReady.connect(self._on_poll_data)
        self.poller.errorOccurred.connect(self._on_poll_error)
        self.poller.start()

    def stop_polling(self) -> None:
        if self.poller is not None:
            self.poller.stop()
            self.poller = None

    def set_poll_interval(self, ms) -> None:
        self.poll_interval = int(ms)
        if self.poller is not None:
            self.poller.set_interval(self.poll_interval)

    def _on_poll_data(self, data: dict) -> None:
        self._dispatch_data(data)

    def _on_poll_error(self, message: str) -> None:
        self.set_status(f"Read failed: {message}")

    def _dispatch_data(self, data: dict) -> None:
        if self.is_recording and self.value_key is not None and self.value_key in data:
            t = len(self.recorded_data["x"]) * (self.poll_interval / 1000.0)
            self.recorded_data["x"].append(t)
            self.recorded_data["y"].append(float(data[self.value_key]))
        for component in self.components:
            component.on_data(data)

    def take_snapshot(self) -> None:
        """One-shot real measurement (button click or window-open preview —
        a single blocking call here is imperceptible)."""
        import httpx

        try:
            data = self.client.read(self.instrument.id)
        except httpx.HTTPStatusError as e:
            self.set_status(f"Read failed: {e.response.status_code} {e.response.text}")
            return
        except Exception as e:
            self.set_status(f"Read failed: {e}")
            return
        self._dispatch_data(data)

    # ---- generic toolbar action handlers (ToolbarComponent dispatches to these) ----

    def on_start(self, checked: bool) -> None:
        if self.value_key is None:
            self.set_status("This instrument declares no readable value")
            return
        if checked:
            self.start_polling()
            self.set_status("Live acquisition started")
        else:
            self.stop_polling()
            self.set_status("Live acquisition stopped")

    def on_snapshot(self, *_args) -> None:
        if self.value_key is None:
            self.set_status("This instrument declares no readable value")
            return
        self.take_snapshot()

    def on_record(self, checked: bool) -> None:
        self.is_recording = checked
        if checked:
            self.recorded_data = {"x": [], "y": []}
            self.set_status("Recording started")
        else:
            self.set_status(f"Recording stopped. {len(self.recorded_data['x'])} points captured")


class ComponentMeta(type):
    """Auto-registers subclasses that declare a non-empty `component_type`.

    Abstract/intermediate bases (like `UIComponent` itself, which has
    `component_type = ""`) are skipped, so only concrete, usable component
    classes ever appear in `REGISTRY`.

    The entry is keyed by `(context, component_type)` — `context` comes
    from the base class, so a subclass only ever names its own type.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        component_type = namespace.get("component_type")
        if component_type:
            REGISTRY[(getattr(cls, "context", "instrument"), component_type)] = cls
        return cls


class UIComponent(metaclass=ComponentMeta):
    """One self-contained block of instrument-window UI.

    A block spec from `ui_blocks.toml` (e.g. `{ type = "viewer",
    dimensionality = "1D" }`) becomes one `UIComponent` instance:
    `component_for("instrument", spec["type"])(window, ctx, **{k: v
    for k, v in spec.items() if k != "type"})`. `default_params` supplies the
    type-level acquisition defaults (tier 2 of the two-tier parameter
    system) so a block spec only needs to name what it wants to override;
    the per-instrument schema-driven parameters (tier 3, e.g.
    `integration_time_ms`) are a different, separate component
    (`SettingsTreeComponent`) generated at runtime from `DeviceSchema`,
    never from this static config.

    `window` is the shared Qt widget parent (addDockWidget/addToolBar/the
    one shared status bar) — for `InstrumentWindow` that's one instrument's
    own window; for `WorkflowWindow` it's the combined window shared by
    every instrument the workflow touches. `ctx` is this component's own
    `InstrumentContext` — schema, client, value_key, poller, etc. — always
    scoped to exactly one instrument, so a component's `build()`/`on_data()`
    never needs to know which kind of window it's attached to.

    Subclasses set:
        component_type: the registry key used in `ui_blocks.toml`.
        default_params: fallback values merged under the block's own
            params (block params win on conflict).
    And inherit:
        context: "instrument" — which config file's `type` names them.
    And implement:
        build(): attach this component's widgets/actions to `self.window`.
        on_data(data): optional — called with every poll's data dict.
    """

    context: str = "instrument"
    component_type: str = ""
    default_params: dict[str, Any] = {}

    def __init__(self, window, ctx: "InstrumentContext", **params: Any) -> None:
        self.window = window
        self.ctx = ctx
        self.params: dict[str, Any] = {**self.default_params, **params}

    def build(self) -> None:
        """Attach this component's widgets/actions to `self.window`."""
        raise NotImplementedError

    def add_dock(self, dock: Any, default_area: str = "top") -> Any:
        """Place one of this component's docks.

        `ui_blocks.toml` could say *which* blocks a window has but not
        *where* they go: each component called `addDockWidget` with an area
        it had hardcoded, so rearranging a window meant editing Python.
        A block may now say:

            { type = "settings_tree", area = "left" }
            { type = "viewer", tab_with = "Trend" }

        `area` is left/right/top/bottom; `tab_with` names an earlier
        block's dock title and tabs this one behind it, which is how a
        window fits two large views in the space of one. A block that says
        neither keeps the component's own default, so an unedited config
        lays out exactly as before.

        Docks are indexed by title as they are added, which is what lets a
        later block name an earlier one.
        """
        from PyQt6.QtCore import Qt

        areas = {
            "left": Qt.DockWidgetArea.LeftDockWidgetArea,
            "right": Qt.DockWidgetArea.RightDockWidgetArea,
            "top": Qt.DockWidgetArea.TopDockWidgetArea,
            "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
        }
        placed = getattr(self.window, "docks_by_title", None)
        if placed is None:
            placed = {}
            self.window.docks_by_title = placed

        tab_with = self.params.get("tab_with")
        if tab_with and tab_with in placed:
            self.window.tabifyDockWidget(placed[tab_with], dock)
        else:
            if tab_with:
                print(
                    f"⚠️  {self.component_type}: no dock titled {tab_with!r} to tab "
                    f"with — is that block listed after it? Placing it normally."
                )
            requested = str(self.params.get("area") or default_area).lower()
            self.window.addDockWidget(areas.get(requested, areas[default_area]), dock)
        placed[dock.windowTitle()] = dock
        return dock

    def on_data(self, data: dict) -> None:
        """Called with every poll's data dict. Default: no-op — components
        that don't care about live data (e.g. the settings tree) just
        don't override this."""
