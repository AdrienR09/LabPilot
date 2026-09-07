"""Read-only library of ready-made, general-purpose workflow templates.

Each script here references the instruments it needs by *role* — e.g.
`session.get("xy_actuator")` rather than a literal instrument id — and
declares those roles via a `REQUIRED_INSTRUMENTS` module constant (see
`core/workflow/instrument_roles.py`). Loading a template
(`POST /api/workflows/templates/{name}/load`) copies it into
`core/workflow_library/` as a new, independent workflow with every role
unbound; binding a role to a real connected instrument (via the
flowchart, or `PUT /api/workflows/{id}/bindings/{role}` directly) is what
actually makes it runnable, and can be changed again later without
touching the script text (see `RunManager._apply_instrument_bindings`,
which resolves roles via `Session.register_alias` at execution time).

These files are never imported/executed by this package itself — they're
read as plain text (for `REQUIRED_INSTRUMENTS`/docstring extraction) and
copied verbatim on load, exactly like any other workflow script.
"""

from __future__ import annotations

__all__: list[str] = []
