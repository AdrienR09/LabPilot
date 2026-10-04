"""Ready-made instrument sets, and probing a whole rig at once.

Setting up a lab PC otherwise means the Devices dialog once per
instrument: pick the adapter out of 314, name it, choose a connection
method, type an address. Every one of those is a chance to pick
`andor_sdk3` when the camera is SDK2, or to end up with an instrument id
nothing in a workflow binds to.

The tests that matter most here are the ones that would catch a template
rotting: that every adapter it names is real, that it loads back as
specs, and that `--all` survives an instrument whose adapter cannot even
be constructed — which is the normal state of a rig before its drivers
are installed, and which used to abort the whole run on the first one.
"""

from __future__ import annotations

import argparse
import json

import pytest

from labpilot.core.config.instrument_sets import (
    InstrumentSetError,
    InstrumentSetPersistence,
)
from labpilot.core.config.rig_templates import (
    TODO,
    install,
    templates,
    unresolved,
)
from labpilot.core.probe import CANNOT_TELL, OK, probe_rig
from labpilot.instruments import adapter_registry


@pytest.fixture
def store(tmp_path) -> InstrumentSetPersistence:
    return InstrumentSetPersistence(tmp_path)


# --- The templates themselves -----------------------------------------------


def test_some_templates_are_shipped():
    assert {template.key for template in templates()} >= {
        "mock_rig", "nv_confocal", "spad_imaging"
    }


@pytest.mark.parametrize("template", templates(), ids=lambda t: t.key)
def test_every_adapter_a_template_names_is_real(template):
    """The check that catches a template rotting: an adapter key renamed
    in `instruments/` leaves the template naming something that no longer
    exists, and the failure would otherwise be a GUI offering an
    instrument that cannot be created."""
    registered = adapter_registry.list()
    unknown = [key for key in template.adapter_keys if key not in registered]
    assert unknown == [], f"{template.key} names adapters that do not exist"


@pytest.mark.parametrize("template", templates(), ids=lambda t: t.key)
def test_every_template_describes_itself(template):
    assert template.description
    assert template.devices


@pytest.mark.parametrize("template", templates(), ids=lambda t: t.key)
def test_every_instrument_has_a_distinct_id(template):
    """Ids are what workflows bind to, so a duplicate silently loses an
    instrument when the set is loaded."""
    ids = [device["id"] for device in template.devices]
    assert len(ids) == len(set(ids))


def test_the_mock_rig_needs_nothing_filled_in():
    """It is the template someone runs before touching hardware, so it has
    to work as shipped."""
    mock = next(t for t in templates() if t.key == "mock_rig")
    assert mock.unresolved() == []
    assert mock.todo == []
    assert mock.missing_adapters() == []


def test_the_hardware_templates_say_what_they_still_need():
    """A blank address reads as "not needed". `TODO-ip-address` does not,
    which is the difference between a config that looks finished and one
    that says what is missing."""
    rig = next(t for t in templates() if t.key == "nv_confocal")
    placeholders = rig.unresolved()
    assert placeholders
    assert all(value.startswith(TODO) for _, _, value in placeholders)
    assert any(name == "mw" for name, _, _ in placeholders)


def test_a_note_is_only_for_what_a_placeholder_cannot_express():
    """A numeric port has no way to look unset, so it is written down
    instead of inferred."""
    spad = next(t for t in templates() if t.key == "spad_imaging")
    assert any("spad.port" in note for note in spad.todo)


def test_unresolved_ignores_values_that_are_set():
    devices = [
        {"id": "a", "connection_params": {"host": "192.168.1.1", "port": 5025}},
        {"id": "b", "connection_params": {"host": f"{TODO}address"}},
    ]
    assert list(unresolved(devices)) == [("b", "host", f"{TODO}address")]


# --- Installing one ---------------------------------------------------------


def test_installing_writes_a_config_and_activates_it(store):
    path, template = install("mock_rig", store=store)
    assert path.exists()
    assert store.get_active_name() == "mock_rig"
    assert len(store.load("mock_rig")) == len(template.devices)


def test_the_installed_config_is_an_ordinary_one(store):
    """Which is the whole design: a template is a saved instrument set, so
    from here on it is editable in the Devices tab and switchable like any
    other."""
    install("mock_rig", store=store)
    specs = store.load("mock_rig")
    assert {spec.id for spec in specs} >= {"stage", "apd", "counter"}
    assert all(spec.adapter_key for spec in specs)
    assert "mock_rig" in store.list_configs()


def test_it_can_be_installed_under_another_name(store):
    install("mock_rig", name="bench_2", store=store)
    assert store.exists("bench_2")
    assert store.get_active_name() == "bench_2"


def test_it_can_be_installed_without_activating(store):
    install("mock_rig", store=store, activate=False)
    assert store.exists("mock_rig")
    assert store.get_active_name() is None


def test_an_existing_config_is_not_silently_replaced(store):
    """A config with real addresses typed into it is exactly what nobody
    wants overwritten by a template full of placeholders."""
    install("mock_rig", store=store)
    with pytest.raises(InstrumentSetError, match="already exists"):
        install("mock_rig", store=store)


def test_overwriting_is_possible_when_asked(store):
    install("mock_rig", store=store)
    install("mock_rig", store=store, overwrite=True)
    assert store.exists("mock_rig")


def test_an_unknown_template_lists_the_real_ones(store):
    with pytest.raises(InstrumentSetError, match="mock_rig"):
        install("no_such_rig", store=store)


def test_a_template_is_valid_json_with_the_keys_the_loader_reads():
    for template in templates():
        payload = json.loads(template.path.read_text())
        assert set(payload) >= {"name", "description", "devices"}


# --- Probing a whole rig ----------------------------------------------------


def _args(**overrides) -> argparse.Namespace:
    defaults = {
        "adapter_key": None, "resource": None, "param": None,
        "offline": False, "no_read": False, "json": False,
        "all": True, "config": "",
    }
    return argparse.Namespace(**{**defaults, **overrides})


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway `~/.labpilot`, so a test never writes into the real one."""
    monkeypatch.setenv("LABPILOT_HOME", str(tmp_path))
    return tmp_path


def test_probing_a_whole_mock_rig_agrees_throughout(home, capsys):
    install("mock_rig")
    assert probe_rig(_args()) == OK
    out = capsys.readouterr().out
    assert "6 instruments" in out
    assert "every instrument agrees" in out


def test_the_summary_names_every_instrument(home, capsys):
    install("mock_rig")
    probe_rig(_args())
    out = capsys.readouterr().out
    for identifier in ("stage", "apd", "spectrometer", "mw", "pulser", "counter"):
        assert identifier in out


def test_an_instrument_that_cannot_be_built_does_not_stop_the_others(home, capsys):
    """The normal state of a rig before its drivers are installed — and
    the bug this command was written to avoid, which it had: an adapter
    whose constructor rejected a *value* rather than an argument name
    aborted the whole run on the first one."""
    install("nv_confocal")
    assert probe_rig(_args()) == CANNOT_TELL
    out = capsys.readouterr().out
    # All eight reported, none of them having been reached.
    assert "8 instruments" in out
    assert out.count("unreachable") >= 8
    assert "Nothing was written and nothing moved" in out


def test_a_named_config_can_be_probed_instead_of_the_active_one(home, capsys):
    install("mock_rig", name="bench_a")
    install("nv_confocal", name="bench_b", activate=True)
    assert probe_rig(_args(config="bench_a")) == OK
    assert "bench_a" in capsys.readouterr().out


def test_with_no_instrument_set_it_says_how_to_make_one(home, capsys):
    assert probe_rig(_args()) == CANNOT_TELL
    assert "rig-init" in capsys.readouterr().out


def test_an_empty_instrument_set_is_reported_as_such(home, capsys):
    InstrumentSetPersistence().save("empty", [])
    assert probe_rig(_args(config="empty")) == CANNOT_TELL
    assert "no instruments in it" in capsys.readouterr().out


def test_a_missing_config_is_reported_not_raised(home, capsys):
    assert probe_rig(_args(config="not_a_config")) == CANNOT_TELL
    assert "not_a_config" in capsys.readouterr().out


def test_offline_probes_the_whole_rig_without_connecting(home, capsys):
    """Useful on a laptop: it reviews what every adapter in a rig claims
    before any of it is wired."""
    install("nv_confocal")
    assert probe_rig(_args(offline=True)) == OK
    out = capsys.readouterr().out
    assert out.count("nothing was connected") == 8


def test_an_offline_run_never_claims_the_hardware_agrees(home, capsys):
    """It connected to nothing. Reporting agreement would be the exact
    false reassurance this whole command exists to avoid."""
    install("nv_confocal")
    probe_rig(_args(offline=True))
    out = capsys.readouterr().out
    assert "agrees with its declared schema" not in out
    assert "declared" in out
    assert "Drop --offline" in out


def test_saved_connection_parameters_reach_each_probe(home, capsys):
    """The config is the one place an address is written down, rather than
    being retyped per probe."""
    install("nv_confocal")
    probe_rig(_args(offline=True))
    assert "TODO-ip-address" in capsys.readouterr().out


def test_json_output_covers_every_instrument(home, capsys):
    install("mock_rig")
    probe_rig(_args(json=True))
    report = json.loads(capsys.readouterr().out)
    assert report["config"] == "mock_rig"
    assert len(report["instruments"]) == 6
    assert all(entry["exit"] == OK for entry in report["instruments"].values())


# --- Binding the backend ----------------------------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "::", ""])
def test_a_public_bind_is_announced(host, capsys):
    """There is no authentication anywhere in the API: anything that can
    reach it can move a stage, open a shutter and start a pulse sequence.
    That is acceptable on localhost and is not a thing to discover
    afterwards on a lab network."""
    from labpilot.core.cli import _warn_if_exposed

    _warn_if_exposed(host)
    assert "no authentication" in capsys.readouterr().err


def test_a_local_bind_says_nothing(capsys):
    from labpilot.core.cli import _warn_if_exposed

    _warn_if_exposed("127.0.0.1")
    assert capsys.readouterr().err == ""


def test_start_binds_this_machine_only_by_default(capsys):
    """`labpilot start` used to default to 0.0.0.0, so every headless
    backend was exposed without anyone choosing it. `labpilot app` always
    defaulted to localhost; the two now agree."""
    import sys

    from labpilot.core.cli import main

    argv, sys.argv = sys.argv, ["labpilot", "start", "--help"]
    try:
        with pytest.raises(SystemExit):
            main()
    finally:
        sys.argv = argv

    help_text = capsys.readouterr().out
    assert "default: 127.0.0.1" in help_text
    assert "0.0.0.0" not in help_text.split("--load")[0]
