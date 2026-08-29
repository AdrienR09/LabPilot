"""Named, swappable "loaded workflows" configs.

Mirrors `instrument_sets.py`'s `InstrumentSetPersistence` exactly, for the
same reason: a lab may want a different set of workflow scripts "loaded"
(visible in the Workflows tab) per physical setup. Distinct from
`WorkflowStore` (core/workflow/store.py), which is the actual database of
workflow graphs/execution history — this only stores *paths* to script
files, not their content. A script's default home is `core.
workflow_library`, but a path can point anywhere; unloading a workflow
(removing its path from here) never touches the script file or the
WorkflowStore row it came from.

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

__all__ = ["WorkflowSetError", "WorkflowSetPersistence"]

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class WorkflowSetError(Exception):
    """Raised when workflow-set config operations fail."""


class WorkflowSetPersistence:
    """Save/load/switch between named "loaded workflow scripts" config files."""

    DEFAULT_NAME = "default"

    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or (Path.home() / ".labpilot" / "config")
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

    def save(self, name: str, script_paths: list[str]) -> Path:
        """Write a named config (overwriting if it already exists)."""
        path = self._path(name)
        payload = {
            "name": name,
            "updated_at": time.time(),
            "script_paths": list(script_paths),
        }
        temp_path = path.with_suffix(".cfg.tmp")
        temp_path.write_text(json.dumps(payload, indent=2))
        temp_path.rename(path)
        return path

    def add_to_active(self, script_path: str) -> str:
        """Add a script path to the active config (creating/activating the
        default one if none is active yet). Shared by every place a
        workflow becomes "loaded" — the create/load REST routes
        (server.py) and the AI's create_workflow/write_workflow_script
        tools (core/ai/tools/workflow_tools.py) — so they can't drift.

        Returns the active config's name.
        """
        active = self.get_active_name() or self.DEFAULT_NAME
        paths = self.load(active) if self.exists(active) else []
        if script_path not in paths:
            paths.append(script_path)
            self.save(active, paths)
        self.set_active_name(active)
        return active

    def remove_from_active(self, script_path: str) -> None:
        """Remove a script path from the active config, if one is active.
        No-op if there's no active config or the path isn't in it."""
        active = self.get_active_name()
        if active is None:
            return
        paths = [p for p in self.load(active) if p != script_path]
        self.save(active, paths)

    def load(self, name: str) -> list[str]:
        """Read a named config's loaded script paths."""
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
