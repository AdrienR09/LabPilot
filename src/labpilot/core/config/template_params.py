"""Last-used tunable-parameter values per workflow TEMPLATE (e.g.
"omniscan"), so loading a template again starts from where you left off
instead of the template's hardcoded defaults.

Distinct from a loaded workflow *instance*'s own settings, which live on
that workflow (`WorkflowGraph.metadata["params"]`, written by
`set_workflow_param`) and survive reopening the same instance, including
across a backend restart. What that does not cover is clicking "load
template" again, which creates a *new* instance with no link to any
previous one's settings — it would otherwise start from the template's
hardcoded defaults. This is what carries values forward into that next
fresh instance.

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
        # `replace`, not `rename`: both are atomic, but only `replace` overwrites
        # an existing target on Windows. `Path.rename` maps to MoveFile without
        # MOVEFILE_REPLACE_EXISTING there, so it raises FileExistsError (WinError
        # 183) on every save after the first — leaving the new content stranded in
        # the .tmp file and the old content in place.
        temp_path.replace(path)
