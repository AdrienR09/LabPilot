"""Generic, config-driven native instrument window.

Replaces the old Detector0D/1D/2DWindow, Motor0D/1D/MultiAxisWindow, and
SourceWindow classes (instrument_windows.py) with a single `InstrumentWindow`
assembled from a list of `UIComponent` blocks (components/) declared per
`[kind."dimensionality"]` in `~/.labpilot/config/ui_blocks.toml`. See that
file's header comment and components/base.py's module docstring for the
full rationale.
"""

from __future__ import annotations

# Must be set before qtpy (pulled in by the viewer toolkit) is imported
# anywhere. This env can also have a standalone PyQt5 install alongside our
# Pin the Qt binding before qtpy is imported by anything — the rule,
# and why it matters, live in labpilot/ui/qt_api.py.
import labpilot.ui.qt_api  # noqa: F401 — imported for its side effect

# isort: split

import shutil
import tomllib
import warnings
from pathlib import Path
from typing import Optional

from pymodaq_data.data import DataIndexWarning
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QMainWindow, QStatusBar, QWidget

# Expected on every poll where a component doesn't supply an axis itself
# (bare 0D values, 2D images with no wavelength/position axes) — the
# viewer toolkit just auto-generates a linear one, which is exactly what
# we want. Not a real problem, so don't let it spam the log every frame.
warnings.filterwarnings("ignore", category=DataIndexWarning)

from backend_client import BackendClient
from components import component_for, components_in
from components.base import InstrumentContext
from components.schema_utils import fetch_schema, pick_1d_series, primary_key
from instrument_blocks import resolve_blocks, should_auto_start_polling, title_suffix
from main import DashboardInstrument, LabPilotStyle

_PACKAGED_DEFAULT_CONFIG = Path(__file__).parent / "config" / "ui_blocks.toml"
_USER_CONFIG = Path.home() / ".labpilot" / "config" / "ui_blocks.toml"


def _load_block_config() -> dict:
    """User-editable block config, consistent with how
    core/config/instrument_sets.py already keeps per-lab config under
    ~/.labpilot/config/ — a packaged default is copied there on first run
    so it's immediately editable rather than hidden inside the package."""
    if not _USER_CONFIG.exists():
        _USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_PACKAGED_DEFAULT_CONFIG, _USER_CONFIG)
    with open(_USER_CONFIG, "rb") as f:
        return tomllib.load(f)


class InstrumentWindow(QMainWindow):
    """One native instrument window, assembled entirely from `block_specs`.

    Each spec is a plain dict (`{"type": "viewer", "dimensionality": "1D"}`,
    etc.) — `type` looks up a `UIComponent` subclass in the registry,
    everything else is passed through as that component's params (merged
    over its own `default_params`). Components attach whatever docks/
    toolbars they need in the order given; `InstrumentWindow` itself only
    owns the schema, the single `InstrumentPoller`, and the handful of
    acquisition concepts (start/stop, snapshot, record) that are generic
    across every instrument kind rather than belonging to one component.
    """

    def __init__(
        self,
        instrument: DashboardInstrument,
        client: BackendClient,
        block_specs: list[dict],
        auto_start_polling: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        # Kept directly on the window (not just reachable via self.ctx) since
        # session_manager.py reads window.instrument for its window registry.
        self.instrument = instrument
        self.client = client

        schema = fetch_schema(client, instrument.id)
        if instrument.kind == "detector" and instrument.dimensionality == "1D":
            value_key, axis_key = pick_1d_series(schema)
        else:
            value_key, axis_key = primary_key(schema), None
        units = schema.get("units", {}).get(value_key, "") if value_key else ""
        axis_units = schema.get("units", {}).get(axis_key, "") if axis_key else ""

        self.setDockNestingEnabled(True)
        central = QWidget()
        central.setFixedSize(1, 1)
        self.setCentralWidget(central)
        central.hide()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        if not instrument.connected:
            self.status_bar.showMessage("Not connected — reads/writes will fail until it's connected")
        else:
            self.status_bar.showMessage("Ready")

        self.ctx = InstrumentContext(
            instrument, client, schema, value_key, axis_key, units, axis_units,
            status_callback=self.status_bar.showMessage,
        )

        suffix = title_suffix(instrument.kind, instrument.dimensionality)
        self.setWindowTitle(f"qudi: {instrument.name} ({suffix})" if suffix else instrument.name)
        self.resize(1000, 700)

        for spec in block_specs:
            spec = dict(spec)
            component_type = spec.pop("type")
            component_cls = component_for("instrument", component_type)
            if component_cls is None:
                raise KeyError(
                    f"ui_blocks.toml names no such block type {component_type!r}. "
                    f"Known: {', '.join(sorted(components_in('instrument')))}"
                )
            component = component_cls(self, self.ctx, **spec)
            component.build()
            self.ctx.components.append(component)

        # If every dock this window built has an explicit max height (a
        # genuinely compact, bounded-content window — e.g. a plain
        # actuator's move-control dock, no plot/image to fill), shrink the
        # window to match instead of leaving it at the default 1000x700
        # sized for a plot-based window with real content to grow into.
        docks = self.findChildren(QDockWidget)
        if docks and all(d.maximumHeight() < 16000 for d in docks):
            content_height = sum(d.maximumHeight() for d in docks)
            self.resize(560, min(700, content_height + 90))

        # Show something immediately rather than a blank window until the
        # user presses Start — harmless for continuously-polled actuators/
        # sources (auto_start_polling handles those below) and matches the
        # previous per-class behavior for 1D/2D detectors.
        if self.ctx.value_key is not None:
            self.ctx.take_snapshot()

        if auto_start_polling:
            self.ctx.start_polling()

    def closeEvent(self, event) -> None:
        self.ctx.stop_polling()
        super().closeEvent(event)


def create_instrument_window(instrument: DashboardInstrument, client: Optional[BackendClient] = None) -> QMainWindow:
    """Public factory — signature unchanged from the old per-class version
    (main.py and session_manager.py both import this by name)."""
    if client is None:
        client = BackendClient()

    config = _load_block_config()
    blocks = resolve_blocks(instrument.kind, instrument.dimensionality, config)
    auto_start_polling = should_auto_start_polling(instrument.kind, instrument.dimensionality)

    window = InstrumentWindow(
        instrument, client, blocks, auto_start_polling=auto_start_polling,
    )
    return window
