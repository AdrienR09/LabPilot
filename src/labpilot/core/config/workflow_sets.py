"""Named, swappable "loaded workflows" configs.

Mirrors `instrument_sets.py`'s `InstrumentSetPersistence` exactly, for the
same reason: a lab may want a different set of workflows "loaded" (visible
in the Workflows tab) per physical setup. Distinct from `WorkflowStore`
(core/workflow/store.py), which is the actual database of workflow
graphs/execution history — this only stores which of them are loaded.
Unloading a workflow never touches its script file or its WorkflowStore
row.

## Entries are workflow ids

They used to be script *paths*, which made the path a workflow instance's
identity — and so two instances of one template had to be two copies of
its source, written into the installed package under timestamped names.
Parameters lived in those copies and were edited by rewriting the
assignment in place. Identifying an instance by its id instead is what
lets a template be shared and its settings be a row (see the `params`
entry in `WorkflowGraph.metadata`).

Legacy path entries are still read: a config written before this change
lists paths, and `server.py` maps each to the workflow it belongs to.

Directory layout — note this lives one level up from instrument configs
(`server.py` constructs this with `config_dir=ConfigPersistence.config_dir`,
i.e. `~/.labpilot`, not `~/.labpilot/config` — unlike `InstrumentSetPersistence()`,
which is built with no arg and so falls back to its own `~/.labpilot/config`
default). `workflows.db` (WorkflowStore) sits alongside these files as a
sibling, both under the same directory:
    ~/.labpilot/
        config/
            instruments/   # see instrument_sets.py
        workflows/
            <name>.cfg  # one per named config — list of loaded script paths
            .active     # plain text file naming the currently active config
            workflows.db
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from labpilot.core.config.paths import config_dir as _config_dir

__all__ = ["WorkflowSetError", "WorkflowSetPersistence"]

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class WorkflowSetError(Exception):
    """Raised when workflow-set config operations fail."""


class WorkflowSetPersistence:
    """Save/load/switch between named "loaded workflow scripts" config files."""

    DEFAULT_NAME = "default"

    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or _config_dir()
        self.dir = Path(base) / "workflows"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._active_marker = self.dir / ".active"

    def _validate_name(self, name: str) -> None:
        if not _NAME_RE.match(name):
            raise WorkflowSetError(
                f"Invalid config name {name!r} — use letters, digits, '_' or '-' only."
            )

    def _path(self, name: str) -> Path:
        self._validate_name(name)
        return self.dir / f"{name}.cfg"

    def list_configs(self) -> list[str]:
        """Names of all saved workflow-set configs."""
        return sorted(p.stem for p in self.dir.glob("*.cfg"))

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def get_active_name(self) -> str | None:
        """Name of the currently active config, if one has been set."""
        if self._active_marker.exists():
            name = self._active_marker.read_text().strip()
            if name and self.exists(name):
                return name
        return None

    def set_active_name(self, name: str) -> None:
        self._validate_name(name)
        self._active_marker.write_text(name)

    def save(self, name: str, entries: list[str]) -> Path:
        """Write a named config (overwriting if it already exists).

        Entries are workflow ids. The key stays `script_paths` so a config
        written here is still readable by an older build, and because the
        list is opaque to this class either way.
        """
        path = self._path(name)
        payload = {
            "name": name,
            "updated_at": time.time(),
            "script_paths": list(entries),
        }
        temp_path = path.with_suffix(".cfg.tmp")
        temp_path.write_text(json.dumps(payload, indent=2))
        # `replace`, not `rename`: both are atomic, but only `replace` overwrites
        # an existing target on Windows. `Path.rename` maps to MoveFile without
        # MOVEFILE_REPLACE_EXISTING there, so it raises FileExistsError (WinError
        # 183) on every save after the first — leaving the new content stranded in
        # the .tmp file and the old content in place.
        temp_path.replace(path)
        return path

    def add_to_active(self, entry: str) -> str:
        """Mark a workflow as loaded in the active config (creating and
        activating the default one if none is active yet). Shared by every
        place a workflow becomes "loaded" so they cannot drift.

        Returns the active config's name.
        """
        active = self.get_active_name() or self.DEFAULT_NAME
        entries = self.load(active) if self.exists(active) else []
        if entry not in entries:
            entries.append(entry)
            self.save(active, entries)
        self.set_active_name(active)
        return active

    def remove_from_active(self, *entries: str) -> None:
        """Unload a workflow from the active config.

        Takes several entries because a workflow loaded before ids were
        used is listed by its script path, and unloading it has to remove
        whichever form is actually there.
        """
        active = self.get_active_name()
        if active is None:
            return
        removed = set(entries)
        self.save(active, [e for e in self.load(active) if e not in removed])

    def load(self, name: str) -> list[str]:
        """Read a named config's loaded workflows (ids, or legacy paths)."""
        path = self._path(name)
        if not path.exists():
            raise WorkflowSetError(f"No workflow config named {name!r}")
        try:
            payload = json.loads(path.read_text())
            return list(payload.get("script_paths", []))
        except (json.JSONDecodeError, TypeError) as e:
            raise WorkflowSetError(f"Failed to load workflow config {name!r}: {e}") from e

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise WorkflowSetError(f"No workflow config named {name!r}")
        path.unlink()
        if self.get_active_name() == name:
            self._active_marker.unlink(missing_ok=True)
