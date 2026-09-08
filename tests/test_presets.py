"""A preset must name a real template and real parameters.

Four templates — a 1-D sweep, a 2-D raster, a confocal map and a
hyperspectral cube — were separate modules with their own hand-written
loops, differing from `omniscan` and from each other mainly in their
result-key names and their default ranges. They existed *because* a result
could not describe itself, so each variant needed its own `RESULT_UI` and
therefore its own file. With `Run` owning the loop and `Dataset` describing
the result, what was left of each was a parameters dict.

That is what they are now (`workflow_templates/presets.toml`), which means
two new ways to be wrong, both silent: naming a template that does not
exist, and setting a parameter the template does not declare — the second
being silent because a load drops unknown parameters on purpose, so the
preset would appear to work and simply scan the wrong thing.

`tests/test_template_smoke.py` runs each preset end to end; these check the
declarations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.core.workflow.instrument_roles import (
    read_required_instruments,
    read_workflow_params,
)
from labpilot.core.workflow.presets import load_presets, presets_path

TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "labpilot" / "core" / "workflow_templates"
)
PRESETS = load_presets()


def test_the_presets_file_is_where_the_package_says_it_is():
    assert presets_path().exists()
    assert PRESETS, "no presets declared at all"


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_a_preset_names_a_template_that_exists(name):
    assert (TEMPLATE_DIR / f"{PRESETS[name].template}.py").exists()


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_a_preset_only_sets_parameters_its_template_declares(name):
    """A load keeps only parameters the template still declares, so a
    misspelled one is dropped without a word and the preset quietly runs
    the template's defaults instead."""
    preset = PRESETS[name]
    declared = read_workflow_params(
        (TEMPLATE_DIR / f"{preset.template}.py").read_text()
    )
    unknown = sorted(set(preset.params) - set(declared))
    assert not unknown, f"{name} sets {unknown}, which {preset.template} does not declare"


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_a_preset_says_what_it_is_for(name):
    """It replaces a module docstring that the template library showed."""
    assert len(PRESETS[name].description) > 40


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_a_preset_scans_axes_its_ranges_define(name):
    """SCAN_AXES picks from AXIS_RANGES; an axis in one and not the other
    is either a scan that does nothing or a range nothing reads."""
    params = PRESETS[name].params
    if "SCAN_AXES" not in params or "AXIS_RANGES" not in params:
        pytest.skip("not a grid preset")
    assert set(params["SCAN_AXES"]) <= set(params["AXIS_RANGES"])


def test_a_preset_does_not_shadow_a_template():
    """Both are loadable by name through the same route, so a collision
    would make which one you get depend on lookup order."""
    templates = {
        p.stem for p in TEMPLATE_DIR.glob("*.py") if not p.stem.startswith("_")
    }
    assert not (templates & set(PRESETS))


def test_the_four_consolidated_templates_are_still_reachable():
    """By the same names they always had — this replaced them, it did not
    remove them."""
    assert {
        "generic_1d_scan", "generic_2d_scan", "confocal_scanner",
        "hyperspectral_imaging",
    } <= set(PRESETS)


def test_every_preset_inherits_its_template_s_bindable_roles():
    """A preset supplies parameters, not instruments — what you bind is
    whatever the script it runs asks for."""
    for name, preset in PRESETS.items():
        roles = read_required_instruments(
            (TEMPLATE_DIR / f"{preset.template}.py").read_text()
        )
        assert roles, f"{name}: base template {preset.template} declares no roles"
