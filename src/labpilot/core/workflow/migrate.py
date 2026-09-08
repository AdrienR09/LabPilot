"""Move stored workflows off the source copies loading one used to make.

Loading a template used to write a timestamped copy of its `.py` into the
installed package directory — `core/workflow_library/omniscan_1788705781.py`
— and point the stored workflow at that copy. Changing one parameter then
rewrote the assignment inside that copy through an AST span edit. So a
configuration change produced a new source file, a workflow could not be
reconfigured on a non-editable install, and reading a workflow's settings
meant parsing Python.

Phase 3 replaced that: an instance is a row (a script path, a parameters
dict, a bindings dict) and loading a template no longer copies anything.
But rows created *before* that still point into `workflow_library/`, and
those copies are the only thing keeping `workflow/capabilities.py` alive —
they import it. This is the migration that lets both go.

For each such workflow: work out which template the copy was made from
(the filename is `<template>_<epoch>.py`), point the row at that template,
and lift the copy's parameters into the row.

**What survives and what does not.** Bindings, name, history and id are in
the row and are untouched — that is the part that would actually hurt to
redo. Parameters are lifted from the copy if it is still on disk; if the
copy is already gone, the workflow comes back at its template's defaults.
The row's own values always win over the copy's, since a row is the newer
of the two.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from labpilot.core.workflow.instrument_roles import read_workflow_params
from labpilot.core.workflow.presets import load_presets

if TYPE_CHECKING:
    from labpilot.core.workflow.store import WorkflowStore

__all__ = ["LIBRARY_DIR_NAME", "migrate_library_workflows", "template_of_copy"]

#: The package directory the copies were written into.
LIBRARY_DIR_NAME = "workflow_library"

#: `omniscan_1788705781` -> `omniscan`. Nine digits or more, so a template
#: legitimately ending in a small number is not mistaken for a copy.
_TIMESTAMPED = re.compile(r"^(?P<template>.+?)_\d{9,}$")


def template_of_copy(script_path: str | Path) -> str | None:
    """The template a timestamped copy was made from, or None.

    Returns None for anything that is not a copy — an ordinary template
    path, or a script the user wrote and loaded from their own directory,
    neither of which this migration should touch.
    """
    path = Path(script_path)
    if LIBRARY_DIR_NAME not in path.parts:
        return None
    match = _TIMESTAMPED.match(path.stem)
    return match.group("template") if match else None


def migrate_library_workflows(store: WorkflowStore, templates_dir: Path) -> list[str]:
    """Repoint every workflow that still references a source copy.

    Returns the ids it changed. Never raises: a workflow it cannot place —
    a copy of a template that no longer exists under any name — is left
    exactly as it is and reported, because a broken row the user can still
    see and fix is better than one silently rewritten to run something
    else.
    """
    presets = load_presets()
    migrated: list[str] = []

    for summary in store.list_all():
        try:
            graph = store.load(summary.id)
        except Exception as e:
            print(f"⚠️  Could not read workflow {summary.id} to migrate it: {e}")
            continue

        script_path = graph.metadata.get("script_path")
        if not script_path:
            continue
        template = template_of_copy(script_path)
        if template is None:
            continue

        # A copy may name what is now a preset rather than a module — the
        # four scanners that became presets of omniscan. Follow it to the
        # script that will actually run, and take the preset's parameters
        # as the base the copy's own values sit on top of.
        preset = presets.get(template)
        script_name = preset.template if preset else template
        target = templates_dir / f"{script_name}.py"
        if not target.exists():
            print(
                f"⚠️  Workflow {summary.id} ({graph.name!r}) was copied from "
                f"{template!r}, which no longer exists — left pointing at "
                f"{script_path}. Load a current template and rebind it."
            )
            continue

        # The copy's parameters, if it is still there to read. A row's own
        # values are newer and win.
        from_copy: dict[str, Any] = {}
        copy_path = Path(script_path)
        if copy_path.exists():
            declared = read_workflow_params(target.read_text())
            from_copy = {
                name: value
                for name, value in read_workflow_params(copy_path.read_text()).items()
                if name in declared
            }

        graph.metadata["script_path"] = str(target)
        graph.metadata["template_name"] = template
        graph.metadata["params"] = {
            **(preset.params if preset else {}),
            **from_copy,
            **(graph.metadata.get("params") or {}),
        }
        try:
            store.save(graph, f"Migrated off the {template!r} source copy")
        except Exception as e:
            print(f"⚠️  Could not save migrated workflow {summary.id}: {e}")
            continue
        migrated.append(summary.id)

    if migrated:
        print(f"✅ Migrated {len(migrated)} workflow(s) off their source copies")
    return migrated
