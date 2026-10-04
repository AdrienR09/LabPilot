"""Ready-made instrument sets for a whole rig.

Setting up a lab PC otherwise means the Devices dialog eight times: pick
the adapter out of 314, name it, choose a connection method, type an
address. Every one of those is a chance to pick `andor_sdk3` when the
camera is SDK2, or to end up with an instrument id nothing in a workflow
binds to.

A template is just a saved instrument set shipped with the package, so
installing one writes the same `~/.labpilot/config/instruments/<name>.cfg`
the Devices dialog would have produced — and from then on it is an
ordinary config, editable in the GUI and switchable like any other.

Addresses nobody can know in advance are written as `TODO-...` rather
than left blank or guessed. A blank looks configured; `TODO-ip-address`
does not, `labpilot probe --all` reports it as unreachable, and
`unresolved()` below lists them so the CLI can say what is still needed
before anything is plugged in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from labpilot.core.config.instrument_sets import (
    InstrumentSetError,
    InstrumentSetPersistence,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "TODO",
    "RigTemplate",
    "install",
    "templates",
    "unresolved",
]

#: Marks a connection parameter only the lab can fill in. A prefix rather
#: than an empty string: an empty `host` reads as "not needed", and the
#: difference matters when the probe reports what it could not reach.
TODO = "TODO-"

_DIRECTORY = Path(__file__).parent / "rigs"


class RigTemplate:
    """One shipped instrument set, before it is installed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.key = path.stem
        payload = json.loads(path.read_text())
        self.description: str = str(payload.get("description", ""))
        self.devices: list[dict[str, Any]] = list(payload.get("devices", []))
        self.todo: list[str] = [str(note) for note in payload.get("todo", [])]
        """Things to find out that a `TODO-` string cannot express — a
        port number, which terminal a signal is on. A numeric placeholder
        has no way to look unset, so those are written down here instead
        of being inferred."""

    @property
    def adapter_keys(self) -> list[str]:
        return [str(device.get("adapter_type", "")) for device in self.devices]

    def unresolved(self) -> list[tuple[str, str, str]]:
        """`(instrument id, parameter, placeholder)` for every TODO left.

        What the CLI prints so the list of things to find out — an IP
        address, a card model, a folder — is visible before anyone walks
        to the lab, rather than one failed connection at a time.
        """
        return list(unresolved(self.devices))

    def missing_adapters(self) -> list[str]:
        """Adapter keys that did not register on this machine.

        Almost always a vendor SDK that is not installed, which is worth
        saying at install time: the template is still written, because the
        config is a declaration and the driver can arrive later.
        """
        from labpilot.instruments import adapter_registry

        registered = adapter_registry.list()
        return [key for key in self.adapter_keys if key not in registered]


def templates() -> list[RigTemplate]:
    """Every shipped template, by name."""
    return [RigTemplate(path) for path in sorted(_DIRECTORY.glob("*.cfg"))]


def unresolved(devices: list[dict[str, Any]]) -> Iterator[tuple[str, str, str]]:
    """Every `TODO-` placeholder in a device list."""
    for device in devices:
        identifier = str(device.get("id", "?"))
        for key, value in (device.get("connection_params") or {}).items():
            if isinstance(value, str) and value.startswith(TODO):
                yield (identifier, str(key), value)


def install(
    key: str,
    *,
    name: str = "",
    store: InstrumentSetPersistence | None = None,
    activate: bool = True,
    overwrite: bool = False,
) -> tuple[Path, RigTemplate]:
    """Write a template out as a named instrument set.

    Refuses to overwrite an existing config unless asked: a config that
    has been edited in the GUI, or had real addresses typed into it, is
    exactly what someone would not want replaced by a template full of
    placeholders.
    """
    available = {template.key: template for template in templates()}
    if key not in available:
        raise InstrumentSetError(
            f"No rig template named {key!r}. Available: "
            f"{', '.join(sorted(available)) or 'none'}"
        )
    template = available[key]
    store = store or InstrumentSetPersistence()
    target = name or template.key

    if store.exists(target) and not overwrite:
        raise InstrumentSetError(
            f"An instrument config named {target!r} already exists. Pass a "
            f"different --as name, or --overwrite to replace it."
        )

    from labpilot.core.lab.spec import InstrumentSpec

    path = store.save(
        target, [InstrumentSpec.from_dict(device) for device in template.devices]
    )
    if activate:
        store.set_active_name(target)
    return path, template
