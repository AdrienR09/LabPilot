"""Per-instance copies of workflow templates.

Loading a template (POST /api/workflows/templates/{name}/load) writes a
timestamped copy of its source here and points the new workflow's
`script_path` at it, so each loaded workflow owns an independent, editable
script. Instance files are generated at runtime and are not tracked in git
(see .gitignore).

This mechanism is scheduled to be replaced: a workflow's tunable parameters
currently live *in* its copied source, edited by an AST span-rewrite, which
is why bug fixes to a template never reach instances already loaded from it
and why copies accumulate here indefinitely. The intended replacement is a
template module plus a params record, with nothing rewriting Python source.
"""

from __future__ import annotations

__all__: list[str] = []
