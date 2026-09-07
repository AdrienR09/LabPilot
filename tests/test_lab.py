"""The spec/handle split: what a config file may and may not remember.

`DashboardManager.instruments` held one untyped dict per instrument, mixing
the adapter, its address and its saved settings together with its status,
its last error and whether it was connected — and `_save_active_config()`
wrote that dict to disk from the `finally` of nearly every operation. Two
consequences, both tested here:

- a console loop stepping a stage rewrote the instrument-set file once per
  point, and the position it stopped at became that stage's startup
  setting, replayed on the next connect;
- connecting an instrument rewrote the file for no reason at all.

The `persist` flag stopped the first from being *written*. `InstrumentSpec`
stops it from being *representable*: a spec has no field for a runtime
fact, so there is nowhere for one to be saved even by mistake.
"""

from __future__ import annotations

import json

import pytest

from labpilot.core.config.instrument_sets import InstrumentSetPersistence
from labpilot.core.lab import InstrumentSpec, Lab, UnknownInstrumentError
from labpilot.core.session import Session
from labpilot.instruments.factory import UnknownAdapterError

STAGE = InstrumentSpec(
    id="stage", adapter_key="mock_basic_actuator_nd", name="Sample stage"
)
APD = InstrumentSpec(id="apd", adapter_key="mock_basic_detector_0d", name="APD")
LASER = InstrumentSpec(id="laser", adapter_key="mock_basic_source", name="Pump laser")


@pytest.fixture
def lab(tmp_path):
    lab = Lab(store=InstrumentSetPersistence(tmp_path), session=Session())
    lab.active_config = "test"
    lab.add(STAGE)
    lab.add(APD)
    lab.add(LASER)
    lab.save()
    return lab


def _saved(lab: Lab) -> dict:
    return json.loads((lab.store.dir / f"{lab.active_config}.cfg").read_text())


# --- What a config file holds ---------------------------------------------


def test_a_saved_config_holds_no_runtime_state(lab):
    """It used to carry `status` and `last_connected` on every entry —
    facts about a process, saved because they shared a record with the
    configuration. Nothing ever read them back."""
    for entry in _saved(lab)["devices"]:
        assert "status" not in entry
        assert "last_connected" not in entry
        assert set(entry) == {
            "id", "name", "adapter_type", "connection_params",
            "custom_settings", "is_enabled",
        }


def test_a_config_file_written_by_the_old_version_still_loads(lab, tmp_path):
    """The keys on disk predate the split, and people have these files."""
    legacy = {
        "name": "legacy",
        "devices": [{
            "id": "stage",
            "name": "Sample stage",
            "adapter_type": "mock_basic_actuator_nd",
            "connection_params": {},
            "custom_settings": {"x": 1.0},
            "last_connected": 1_700_000_000.0,   # dropped
            "status": "error",                    # dropped
            "is_enabled": True,
        }],
    }
    (lab.store.dir / "legacy.cfg").write_text(json.dumps(legacy))

    specs = lab.store.load("legacy")
    assert [s.id for s in specs] == ["stage"]
    assert specs[0].defaults == {"x": 1.0}
    assert not hasattr(specs[0], "status")


async def test_connecting_does_not_rewrite_the_config(lab):
    """Connecting is not a configuration change. It used to save anyway,
    from the `finally` of connect_instrument."""
    before = (lab.store.dir / "test.cfg").read_bytes()
    await lab.connect("stage")
    await lab.disconnect("stage")
    assert (lab.store.dir / "test.cfg").read_bytes() == before


async def test_a_runtime_write_leaves_the_spec_alone(lab):
    """Where the pollution bug lived: every scan point took this path."""
    await lab.connect("stage")
    handle = lab["stage"]

    await handle.write({"x": 3.0})

    assert handle.spec.defaults == {}
    assert _saved(lab)["devices"][0]["custom_settings"] == {}


async def test_a_saved_setting_is_applied_on_the_next_connect(lab):
    """The other half: a real configuration change must survive a
    reconnect, which is what `custom_settings` was there for.

    A source's output level rather than a stage position, because a
    position is the very thing that should not be configuration — and
    because reading one back immediately would measure how fast the stage
    travels rather than whether the setting was applied.
    """
    lab.update_spec("laser", lab["laser"].spec.with_defaults({"output": 2.5}))
    lab.save()

    fresh = Lab(store=lab.store, session=Session())
    await fresh.load("test")
    await fresh.connect("laser")

    # The mock reports its output with a little noise, as a real one would.
    assert (await fresh["laser"].read())["output"] == pytest.approx(2.5, abs=0.01)


# --- What a handle is ------------------------------------------------------


def test_an_instrument_is_one_object_not_a_lookup(lab):
    """`session.get()` built a new wrapper per call, so nothing could hold
    on to an instrument — two callers naming the same id got two objects
    that agreed only by convention."""
    assert lab["stage"] is lab["stage"]
    assert lab["stage"].adapter is lab.get("stage").adapter


async def test_a_workflow_gets_the_same_instrument_object_too(lab):
    """`session.get()` built a fresh wrapper per call, so `is` was never
    true and a wrapper could hold no state of its own."""
    await lab.connect("stage")
    assert lab.session.get("stage") is lab.session.get("stage")
    assert lab.session.get("stage") is lab["stage"].device


def test_the_handle_knows_what_it_is_doing(lab):
    handle = lab["stage"]
    assert (handle.status, handle.error, handle.connected) == ("idle", None, False)


async def test_a_failed_connect_is_recorded_on_the_handle_not_raised_away(lab, monkeypatch):
    handle = lab["stage"]

    async def boom():
        raise ConnectionError("no such port")

    monkeypatch.setattr(handle.adapter, "connect", boom)
    with pytest.raises(ConnectionError):
        await lab.connect("stage")

    assert handle.status == "error"
    assert handle.error == "no such port"


async def test_a_connected_instrument_is_resolvable_from_a_workflow(lab):
    await lab.connect("apd")
    assert lab.session.has("apd")

    lab.bind("detector", "apd")
    assert lab.session.get("detector").schema.kind == "detector"

    await lab.disconnect("apd")
    assert not lab.session.has("apd")


def test_binding_a_role_to_a_typo_fails_at_the_bind(lab):
    """Rather than at the first read inside a running workflow."""
    with pytest.raises(UnknownInstrumentError):
        lab.bind("detector", "apd_2")


# --- Mistakes --------------------------------------------------------------


def test_an_unknown_id_names_the_near_misses(lab):
    """A registered id carries a suffix (`apd_2`, not `apd`), so asking for
    the adapter's own name is the usual mistake."""
    with pytest.raises(UnknownInstrumentError) as excinfo:
        lab.get("stag")
    assert "'stage'" in str(excinfo.value)


def test_an_adapter_that_will_not_build_leaves_the_lab_untouched(lab):
    """Re-pointing an instrument at a bad address must not cost you the
    instrument you had."""
    before = lab["stage"]
    with pytest.raises(UnknownAdapterError):
        lab.add(InstrumentSpec(id="stage", adapter_key="no_such_adapter"))
    assert lab["stage"] is before


def test_a_spec_does_not_share_its_caller_s_dict():
    """A frozen record that aliases a mutable dict is frozen by convention
    only — and these come straight off a JSON payload."""
    defaults = {"x": 1.0}
    spec = InstrumentSpec(id="s", adapter_key="k", defaults=defaults)
    defaults["x"] = 99.0
    assert spec.defaults == {"x": 1.0}


def test_changing_a_spec_makes_a_new_one():
    spec = InstrumentSpec(id="s", adapter_key="k")
    assert spec.with_defaults({"x": 1.0}) is not spec
    assert spec.defaults == {}
