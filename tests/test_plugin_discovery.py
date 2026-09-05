"""Third-party adapter packages, discovered through entry points.

Until this existed every driver had to live inside
`labpilot/instruments/`, which makes "an exhaustive instrument library"
one maintainer's backlog rather than something the people who own the
hardware can contribute.

The entry points here are real `importlib.metadata.EntryPoint` objects
pointing at real modules written to a temporary directory, so `load()`
does the actual import — a mock returning a pre-made object would pass
even if the loading contract were wrong.
"""

from __future__ import annotations

import sys
from importlib.metadata import EntryPoint

import pytest

from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments import DISCOVERY_FAILURES, _base, discover_plugins
from labpilot.instruments._base import AdapterBase, AdapterRegistry

GROUP = "labpilot.test.adapters"


@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in list(sys.modules):
        if name.startswith("labpilot_fake_plugin"):
            del sys.modules[name]


@pytest.fixture(autouse=True)
def isolated_failures(monkeypatch):
    """`DISCOVERY_FAILURES` is module state shared with the real import-time
    discovery; leaving test entries in it would break
    `test_adapter_contracts.py`'s "no unexpected failures" invariant."""
    before = list(DISCOVERY_FAILURES)
    yield
    DISCOVERY_FAILURES[:] = before


def _entry_points(monkeypatch, *entries: EntryPoint) -> None:
    import importlib.metadata

    monkeypatch.setattr(
        importlib.metadata, "entry_points",
        lambda group=None: [e for e in entries if group in (None, GROUP)],
    )


_ADAPTER_SOURCE = '''\
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry


class FakePluginAdapter(AdapterBase):
    def __init__(self, resource: str = "") -> None:
        super().__init__()
        self._resource = resource

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(name="fake_plugin", kind="detector",
                            readable={"counts": "float64"})

    def _connect_sync(self) -> None: ...
    def _disconnect_sync(self) -> None: ...
    def _read_sync(self) -> dict:
        return {"counts": 1.0}


def register() -> None:
    adapter_registry.register("fake_plugin_via_callable", FakePluginAdapter)


adapter_registry.register("fake_plugin_via_module", FakePluginAdapter)
'''


def _sandbox_registry(monkeypatch) -> AdapterRegistry:
    """A throwaway registry the plugin module registers into, so a test
    plugin never lands in the real one. The plugin imports
    `adapter_registry` from `_base` at its own import time, which is after
    this patch."""
    registry = AdapterRegistry()
    monkeypatch.setattr(_base, "adapter_registry", registry)
    return registry


def test_a_module_entry_point_registers_on_import(plugin_dir, monkeypatch):
    """The least-ceremony form: point at a module, and importing it is the
    registration — the same contract an in-tree adapter module has."""
    (plugin_dir / "labpilot_fake_plugin_a.py").write_text(_ADAPTER_SOURCE)
    registry = _sandbox_registry(monkeypatch)
    _entry_points(monkeypatch, EntryPoint("a", "labpilot_fake_plugin_a", GROUP))

    discover_plugins(GROUP)

    assert "fake_plugin_via_module" in registry.list()


def test_a_callable_entry_point_is_called(plugin_dir, monkeypatch):
    """What a package with more than one adapter module actually wants: one
    named hook that registers everything explicitly."""
    (plugin_dir / "labpilot_fake_plugin_b.py").write_text(_ADAPTER_SOURCE)
    registry = _sandbox_registry(monkeypatch)
    _entry_points(
        monkeypatch, EntryPoint("b", "labpilot_fake_plugin_b:register", GROUP)
    )

    discover_plugins(GROUP)

    assert "fake_plugin_via_callable" in registry.list()


def test_a_discovered_plugin_adapter_describes_itself_like_any_other(
    plugin_dir, monkeypatch
):
    """A plugin adapter is not a second-class citizen: it shows up in
    `list_with_schemas()`, so the instrument browser and tag search see
    it."""
    (plugin_dir / "labpilot_fake_plugin_c.py").write_text(_ADAPTER_SOURCE)
    registry = _sandbox_registry(monkeypatch)
    _entry_points(monkeypatch, EntryPoint("c", "labpilot_fake_plugin_c", GROUP))

    discover_plugins(GROUP)

    schemas = registry.list_with_schemas()
    assert schemas["fake_plugin_via_module"].readable == {"counts": "float64"}


def test_a_broken_plugin_is_recorded_not_raised(monkeypatch, capsys):
    """A third-party package that fails to import must not take the
    application down — but it must not vanish either, which is why it lands
    in `DISCOVERY_FAILURES` like an in-tree failure does."""
    _entry_points(
        monkeypatch, EntryPoint("broken", "labpilot_no_such_module", GROUP)
    )

    discover_plugins(GROUP)

    failures = [f for f in DISCOVERY_FAILURES if "broken" in f.module]
    assert len(failures) == 1
    assert failures[0].kind == "error"
    assert "broken" in capsys.readouterr().err


def test_a_plugin_reusing_a_registered_key_is_reported_as_the_duplicate():
    """Plugins load after the built-ins, so a key collision names the
    plugin. Asserted on the registry directly — the message is what a
    plugin author sees."""
    registry = AdapterRegistry()

    class _Adapter(AdapterBase):
        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(name="taken", kind="detector")

        def _connect_sync(self) -> None: ...
        def _disconnect_sync(self) -> None: ...
        def _read_sync(self) -> dict:
            return {}

    registry.register("taken", _Adapter)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("taken", _Adapter)
