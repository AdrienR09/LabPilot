"""Shared instrument-kind -> block-config resolution.

Both `InstrumentWindow` (one instrument, its own window) and
`WorkflowWindow` (several instruments sharing one window) need to answer
the same question for a given instrument: which `ui_blocks.toml` top-level
kind it belongs to (collapsing "motor"->"actuator" and
"counter"/"generic"->"detector"), which dimensionality key that config
uses for it ("SOURCE" is a fixed literal key, not a real dimensionality),
which block list that resolves to, and whether its window should start
polling immediately. Previously each window duplicated this mapping
inline — a kind added to one and not the other would silently diverge.
This is the actual "typical UI window per instrument type" logic the
atomic-component framework is built around, so it belongs in exactly one
place, shared by both windows.
"""

from __future__ import annotations

from typing import Optional

_TITLE_SUFFIX = {
    ("detector", "0D"): "Time Series",
    ("detector", "1D"): "Spectrometer",
    ("detector", "2D"): "Scanner",
    ("detector", "ND"): "ND Viewer",
    ("actuator", "0D"): "Switch",
    ("actuator", "1D"): "Motor Control",
    ("actuator", "ND"): "Multi-Axis Motor Control",
    ("source", "SOURCE"): "Source Control",
}


def config_kind(kind: str) -> str:
    """Raw `DashboardInstrument.kind` -> `ui_blocks.toml` top-level key."""
    if kind in ("counter", "generic"):
        kind = "detector"
    return "actuator" if kind == "motor" else kind


def config_dimensionality(kind: str, dimensionality: str) -> str:
    """`ui_blocks.toml` second-level key — "SOURCE" is a fixed literal key
    for every source regardless of its real dimensionality."""
    return dimensionality if config_kind(kind) != "source" else "SOURCE"


def resolve_blocks(kind: str, dimensionality: str, block_config: dict) -> list[dict]:
    """This instrument's block list from a loaded `ui_blocks.toml`, falling
    back to a plain 0D-style readout for an unknown kind/dimensionality
    combination rather than crashing."""
    ck = config_kind(kind)
    cd = config_dimensionality(kind, dimensionality)
    type_config = block_config.get(ck, {}).get(cd)
    if type_config is None:
        type_config = block_config.get("detector", {}).get("0D", {"blocks": []})
    return type_config.get("blocks", [])


def should_auto_start_polling(kind: str, dimensionality: str) -> bool:
    """Detectors are Start/Stop-toggled by the user (ToolbarComponent's
    "start" action); numeric actuators/sources show live position/output
    continuously for as long as the window is open, like Qudi's own motor
    modules always have. A boolean (switch-style) actuator has nothing to
    poll for — its state only changes when this window itself writes it —
    so it stays read-once."""
    ck = config_kind(kind)
    return ck == "source" or (ck == "actuator" and dimensionality != "0D")


def title_suffix(kind: str, dimensionality: str) -> Optional[str]:
    """The `_TITLE_SUFFIX` window-title tag for this instrument's typical
    window (e.g. "Spectrometer", "Multi-Axis Motor Control") — None for an
    unrecognized combination."""
    ck = config_kind(kind)
    cd = config_dimensionality(kind, dimensionality)
    return _TITLE_SUFFIX.get((ck, cd))
