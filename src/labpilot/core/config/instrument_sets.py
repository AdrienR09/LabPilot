"""Named, swappable instrument-set configs.

Distinct from `SessionConfig`/`ConfigPersistence` in this package (which
persist one current session's UI/AI/workflow state to a single file): this
holds *multiple named snapshots* of "which instruments are loaded, with what
connection params", one JSON file per name, so a lab can keep separate
configs per physical setup and switch between them.

Directory layout (sibling to workflow configs under the same config root):
    ~/.labpilot/config/
        instruments/
            <name>.cfg    # one per named config — list of DeviceConfig entries
                          # (JSON content; .cfg extension by convention, same
                          # as Qudi's own per-setup config files)
            .active       # plain text file naming the currently active config
        workflows/        # see workflow_sets.py's WorkflowSetPersistence — the
                          # equivalent config system for loaded workflow scripts
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from labpilot.core.config.paths import config_dir as _config_dir

if TYPE_CHECKING:
    from labpilot.core.lab.spec import InstrumentSpec

__all__ = ["InstrumentSetError", "InstrumentSetPersistence"]

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class InstrumentSetError(Exception):
    """Raised when instrument-set config operations fail."""


class InstrumentSetPersistence:
    """Save/load/switch between named instrument-set config files."""

    DEFAULT_NAME = "default"

    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or _config_dir()
        self.dir = Path(base) / "instruments"
        self.dir.mkdir(parents=True, exist_ok=True)
        # Reserved for the equivalent workflow-config system.
        (Path(base) / "workflows").mkdir(parents=True, exist_ok=True)
        self._active_marker = self.dir / ".active"

    def _validate_name(self, name: str) -> None:
        if not _NAME_RE.match(name):
            raise InstrumentSetError(
                f"Invalid config name {name!r} — use letters, digits, '_' or '-' only."
            )

    def _path(self, name: str) -> Path:
        self._validate_name(name)
        return self.dir / f"{name}.cfg"

    def list_configs(self) -> list[str]:
        """Names of all saved instrument-set configs."""
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

    def save(self, name: str, entries: list[InstrumentSpec]) -> Path:
        """Write a named config (overwriting if it already exists).

        Only specs are written. A config file used to also carry each
        instrument's `status` and `last_connected` — facts about a process
        rather than a configuration, saved because the two shared one
        record. Nothing ever read them back.
        """
        path = self._path(name)
        payload = {
            "name": name,
            "updated_at": time.time(),
            "devices": [e.to_dict() for e in entries],
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

    def load(self, name: str) -> list[InstrumentSpec]:
        """Read a named config's instrument specs.

        `InstrumentSpec.from_dict` reads both the current key names and the
        ones files on disk already use, so an existing config loads
        unchanged. Imported here rather than at module scope: `core.lab`
        imports *this* module, and a top-level import would close the loop.
        """
        from labpilot.core.lab.spec import InstrumentSpec

        path = self._path(name)
        if not path.exists():
            raise InstrumentSetError(f"No instrument config named {name!r}")
        try:
            payload = json.loads(path.read_text())
            return [InstrumentSpec.from_dict(d) for d in payload.get("devices", [])]
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise InstrumentSetError(f"Failed to load instrument config {name!r}: {e}") from e

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise InstrumentSetError(f"No instrument config named {name!r}")
        path.unlink()
        if self.get_active_name() == name:
            self._active_marker.unlink(missing_ok=True)
