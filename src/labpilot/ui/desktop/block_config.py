"""Loading the block-config files, `ui_blocks.toml` and `workflow_blocks.toml`.

Both follow the same rule: a packaged default is copied to
`~/.labpilot/config/` on first run, so it is immediately editable rather
than hidden inside the installed package (the convention
core/config/instrument_sets.py already uses for per-lab config), and it is
re-read every time a window opens — no restart to see an edit.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

__all__ = ["load_block_config", "load_ui_blocks", "load_workflow_blocks"]

_PACKAGED = Path(__file__).parent / "config"
_USER = Path.home() / ".labpilot" / "config"


def load_block_config(name: str) -> dict[str, Any]:
    """One named block-config file, from the user's copy of it."""
    user = _USER / name
    if not user.exists():
        user.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_PACKAGED / name, user)
    with open(user, "rb") as f:
        return tomllib.load(f)


def load_ui_blocks() -> dict[str, Any]:
    """Which blocks each (instrument kind, dimensionality) window gets."""
    return load_block_config("ui_blocks.toml")


def load_workflow_blocks() -> list[dict[str, Any]]:
    """Which control docks a workflow window can be given, in order."""
    return list(load_block_config("workflow_blocks.toml").get("controls", []))
