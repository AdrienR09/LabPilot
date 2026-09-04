"""Invariants every instrument adapter must satisfy.

These are contract tests, not behaviour tests: they assert that what an
adapter *advertises* matches what it can actually *do*, across the whole
registry at once. Both invariants below were silently violated before this
file existed — the write-dispatch one by eight camera adapters, seven of
which declared an `exposure` control the GUI rendered and `write()` could
never apply.

They are deliberately cheap (no hardware, no connections — only schema
inspection and `getattr`) so they can gate every commit.
"""

from __future__ import annotations

import pytest

from instruments import (
    DISCOVERY_FAILURES,
    INSTRUMENT_CATALOG,
    adapter_registry,
    available_catalog,
)
from instruments.generic_params import validate_write_dispatch

# Registered on purpose without a catalogue row: a generic escape hatch that
# wraps *any* pymeasure Instrument, so it needs an `instrument_class=` argument
# and cannot be meaningfully picked from a catalogue browser.
_UNCATALOGUED_BY_DESIGN = {"pymeasure_generic"}


def _instantiable_adapters() -> list[tuple[str, object]]:
    """Every adapter that can be constructed with no arguments — i.e. mocks,
    fixtures, and any real driver whose connection parameters all default.

    Constructing an adapter does not touch hardware (`__init__` only stores
    connection parameters; `connect()` is what opens the device), so this is
    safe to do for the whole registry.
    """
    out = []
    for key, cls in sorted(adapter_registry.list().items()):
        try:
            out.append((key, cls()))
        except Exception:
            # Needs a resource=/serial_number=/instrument_class= argument.
            continue
    return out


ADAPTERS = _instantiable_adapters()


def test_some_adapters_are_instantiable():
    """Guards the guard: if construction broke wholesale, the parametrised
    test below would vacuously pass with an empty list."""
    assert len(ADAPTERS) > 50, f"only {len(ADAPTERS)} adapters constructible"


@pytest.mark.parametrize("key,adapter", ADAPTERS, ids=[k for k, _ in ADAPTERS])
def test_every_settable_key_has_a_working_write_path(key, adapter):
    """`AdapterBase.write({k: v})` dispatches to a `set_<k>()` coroutine by
    naming convention. A schema key with no matching setter is a control the
    UI renders and every write raises `NotImplementedError` on."""
    missing = validate_write_dispatch(adapter)
    assert not missing, (
        f"{key} declares settable {missing} with no set_<key>() method "
        f"and no write() override — either implement them or remove the keys "
        f"from schema.settable"
    )


def test_registered_adapters_are_catalogued():
    """The catalogue is what the Devices tab browses. An adapter missing from
    it is registered but unreachable through the UI."""
    registered = set(adapter_registry.list())
    catalogued = {m.adapter_key for m in INSTRUMENT_CATALOG}
    orphans = registered - catalogued - _UNCATALOGUED_BY_DESIGN
    assert not orphans, f"registered but not in INSTRUMENT_CATALOG: {sorted(orphans)}"


def test_offered_catalog_entries_can_be_created():
    """Whatever the catalogue offers must be creatable. `INSTRUMENT_CATALOG`
    itself is a static table that can name a driver whose vendor SDK is absent
    or broken on this machine; `available_catalog()` is the filtered view the
    API serves, and it must never advertise an adapter that would raise
    `UnknownAdapterError` on create."""
    registered = set(adapter_registry.list())
    offered = {m.adapter_key for m in available_catalog()}
    assert offered <= registered
    assert not offered - registered


def test_no_unexpected_adapter_discovery_failures():
    """A missing optional backend is fine. Anything else — a broken SDK
    install, a missing runtime library, an architecture mismatch — used to be
    swallowed by a substring match on the exception message and is now
    recorded."""
    errors = [f for f in DISCOVERY_FAILURES if f.kind == "error"]
    assert not errors, "adapter modules failed to import: " + "; ".join(
        f"{f.module}: {f.error}" for f in errors
    )
