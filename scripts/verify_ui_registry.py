#!/usr/bin/env python3
"""Verify the UI component registry, and that the config files name real blocks.

`ui_blocks.toml` says a block's `type` "must match a key in the registry",
and a workflow's `RESULT_UI["type"]` had the same requirement against a
second registry. Neither claim was checked anywhere: a typo in either
produced a blank panel at window-open time, with no error, on a machine
with hardware attached.

Run it:

    QT_QPA_PLATFORM=offscreen python scripts/verify_ui_registry.py

Not a pytest test, deliberately. `tests/` is the headless, Qt-free suite,
and importing these modules into it pulls pymodaq_gui's Qt stack in
alongside the rest of the collection — which this project already found
crashes the whole run with a metaclass conflict (it passes in isolation and
fails when collected with the other files; see tests/test_result_types.py's
docstring, where the same conclusion was reached and the same escape taken).
This is that escape: the offscreen-harness convention the other desktop-side
checks already use.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "src" / "labpilot" / "ui" / "desktop"
UI_BLOCKS = DESKTOP / "config" / "ui_blocks.toml"
WORKFLOW_BLOCKS = DESKTOP / "config" / "workflow_blocks.toml"

sys.path.insert(0, str(ROOT / "src"))

failures: list[str] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✅ {description}")
    else:
        print(f"  ❌ {description}{f' — {detail}' if detail else ''}")
        failures.append(description)


print("=" * 78)
print("LABPILOT UI REGISTRY VERIFICATION")
print("=" * 78)

print("\n1. Importing the component packages (this is what registers them)...")
import labpilot.ui.desktop.components  # noqa: E402  — importing is what registers
import labpilot.ui.desktop.components.workflow_result  # noqa: E402,F401
from labpilot.ui.desktop.components.base import component_for, components_in  # noqa: E402

instrument_blocks = components_in("instrument")
result_views = components_in("result")
print(
    f"   {len(instrument_blocks)} instrument blocks, "
    f"{len(components_in('workflow'))} workflow controls, "
    f"{len(result_views)} result views"
)

print("\n2. One registry, two contexts")
check("instrument blocks registered", bool(instrument_blocks))
check("result views registered", bool(result_views))
check(
    "the context is part of the key",
    component_for("instrument", "ndscan") is None
    and component_for("result", "viewer") is None,
    "a result type resolved as an instrument block, or the reverse",
)
check("an unknown type resolves to None", component_for("instrument", "nope") is None)

print("\n3. Every block in ui_blocks.toml names a real component")
config = tomllib.loads(UI_BLOCKS.read_text())
seen = 0
for kind, by_dimensionality in config.items():
    for dimensionality, section in by_dimensionality.items():
        for block in section.get("blocks", []):
            seen += 1
            check(
                f"[{kind}.{dimensionality!r}] {block['type']}",
                block["type"] in instrument_blocks,
                f"no component registers {block['type']!r}; known: "
                f"{', '.join(sorted(instrument_blocks))}",
            )
check("the packaged ui_blocks.toml declares blocks at all", seen > 0)

print("\n4. Every control in workflow_blocks.toml names a real component")
workflow_controls = components_in("workflow")
controls = tomllib.loads(WORKFLOW_BLOCKS.read_text()).get("controls", [])
for block in controls:
    check(
        f"[[controls]] {block.get('type')}",
        block.get("type") in workflow_controls,
        f"no component registers {block.get('type')!r}; known: "
        f"{', '.join(sorted(workflow_controls))}",
    )
    check(
        f"  {block.get('type')} says what a workflow must declare",
        bool(block.get("requires")),
        "`requires` is empty, so this control would apply to every workflow",
    )
check("the packaged workflow_blocks.toml declares controls at all", bool(controls))

print("\n5. Every result view answers the two calls it is dispatched through")
for name, adapter in sorted(result_views.items()):
    check(
        f"{name} declares build() and update()",
        callable(getattr(adapter, "build", None))
        and callable(getattr(adapter, "update", None)),
    )

print("\n" + "=" * 78)
if failures:
    print(f"FAILED — {len(failures)} check(s):")
    for failure in failures:
        print(f"  • {failure}")
    sys.exit(1)
print(
    f"All checks passed ({seen} instrument blocks, {len(controls)} workflow "
    f"controls, {len(result_views)} result views)."
)
