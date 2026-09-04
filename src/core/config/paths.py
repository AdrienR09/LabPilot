"""Where LabPilot keeps per-user state.

Everything that persists across runs — instrument sets, workflow sets,
UI preferences, saved layouts, logs — lives under one root, resolved here
rather than by each module hardcoding `Path.home() / ".labpilot"`.

Set `LABPILOT_HOME` to relocate it. That is what the test suite does: before
this existed, anything that exercised the dashboard manager wrote into the
developer's *real* `~/.labpilot`, so a test that created an instrument left it
in the active instrument set and it was loaded back on the next real server
start.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["config_dir", "labpilot_home"]


def labpilot_home() -> Path:
    """Root directory for persistent LabPilot state (`~/.labpilot` by default).

    Read on every call rather than cached at import, so a process can set
    `LABPILOT_HOME` before touching the config layer and have it apply.
    """
    override = os.environ.get("LABPILOT_HOME")
    return Path(override).expanduser() if override else Path.home() / ".labpilot"


def config_dir() -> Path:
    """The `config/` subdirectory holding instrument sets, workflow sets and
    UI preferences."""
    return labpilot_home() / "config"
