"""Instrument role declarations for role-based workflow scripts.

A template script (see `core/workflow_templates/`) references the
instruments it needs by *role* rather than by a literal instrument id —
`session.get("xy_actuator")` instead of `session.get("scanner_2d_1")` —
and declares what each role requires via a module-level constant:

    REQUIRED_INSTRUMENTS = {
        "xy_actuator": {"kind": "motor", "dimensionality": "ND"},
        "detector":    {"kind": "detector", "dimensionality": "0D"},
    }

Read back here with `ast.literal_eval` on the parsed AST — the same
safety property as `workflow_window.py`'s `UI_BLOCKS` reader on the Qt
desktop side: this never executes the script just to discover its role
requirements. The actual role -> real-instrument-id binding is separate,
mutable state stored in `WorkflowGraph.metadata["instrument_bindings"]`
(see `core/api/workflow_templates.py`), resolved at run time via
`Session.register_alias` (`core/workflow/engine.py`) — the script text
itself never changes when a binding is made or changed.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable  # noqa: TC003 -- used in a runtime signature
from pathlib import Path
from typing import Optional

from labpilot.core.workflow.result_types import ResultUIError, parse_result_ui_literal

__all__ = [
    "GENERIC",
    "read_required_instruments",
    "read_required_instruments_from_file",
    "read_template_description",
    "read_result_ui",
    "read_result_ui_from_file",
    "read_capabilities",
    "read_workflow_params",
    "role_refusal",
]

#: The kind that means "does not fit the other four", and therefore fits
#: any role — see `role_refusal`.
GENERIC = "generic"


def role_refusal(
    role: str,
    requirement: dict,
    instrument_id: str,
    kind: str,
    dimensionality: str,
    capabilities: Iterable[str] = (),
) -> str | None:
    """Why this instrument may not fill this role, or None if it may.

    ## A capability decides; a kind only guesses

    `"capability"` is checked first and binds nothing else, because it is
    the one requirement that is exactly knowable: a device either declares
    `gated_counter` or it does not, and if it does not, `configure_gates`
    is a `AttributeError` waiting for the run to reach it.

    That is why a role which names a capability should not also name a
    kind. A photon counter is a 0D detector, and whether its adapter
    spells that `kind="counter"` or `kind="detector"` is a taxonomy
    choice with no bearing on whether it can gate: the mock rig's counter
    says `counter`, a Time Tagger says `counter` at 1D, an R-Series FPGA
    card says `generic`, and an APD that grew the mixin says `detector`.
    Requiring one of those spellings refuses three devices that do the
    job in order to refuse nothing that does not.

    ## A generic instrument fits every role

    `kind` sorts a device into one of five buckets, and `generic` is the
    bucket for devices that are not one thing: an NI DAQ card is
    simultaneously an actuator (its analog outputs), a detector (its
    analog inputs), a counter (its counters) and a hardware-timed
    scanner, depending only on which terminal a workflow asks for. A
    lock-in is a source and a detector at once. Refusing to bind those to
    a `detector` role is the taxonomy asserting something it cannot know,
    and it is the reason a card that does the job is missing from the
    list.

    So `generic` satisfies any *kind* requirement, and what it can
    actually do is settled where that is knowable: by its capabilities
    above, and by its schema when the script asks for a parameter it does
    not have. Both checks are exact and need no taxonomy.

    The kind check stays for every other kind, where it is still useful:
    a `motor` bound to a `detector` role is nearly always a mis-click,
    and the error is cheaper than the failed run.
    """
    wanted_capability = requirement.get("capability")
    if wanted_capability and wanted_capability not in set(capabilities or ()):
        have = ", ".join(sorted(capabilities or ())) or "none"
        return (
            f"Role {role!r} needs a {wanted_capability!r} instrument, but "
            f"{instrument_id!r} declares {have}"
        )

    if kind == GENERIC:
        return None

    wanted = requirement.get("kind")
    if wanted and kind != wanted:
        return (
            f"Role {role!r} needs kind={wanted!r}, but {instrument_id!r} "
            f"is {kind!r}"
        )

    wanted_dim = requirement.get("dimensionality")
    if wanted_dim and dimensionality != wanted_dim:
        return (
            f"Role {role!r} needs dimensionality={wanted_dim!r}, but "
            f"{instrument_id!r} is {dimensionality!r}"
        )
    return None

# Constant names read_workflow_params never treats as a tunable workflow
# parameter: REQUIRED_INSTRUMENTS/RESULT_UI have their own special-purpose
# readers above, and every role-id constant (e.g. `SCANNER_ID = "xy_actuator"`)
# follows the "<ROLE>_ID" naming convention across every template in
# core/workflow_templates/ — its value is an internal session.get() key,
# never a user-tunable setting.
_RESERVED_WORKFLOW_PARAM_NAMES = {"REQUIRED_INSTRUMENTS", "RESULT_UI", "CAPABILITIES"}


def read_required_instruments(script_text: str) -> dict[str, dict]:
    """{role_name: {"kind": ..., "dimensionality": ...}, ...} declared by
    a script's `REQUIRED_INSTRUMENTS` constant, or {} if it has none (a
    plain, non-role-based script — every literal-id workflow already in
    `workflow_library/` falls in this bucket and is unaffected)."""
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return {}

    result: dict[str, dict] = {}
    for stmt in tree.body:
        is_plain = (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "REQUIRED_INSTRUMENTS"
        )
        is_annotated = (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "REQUIRED_INSTRUMENTS"
            and stmt.value is not None
        )
        if is_plain or is_annotated:
            try:
                result = ast.literal_eval(stmt.value)
            except Exception:
                pass
    return result


def read_required_instruments_from_file(script_path: str | Path) -> dict[str, dict]:
    path = Path(script_path)
    if not path.exists():
        return {}
    return read_required_instruments(path.read_text())


def read_result_ui(script_text: str) -> dict:
    """{"type": "image2d"|"spectrum", "value_key": ..., ...} declared by a
    script's `RESULT_UI` constant, or {} if it has none. Describes how
    `workflow_window.py` (the native desktop window) should render this
    workflow's live/last result — same never-execute-the-script safety
    property as `read_required_instruments` above.

    `RESULT_UI` may be a plain dict literal (the historical form, read
    exactly as before) or a call to one of `core.workflow.result_types`'s
    typed dataclasses (`ImageResult(...)` etc.) — see
    `parse_result_ui_literal`. A malformed dataclass call (`ResultUIError`)
    is deliberately NOT swallowed by the `except Exception: pass` below —
    that's meant to tolerate a RESULT_UI that isn't a static literal at all
    (rare, treated as "no RESULT_UI", same as before dataclass support
    existed), not to hide a genuine authoring mistake."""
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return {}

    result: dict = {}
    for stmt in tree.body:
        is_plain = (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "RESULT_UI"
        )
        is_annotated = (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "RESULT_UI"
            and stmt.value is not None
        )
        if is_plain or is_annotated:
            try:
                result = parse_result_ui_literal(stmt.value)
            except ResultUIError:
                raise
            except Exception:
                pass
    return result


def read_result_ui_from_file(script_path: str | Path) -> dict:
    path = Path(script_path)
    if not path.exists():
        return {}
    return read_result_ui(path.read_text())


def _read_top_level_constant(script_text: str, name: str) -> Optional[object]:
    """The literal value of a top-level `name = ...` (or annotated)
    constant, or None if the script declares no such constant — the same
    AST-walk `read_required_instruments`/`read_result_ui` each duplicate
    for their own constant, generalized so `read_capabilities` below
    doesn't need a third copy."""
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return None

    result: Optional[object] = None
    for stmt in tree.body:
        is_plain = (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == name
        )
        is_annotated = (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == name
            and stmt.value is not None
        )
        if is_plain or is_annotated:
            try:
                result = ast.literal_eval(stmt.value)
            except Exception:
                pass
    return result


def read_capabilities(script_text: str) -> dict[str, dict]:
    """{capability_name: {...params}, ...} declared by a script's
    `CAPABILITIES` constant (`WORKFLOW_COMPOSITION.md` §3) — e.g.
    `{"scan": {}, "optimizer": {"around": "actuator"}, "save": {}}`.

    Backward-compatible fallback for every existing template (none of
    which declare `CAPABILITIES` yet): if the script has no `CAPABILITIES`
    constant at all, an `"optimizer"` capability is inferred from
    `RESULT_UI["crosshair"]` when present — exactly reproducing today's
    behavior (`server.py`'s `_resolve_optimize_targets` used to check
    `RESULT_UI.get("crosshair")` directly; that check now lives here, once,
    behind the same public name every OTHER capability is looked up by) so
    no existing template needs to add a `CAPABILITIES` constant just to
    keep its optimizer working."""
    declared = _read_top_level_constant(script_text, "CAPABILITIES")
    if isinstance(declared, dict):
        return declared

    inferred: dict[str, dict] = {}
    result_ui = read_result_ui(script_text)
    crosshair = result_ui.get("crosshair") if isinstance(result_ui, dict) else None
    if crosshair:
        inferred["optimizer"] = {"around": crosshair.get("role")}
    return inferred


def read_workflow_params(script_text: str) -> dict[str, object]:
    """{name: value} for every top-level UPPERCASE constant this script
    declares that isn't REQUIRED_INSTRUMENTS/RESULT_UI or a role-id
    constant (see `_RESERVED_WORKFLOW_PARAM_NAMES` above) — this
    workflow's own tunable settings (e.g. omniscan.py's
    AXIS_RANGES/SCAN_AXES/SETTLE_TOLERANCE), as distinct from an
    *instrument's* settings (which come from that instrument's own
    DeviceSchema, a completely separate surface — see
    SettingsTreeComponent on the Qt desktop side). Only literal-eval-able
    values are included (numbers, strings, bools, lists/dicts of those);
    an expression referencing another name, a function call, etc. is
    silently skipped rather than guessed at. Same never-execute-the-script
    safety property as `read_required_instruments`/`read_result_ui`.

    Dict order matches source order, so a caller rendering these as a form
    gets the same top-to-bottom order the template author wrote them in.
    """
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return {}

    result: dict[str, object] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            name, value_node = stmt.targets[0].id, stmt.value
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.value is not None
        ):
            name, value_node = stmt.target.id, stmt.value
        else:
            continue

        if not name.isupper() or name in _RESERVED_WORKFLOW_PARAM_NAMES or name.endswith("_ID"):
            continue
        try:
            result[name] = ast.literal_eval(value_node)
        except Exception:
            continue
    return result


def read_template_description(script_text: str) -> str:
    """First line of a template's own module docstring, for display in
    the template library listing — never executes the script."""
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return ""
    doc = ast.get_docstring(tree) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""
