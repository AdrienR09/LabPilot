"""Per-instrument native-UI display preferences.

Purely local display choices for an instrument's native Qt window, set
through the existing per-instrument Settings modal in the React
Instruments tab (`InstrumentSettingsModal`), not a new dialog — currently
none are declared (the native actuator window is deliberately just the
simplest fixed control surface, no display-mode choice to make), but the
mechanism (`PrefSpec`/`DISPLAY_PREF_SCHEMA`/`get_display_pref_schema`)
stays in place for the next one that needs it, rather than being ripped
out only to be rebuilt. Distinct from two other, easily-confused config
surfaces in this app:
  - `~/.labpilot/config/ui_blocks.toml` — per (kind, dimensionality)
    *type-level* block layout, not per specific instrument.
  - `DeviceSchema.settable`/`custom_settings` (`write_instrument_settings`
    below, `components/settings_tree.py` on the Qt side) — real device
    parameters, round-tripped to hardware. These prefs are never written
    to any instrument.

Read via `GET /api/dashboard/instruments/{id}/ui_prefs`, written via
`PUT` to the same path (see routes in `core/api/dashboard.py`) — reachable
from both the React frontend and the native Qt desktop app's
`BackendClient`, since neither talks to the other's process directly. A
change only takes effect the next time that instrument's window is
opened — same as editing `ui_blocks.toml` — no live-refresh of an
already-open window.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.config.paths import config_dir as _config_dir

__all__ = [
    "PrefSpec",
    "get_display_pref_schema",
    "get_instrument_ui_prefs",
    "set_instrument_ui_prefs",
]

def _path() -> Path:
    """Resolved per call, not cached at import, so LABPILOT_HOME is honoured
    even when this module is imported before it is set (see config/paths.py)."""
    return _config_dir() / "instrument_ui_prefs.json"


def _load_all() -> dict[str, dict[str, Any]]:
    path = _path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_instrument_ui_prefs(instrument_id: str) -> dict[str, Any]:
    """This instrument's saved UI prefs, or {} if it has none yet."""
    return _load_all().get(instrument_id, {})


def set_instrument_ui_prefs(instrument_id: str, prefs: dict[str, Any]) -> None:
    all_prefs = _load_all()
    all_prefs[instrument_id] = prefs
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_prefs, indent=2))


@dataclass(frozen=True)
class PrefSpec:
    """One declared display preference — the "tier 4" metaobject a
    `UIComponent` subclass would declare (mirrored here, not imported from
    `src/ui/desktop/components/`, so the backend never needs PyQt6 on its
    path). `kind` is a rendering hint for a generic frontend form, the same
    role `generic_params.ParamSpec` plays for device parameters — "bool"
    is the only kind any current pref needs; add "choice"/"int" here first
    if a future preference needs one, rather than hardcoding new JSX.
    """

    kind: str
    label: str
    default: Any = False


# Keyed by instrument `kind` (motor/source/detector/...), matching
# `DashboardInstrument.kind` — not by component_type, since the settings
# modal only knows the instrument's kind, not which UIComponent its native
# window will end up building for it. Empty for every kind today (see
# module docstring); add an entry here (and nowhere else — the frontend's
# InstrumentSettingsModal renders this generically) the next time a native
# component needs a real per-instrument display choice.
DISPLAY_PREF_SCHEMA: dict[str, dict[str, PrefSpec]] = {}


def get_display_pref_schema(kind: str) -> dict[str, dict[str, Any]]:
    """This instrument kind's declared display preferences, JSON-shaped
    for the API layer — {} if this kind has none (e.g. a detector, which
    has no native-UI display prefs today)."""
    return {name: asdict(spec) for name, spec in DISPLAY_PREF_SCHEMA.get(kind, {}).items()}
