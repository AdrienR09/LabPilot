"""Saving a config a second time overwrites the first — on Windows too.

All four config stores write to a `.tmp` file and then move it into place,
which is the right way to avoid a half-written config. Every one of them
made the move with `Path.rename`, and that is where they broke: `rename`
and `replace` are both atomic, but only `replace` overwrites an existing
target on Windows. `Path.rename` maps to MoveFile without
MOVEFILE_REPLACE_EXISTING, so the *second* save of any config raised

    FileExistsError: [WinError 183] Cannot create a file when that file
    already exists: '...\\mock_rig.cfg.tmp' -> '...\\mock_rig.cfg'

and the failure was worse than it looked: the new content stayed stranded
in the `.tmp` file while the old content remained in place, so a config
silently stopped tracking reality. Creating a second instrument was enough
to hit it.

POSIX `rename` already overwrites, so these tests would pass on Linux and
macOS whichever call the code made. The `windows_rename` fixture closes that
gap: it gives `os.rename` the Windows behaviour — refuse an existing target —
and leaves `os.replace` alone, so every test here reproduces the real failure
on any platform. `Path.rename` and `Path.replace` dispatch to exactly those
two functions, which is what makes the substitution faithful.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labpilot.core.config.instrument_sets import InstrumentSetPersistence
from labpilot.core.config.template_params import TemplateParamPersistence
from labpilot.core.config.workflow_sets import WorkflowSetPersistence
from labpilot.core.lab.spec import InstrumentSpec


def _spec(instrument_id: str) -> InstrumentSpec:
    return InstrumentSpec(id=instrument_id, adapter_key="mock_basic")


@pytest.fixture(autouse=True)
def windows_rename(monkeypatch):
    """Make `os.rename` refuse an existing target, as it does on Windows.

    Windows implements it with MoveFile and no MOVEFILE_REPLACE_EXISTING,
    so this is the one behavioural difference that mattered. `os.replace`
    is deliberately left alone — it overwrites on both platforms, and the
    point of each test is that the code reaches for that one.
    """
    real_rename = os.rename

    def refuse_existing(src, dst, **kwargs):
        if os.path.exists(dst):
            raise FileExistsError(
                183, "Cannot create a file when that file already exists", str(src), None, str(dst)
            )
        return real_rename(src, dst, **kwargs)

    monkeypatch.setattr(os, "rename", refuse_existing)


def test_an_instrument_set_can_be_saved_over_itself(tmp_path):
    store = InstrumentSetPersistence(config_dir=tmp_path)
    store.save("mock_rig", [_spec("apd")])
    store.save("mock_rig", [_spec("apd"), _spec("stage")])

    assert [s.id for s in store.load("mock_rig")] == ["apd", "stage"]


def test_the_second_save_leaves_no_temp_file_behind(tmp_path):
    """A stranded `.cfg.tmp` is the fingerprint of the failed move."""
    store = InstrumentSetPersistence(config_dir=tmp_path)
    store.save("mock_rig", [_spec("apd")])
    store.save("mock_rig", [_spec("stage")])

    assert list(store.dir.glob("*.tmp")) == []


def test_a_workflow_set_can_be_saved_over_itself(tmp_path):
    store = WorkflowSetPersistence(config_dir=tmp_path)
    store.save("default", ["first.py"])
    store.save("default", ["first.py", "second.py"])

    assert store.load("default") == ["first.py", "second.py"]


def test_template_params_can_be_saved_over_themselves(tmp_path):
    store = TemplateParamPersistence(config_dir=tmp_path)
    store.save("odmr_sweep", {"SWEEP_POINTS": 21})
    store.save("odmr_sweep", {"SWEEP_POINTS": 51})

    assert store.load("odmr_sweep") == {"SWEEP_POINTS": 51}


def test_the_session_config_can_be_saved_over_itself(tmp_path):
    from labpilot.core.config import ConfigPersistence, DeviceConfig, SessionConfig

    store = ConfigPersistence(config_dir=tmp_path)
    store.session_config_path.parent.mkdir(parents=True, exist_ok=True)

    def device(name: str) -> DeviceConfig:
        return DeviceConfig(name=name, adapter_type="mock_basic", connection_params={})

    store.save_session_config(SessionConfig(devices=[device("apd")]))
    saved = store.save_session_config(
        SessionConfig(devices=[device("apd"), device("stage")])
    )

    written = json.loads(saved.read_text())
    assert [d["name"] for d in written["devices"]] == ["apd", "stage"]
    assert list(saved.parent.glob("*.tmp")) == []


# --- The guard that works on every platform --------------------------------

_CONFIG_MODULES = (
    "core/config/instrument_sets.py",
    "core/config/workflow_sets.py",
    "core/config/template_params.py",
    "core/config/__init__.py",
)


@pytest.mark.parametrize("module", _CONFIG_MODULES)
def test_no_config_store_moves_a_file_with_rename(module):
    source = Path(__file__).resolve().parents[1] / "src" / "labpilot" / module
    if not source.is_file():
        pytest.skip(f"{module} is not in this install")
    offenders = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(source.read_text().splitlines(), start=1)
        if ".rename(" in line and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        f"{module} moves a file with `rename`, which cannot overwrite an existing "
        f"target on Windows — use `replace`: {offenders}"
    )
