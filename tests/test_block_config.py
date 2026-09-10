"""The block-config files, and the bug that made new blocks invisible.

`ui_blocks.toml` and `workflow_blocks.toml` are copied to
`~/.labpilot/config/` on first run so they can be edited. They used to be
copied *and then never consulted again*, so every block added afterwards
was invisible to anyone who had run the app before — no error, no
warning, just a control that never appeared. A pulse editor was added,
rewritten, and rewritten again without any existing installation ever
being able to show it.

So the packaged file is the base and the user's is an override layer
merged on top. What these pin is that merge, and the invariant the bug
actually broke: every control a shipped template needs must be selectable
from the shipped config.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

import labpilot.core.workflow_templates as templates
from labpilot.core.workflow.instrument_roles import read_workflow_params

DESKTOP = Path("src/labpilot/ui/desktop")
TEMPLATES = Path(templates.__path__[0])


def _block_config():
    """`block_config.py` by path.

    It lives under `ui/desktop/` but imports nothing from Qt — and the
    merge rule is the part that has to be right, so it is tested here
    rather than in an offscreen harness.
    """
    spec = importlib.util.spec_from_file_location(
        "block_config", DESKTOP / "block_config.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bc = _block_config()


def packaged(name: str) -> dict:
    with open(DESKTOP / "config" / name, "rb") as f:
        return tomllib.load(f)


def controls(config: dict) -> list[str]:
    return [c["type"] for c in config.get("controls", ())]


# --- The merge --------------------------------------------------------------


def test_a_block_added_by_an_upgrade_reaches_an_existing_installation():
    """The bug, stated directly. A user file written before `pulse_editor`
    existed must not hide it."""
    shipped = {"controls": [{"type": "axes_control"}, {"type": "pulse_editor"}]}
    stale = {"controls": [{"type": "axes_control"}]}

    assert controls(bc.merge_blocks(shipped, stale)) == [
        "axes_control", "pulse_editor",
    ]


def test_an_edited_block_keeps_the_edit():
    """The reason the file is copied out at all: it is meant to be
    changed, and an upgrade must not undo that."""
    shipped = {"controls": [{"type": "sweep_control", "requires": ["A", "B"]}]}
    edited = {"controls": [{"type": "sweep_control", "requires": ["A"]}]}

    merged = bc.merge_blocks(shipped, edited)
    assert merged["controls"][0]["requires"] == ["A"]


def test_an_edit_overrides_one_key_without_dropping_the_others():
    shipped = {"controls": [{"type": "poll_rate", "default_ms": 200, "area": "right"}]}
    edited = {"controls": [{"type": "poll_rate", "default_ms": 50}]}

    merged = bc.merge_blocks(shipped, edited)["controls"][0]
    assert merged == {"type": "poll_rate", "default_ms": 50, "area": "right"}


def test_a_block_the_user_invented_is_kept():
    shipped = {"controls": [{"type": "axes_control"}]}
    extended = {"controls": [{"type": "my_control"}]}

    assert controls(bc.merge_blocks(shipped, extended)) == ["axes_control", "my_control"]


def test_packaged_order_is_kept_so_a_new_block_lands_where_it_was_meant_to():
    """The list is the order the docks appear in, so appending everything
    would put an upgrade's new control at the bottom regardless."""
    shipped = {"controls": [{"type": "a"}, {"type": "b"}, {"type": "c"}]}
    stale = {"controls": [{"type": "c"}, {"type": "a"}]}

    assert controls(bc.merge_blocks(shipped, stale)) == ["a", "b", "c"]


def test_sections_merge_one_at_a_time():
    """`ui_blocks.toml` is sections of blocks, so a user who edited the
    source window must still get a capability section added later."""
    shipped = {
        "source": {"SOURCE": {"blocks": [{"type": "move_control"}]}},
        "capability": {"pulser": {"blocks": [{"type": "actions"}]}},
    }
    stale = {"source": {"SOURCE": {"blocks": [{"type": "move_control", "area": "left"}]}}}

    merged = bc.merge_blocks(shipped, stale)
    assert merged["source"]["SOURCE"]["blocks"][0]["area"] == "left"
    assert "pulser" in merged["capability"]


def test_removal_is_explicit_because_merging_cannot_express_it():
    """A line deleted from the user's file looks exactly like a line they
    never wrote, so dropping a block is something they say rather than
    something they omit."""
    shipped = {"controls": [{"type": "axes_control"}, {"type": "sweep_control"}]}
    trimmed = {"disabled": ["sweep_control"]}

    merged = bc.merge_blocks(shipped, trimmed)
    assert controls(merged) == ["axes_control"]
    assert "disabled" not in merged


def test_disabling_reaches_into_every_section():
    shipped = {
        "source": {"SOURCE": {"blocks": [{"type": "actions"}, {"type": "poll_rate"}]}},
        "capability": {"pulser": {"blocks": [{"type": "actions"}]}},
    }
    merged = bc.merge_blocks(shipped, {"disabled": ["actions"]})

    assert [b["type"] for b in merged["source"]["SOURCE"]["blocks"]] == ["poll_rate"]
    assert merged["capability"]["pulser"]["blocks"] == []


def test_an_untouched_file_gives_exactly_what_is_shipped():
    for name in ("ui_blocks.toml", "workflow_blocks.toml"):
        shipped = packaged(name)
        assert bc.merge_blocks(shipped, shipped) == shipped


def test_a_first_run_writes_the_file_out_to_be_edited(tmp_path):
    """It is copied so it can be found and changed, not so it can shadow
    the package."""
    config = bc.load_block_config(
        "workflow_blocks.toml", packaged=DESKTOP / "config", user=tmp_path
    )
    assert (tmp_path / "workflow_blocks.toml").exists()
    assert controls(config) == controls(packaged("workflow_blocks.toml"))


def test_a_stale_user_file_is_not_rewritten(tmp_path):
    """Merging is enough; overwriting someone's config on load is not this
    function's business."""
    stale = tmp_path / "workflow_blocks.toml"
    stale.write_text('[[controls]]\ntype = "axes_control"\nrequires = ["X"]\n')
    before = stale.read_text()

    config = bc.load_block_config(
        "workflow_blocks.toml", packaged=DESKTOP / "config", user=tmp_path
    )
    assert stale.read_text() == before
    assert "pulse_editor" in controls(config)
    assert config["controls"][0]["requires"] == ["X"]


# --- Every shipped control is reachable -------------------------------------


def declared(template: str) -> set[str]:
    return set(read_workflow_params((TEMPLATES / f"{template}.py").read_text()))


@pytest.mark.parametrize(
    ("control", "template"),
    [
        ("axes_control", "omniscan"),
        ("sweep_control", "odmr_sweep"),
        ("pulse_editor", "pulse_sequence_editor"),
        ("pulse_control", "pulsed_measurement"),
    ],
)
def test_each_shipped_control_is_selected_by_the_template_it_is_for(control, template):
    """The invariant the stale-config bug broke, and the one renaming a
    template's parameters breaks next: a control whose `requires` no
    template satisfies is a dock nobody will ever see, and nothing
    anywhere raises."""
    block = next(
        c for c in packaged("workflow_blocks.toml")["controls"] if c["type"] == control
    )
    missing = set(block.get("requires", ())) - declared(template)
    assert not missing, f"{template}.py declares none of {sorted(missing)}"


def test_no_shipped_control_is_unreachable():
    """Every control in the file is satisfied by *some* shipped template.
    One that is not is either a typo or a dock for a template that no
    longer exists."""
    every = [
        declared(path.stem) for path in TEMPLATES.glob("*.py")
        if path.stem not in ("__init__", "_common")
    ]
    for block in packaged("workflow_blocks.toml")["controls"]:
        requires = set(block.get("requires", ()))
        assert any(requires <= params for params in every), block["type"]


def test_the_editor_and_the_measurement_do_not_share_a_dock():
    """They are different jobs — one binds no instruments and writes a
    file, the other binds the rig and plays one — so a parameter rename
    that made either dock apply to both would be a mistake worth
    catching."""
    blocks = {
        c["type"]: set(c.get("requires", ()))
        for c in packaged("workflow_blocks.toml")["controls"]
    }
    assert not blocks["pulse_editor"] <= declared("pulsed_measurement")
    assert not blocks["pulse_control"] <= declared("pulse_sequence_editor")
