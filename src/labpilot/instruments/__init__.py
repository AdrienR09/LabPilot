"""Adapter registry with auto-discovery.

On import this registers every adapter shipped under `labpilot/instruments/`
and then every adapter advertised by an installed third-party package
through the `labpilot.adapters` entry-point group (see `discover_plugins`),
so a driver does not have to live in this tree to be usable. Missing
optional dependencies (pylablib, pymeasure) are recorded and skipped.

Usage:
    >>> from labpilot.instruments import adapter_registry
    >>> adapter_registry.list()  # All available adapters
    >>> adapter_registry.search(tags=["camera"])  # Filter by tag
    >>> AdapterClass = adapter_registry.get("andor_sdk2")
"""

from __future__ import annotations

import importlib
import importlib.metadata
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.catalog import INSTRUMENT_CATALOG, InstrumentMetadata

if TYPE_CHECKING:
    from labpilot.core.device.schema import DeviceSchema

__all__ = [
    "DISCOVERY_FAILURES",
    "ENTRY_POINT_GROUP",
    "INSTRUMENT_CATALOG",
    "AdapterBase",
    "DiscoveryFailure",
    "InstrumentMetadata",
    "adapter_registry",
    "available_catalog",
    "discover_adapters",
    "discover_plugins",
]

ENTRY_POINT_GROUP = "labpilot.adapters"
"""Entry-point group third-party driver packages advertise themselves in —
see `discover_plugins`."""

# Vendor packages whose absence is a normal, expected optional-install state
# rather than a bug worth reporting.
_OPTIONAL_BACKENDS = frozenset({"pylablib", "pymeasure"})


@dataclass(frozen=True)
class DiscoveryFailure:
    """One adapter module that did not import during `discover_adapters()`.

    Recorded rather than only printed, so the failure is inspectable — a
    catalogue entry with no registered adapter used to be indistinguishable
    from a typo, because the cause was a stderr line nobody kept.
    """

    module: str
    error: str
    kind: Literal["missing_dependency", "error"]


# Populated by discover_adapters(); see available_catalog() for the main
# consumer, and tests/test_adapter_contracts.py for the invariant.
DISCOVERY_FAILURES: list[DiscoveryFailure] = []


def available_catalog() -> list[InstrumentMetadata]:
    """`INSTRUMENT_CATALOG` restricted to entries whose adapter actually
    registered on this machine.

    The catalogue is a static table; whether a driver imports depends on the
    installed vendor SDKs. A camera whose vendor C extension fails to load
    (a broken install, a missing runtime, the wrong architecture) leaves its
    catalogue row intact but its adapter unregistered — and the Devices tab
    would then offer an instrument that raises `UnknownAdapterError` the
    moment you try to create it. Serving this list instead degrades to
    "not offered" rather than "offered and broken".
    """
    registered = adapter_registry.list()
    return [m for m in INSTRUMENT_CATALOG if m.adapter_key in registered]


def discover_adapters() -> None:
    """Auto-discover and import all adapter modules.

    Walks the instruments package tree and imports all submodules.
    Each adapter module should call adapter_registry.register() at the bottom
    to make itself discoverable.

    Missing dependencies are silently skipped (e.g., if pylablib not installed,
    all pylablib adapters are skipped).

    Rules:
    - Adapter modules must be under instruments/
    - Each module calls register(key, Class) at import time
    - Import errors are logged but don't crash the discovery process
    - Modules starting with "_" are skipped (private/base modules)

    Example adapter module structure:
        instruments/Keithley/source.py:
            '''Keithley SMU adapters.'''

            try:
                from pymeasure.instruments.keithley import Keithley2400
            except ImportError:
                # pymeasure not installed - skip this adapter
                pass
            else:
                from labpilot.instruments._base import AdapterBase, adapter_registry

                class Keithley2400Adapter(AdapterBase):
                    ...

                adapter_registry.register("keithley_2400", Keithley2400Adapter)
    """
    # Get the adapters package path
    adapters_path = Path(__file__).parent

    # Walk all subpackages
    for module_info in pkgutil.walk_packages(
        [str(adapters_path)], prefix="labpilot.instruments."
    ):
        module_name = module_info.name

        # Skip private modules (start with _)
        if module_name.split(".")[-1].startswith("_"):
            continue

        # Try to import the module
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            # An optional vendor SDK simply isn't installed. Match on the
            # missing module's own name, not a substring of the message: the
            # old `"pylablib" in str(e)` test also swallowed *broken* pylablib
            # installs, e.g. a camera whose C extension fails with
            # "could not load C extensions: symbol not found". Those are real
            # failures and are recorded below instead.
            root = (e.name or "").split(".")[0]
            if root in _OPTIONAL_BACKENDS:
                DISCOVERY_FAILURES.append(
                    DiscoveryFailure(module_name, str(e), "missing_dependency")
                )
            else:
                DISCOVERY_FAILURES.append(DiscoveryFailure(module_name, str(e), "error"))
                print(
                    f"Warning: Failed to import adapter module {module_name}: {e}",
                    file=sys.stderr,
                )
        except Exception as e:
            # Present but unusable — a broken SDK install, a missing runtime
            # library, an architecture mismatch. Recorded so `available_catalog()`
            # can stop advertising the adapter and so the cause survives.
            DISCOVERY_FAILURES.append(DiscoveryFailure(module_name, str(e), "error"))
            print(
                f"Warning: Error loading adapter {module_name}: {e}",
                file=sys.stderr,
            )


def discover_plugins(group: str = ENTRY_POINT_GROUP) -> None:
    """Import every installed package that advertises LabPilot adapters.

    A third-party driver package declares, in its own pyproject.toml:

        [project.entry-points."labpilot.adapters"]
        acme = "acme_labpilot:register"

    The target may be a module — imported for its side effects, the same
    contract as an in-tree adapter module — or a callable, which is called
    with no arguments so it can register adapters and catalogue entries
    explicitly. Both are supported because the first is the least
    ceremony and the second is what a package with more than one module
    actually wants.

    Until now every driver had to live inside `labpilot/instruments/`,
    which makes an exhaustive instrument library one maintainer's backlog
    rather than something the people with the hardware can contribute.
    Discovery failures are recorded in `DISCOVERY_FAILURES` exactly like
    in-tree ones: a broken plugin must not take the application down with
    it, but it must not vanish silently either.
    """
    try:
        entry_points = importlib.metadata.entry_points(group=group)
    except Exception as e:  # pragma: no cover - importlib.metadata edge cases
        DISCOVERY_FAILURES.append(DiscoveryFailure(group, str(e), "error"))
        return

    for entry_point in entry_points:
        try:
            loaded = entry_point.load()
            if callable(loaded):
                loaded()
        except Exception as e:
            DISCOVERY_FAILURES.append(
                DiscoveryFailure(f"{group}:{entry_point.name}", str(e), "error")
            )
            print(
                f"Warning: Failed to load adapter plugin {entry_point.name!r} "
                f"({entry_point.value}): {e}",
                file=sys.stderr,
            )


# Auto-discover on package import: adapters shipped in this package first,
# then any installed plugins. Plugins go last so a plugin can see (and
# subclass) the built-in adapters, and so a key collision reports the
# plugin as the duplicate rather than the built-in.
discover_adapters()
discover_plugins()
