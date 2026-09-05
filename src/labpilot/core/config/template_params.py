"""Last-used tunable-parameter values per workflow TEMPLATE (e.g.
"omniscan"), so loading a template again starts from where you left off
instead of the template's hardcoded defaults.

Distinct from an already-loaded workflow *instance*'s own script file,
which already remembers its own edits directly (every `set_workflow_param`
call rewrites that instance's script in place — see `write_workflow_param`)
— that already survives reopening the *same* instance/window, including
across a backend restart (its script_path stays registered in
`WorkflowSetPersistence`). What that doesn't cover is clicking "load
template" again: `load_workflow_template` (server.py) always copies the
template's own original source into a brand-new, separately-tracked
script file, so a fresh instance starts from the template's hardcoded
defaults with no link to any previous instance's edits. This is what
carries values forward into that next fresh instance.

Mirrors `workflow_sets.py`'s `WorkflowSetPersistence` layout/pattern
exactly (same `config_dir`, same atomic temp-then-rename write) — a
sibling directory alongside it, one JSON file per template name:
    ~/.labpilot/config/
        workflows/              # WorkflowSetPersistence
        workflow_template_params/
            <template_name>.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from labpilot.core.config.paths import config_dir as _config_dir

__all__ = ["TemplateParamPersistence"]

_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_-]")


class TemplateParamPersistence:
    """Save/load a workflow template's last-known parameter values."""

    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or _config_dir()
        self.dir = Path(base) / "workflow_template_params"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, template_name: str) -> Path:
        safe = _UNSAFE_CHARS_RE.sub("_", template_name)
        return self.dir / f"{safe}.json"

    def load(self, template_name: str) -> dict[str, object]:
        """{param_name: value} last saved for this template — {} if none
        saved yet, or the file is somehow unreadable (never raises; a
        missing/corrupt status file just means "start from the template's
        own defaults", not a hard failure)."""
        path = self._path(template_name)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, template_name: str, params: dict[str, object]) -> None:
        """Overwrites this template's saved parameter values wholesale —
        called with the *complete* current set (see server.py's
        set_workflow_param) so a since-removed param doesn't linger.
        JSON can't round-trip a tuple (e.g. an AXIS_RANGES entry), so
        those come back as lists — harmless, since every reader unpacks
        them positionally rather than depending on the exact container
        type."""
        path = self._path(template_name)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(params, indent=2, default=str))
        temp_path.rename(path)
