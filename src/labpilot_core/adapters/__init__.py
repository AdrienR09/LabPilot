"""Adapter registry with auto-discovery.

Automatically discovers and registers all adapters from labpilot_core.adapters
subpackages on import. Missing optional dependencies (pylablib, pymeasure) are
silently skipped.

Usage:
    >>> from labpilot_core.adapters import adapter_registry
    >>> adapter_registry.list()  # All available adapters
    >>> adapter_registry.search(tags=["camera"])  # Filter by tag
    >>> AdapterClass = adapter_registry.get("andor_sdk2")
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from labpilot_core.adapters._base import AdapterBase, adapter_registry

if TYPE_CHECKING:
    from labpilot_core.device.schema import DeviceSchema

__all__ = ["AdapterBase", "adapter_registry", "discover_adapters"]


def discover_adapters() -> None:
    """Auto-discover and import all adapter modules.

    Walks the labpilot_core.adapters package tree and imports all submodules.
    Each adapter module should call adapter_registry.register() at the bottom
    to make itself discoverable.

    Missing dependencies are silently skipped (e.g., if pylablib not installed,
    all pylablib adapters are skipped).

    Rules:
    - Adapter modules must be under labpilot_core/adapters/
    - Each module calls register(key, Class) at import time
    - Import errors are logged but don't crash the discovery process
    - Modules starting with "_" are skipped (private/base modules)

    Example adapter module structure:
        labpilot_core/adapters/pymeasure/keithley.py:
            '''Keithley SMU adapters.'''

            try:
                from pymeasure.instruments.keithley import Keithley2400
            except ImportError:
                # pymeasure not installed - skip this adapter
                pass
            else:
                from labpilot_core.adapters._base import AdapterBase, adapter_registry

                class Keithley2400Adapter(AdapterBase):
                    ...

                adapter_registry.register("keithley_2400", Keithley2400Adapter)
    """
    # Get the adapters package path
    adapters_path = Path(__file__).parent

    # Walk all subpackages
    for module_info in pkgutil.walk_packages(
        [str(adapters_path)], prefix="labpilot_core.adapters."
    ):
        module_name = module_info.name

        # Skip private modules (start with _)
        if module_name.split(".")[-1].startswith("_"):
            continue

        # Try to import the module
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            # Optional dependency missing - skip silently
            # (e.g., pylablib or pymeasure not installed)
            if "pylablib" in str(e) or "pymeasure" in str(e):
                pass
            else:
                # Unexpected import error - log but continue
                print(
                    f"Warning: Failed to import adapter module {module_name}: {e}",
                    file=sys.stderr,
                )
        except Exception as e:
            # Other error during import - log but continue
            print(
                f"Warning: Error loading adapter {module_name}: {e}",
                file=sys.stderr,
            )


# Auto-discover on package import
discover_adapters()
