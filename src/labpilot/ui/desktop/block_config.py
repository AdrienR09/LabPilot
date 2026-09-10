"""Loading the block-config files, `ui_blocks.toml` and `workflow_blocks.toml`.

Both follow the same rule: a packaged default is copied to
`~/.labpilot/config/` on first run, so it is immediately editable rather
than hidden inside the installed package (the convention
core/config/instrument_sets.py already uses for per-lab config), and it is
re-read every time a window opens — no restart to see an edit.

## The user's file is an override layer, not a replacement

It used to be a replacement, and that was a silent bug with a long fuse.
The packaged file was copied once and never consulted again, so every
block added afterwards was invisible to anyone who had run the app
before — no error, no warning, just a control that never appeared. The
pulse editor and the two capability sections were added over a period
during which any existing installation simply never saw them.

So the packaged file is now the base and the user's is merged on top:

- a section or a block the user did not touch keeps whatever the package
  ships, including blocks added by an upgrade;
- a block the user *did* touch wins, matched by `type`, so an edited
  `poll_rate` or a rewritten `requires` survives;
- a block the user invented is kept.

The one thing merging cannot express is deletion — a line removed from
the user's file simply looks like a line they never wrote. So removal is
explicit: a top-level `disabled = ["axes_control"]` drops a block or
control by `type`, everywhere it appears.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

__all__ = ["load_block_config", "load_ui_blocks", "load_workflow_blocks", "merge_blocks"]

_PACKAGED = Path(__file__).parent / "config"
_USER = Path.home() / ".labpilot" / "config"

#: Top-level key naming block/control `type`s to drop after merging.
DISABLED = "disabled"


def load_block_config(name: str, packaged: Path | None = None, user: Path | None = None) -> dict[str, Any]:
    """One named block-config file: the packaged default, with the user's
    edits merged over it."""
    source = (packaged or _PACKAGED) / name
    target = (user or _USER) / name

    shipped = _read(source)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
        return _without_disabled(shipped, _disabled(shipped))
    return merge_blocks(shipped, _read(target))


def merge_blocks(packaged: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """The packaged config with the user's on top.

    Kept as a plain function of two dicts so the merge rule is testable
    without a home directory, which is the part that actually has to be
    right.
    """
    merged = _merge(packaged, user)
    return _without_disabled(merged, _disabled(merged))


def _read(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in over.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge(existing, value)
        elif _typed(existing) and _typed(value):
            merged[key] = _merge_typed(existing, value)
        else:
            merged[key] = value
    return merged


def _typed(value: Any) -> bool:
    """A list of blocks — dicts each naming a `type`, which is what makes
    them mergeable one by one rather than wholesale."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) and "type" in item for item in value)
    )


def _merge_typed(base: list[dict], over: list[dict]) -> list[dict]:
    """Packaged order, with the user's version of each block winning and
    anything they invented appended.

    Order matters: `workflow_blocks.toml`'s list is the order the docks
    appear in, and `ui_blocks.toml`'s is the order a window stacks them.
    Keeping the packaged order means an upgrade's new block lands where
    the package meant it to, not at the end.
    """
    by_type = {item["type"]: item for item in over}
    merged = [{**item, **by_type.pop(item["type"], {})} for item in base]
    return merged + list(by_type.values())


def _disabled(config: dict[str, Any]) -> set[str]:
    value = config.get(DISABLED)
    return {str(name) for name in value} if isinstance(value, list) else set()


def _without_disabled(config: dict[str, Any], names: set[str]) -> dict[str, Any]:
    if not names:
        return config
    cleaned: dict[str, Any] = {}
    for key, value in config.items():
        if key == DISABLED:
            continue
        if isinstance(value, dict):
            cleaned[key] = _without_disabled(value, names)
        elif _typed(value):
            cleaned[key] = [item for item in value if item["type"] not in names]
        else:
            cleaned[key] = value
    return cleaned


def load_ui_blocks() -> dict[str, Any]:
    """Which blocks each (instrument kind, dimensionality) window gets."""
    return load_block_config("ui_blocks.toml")


def load_workflow_blocks() -> list[dict[str, Any]]:
    """Which control docks a workflow window can be given, in order."""
    return list(load_block_config("workflow_blocks.toml").get("controls", []))
