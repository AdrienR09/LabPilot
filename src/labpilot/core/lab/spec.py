"""`InstrumentSpec` — what an instrument *is*, independent of any process.

The persistent half of the spec/handle split. A spec is the answer to
"which instruments does this lab have": an id, which adapter class to
build, how to reach the hardware, and which settings to apply once it
answers. Nothing in it depends on a running process, so it is exactly what
belongs in a config file and nothing else does.

That boundary is the fix for a real bug. `custom_settings` used to hold
whatever anyone had last written to the device, because
`write_instrument_settings` stored every write and then saved the whole
instrument set to disk — so a console loop stepping a stage rewrote the
config JSON once per point, and the position the scan happened to stop at
became that stage's startup setting, replayed on the next connect. The
`persist` flag stopped the writing; this class stops the *representing*.
`status`, `error` and `last_connected` are not fields here, so a runtime
fact has nowhere to be persisted even by accident.

Frozen, so a spec is shared freely and changed by replacement
(`spec.with_defaults(...)`), which is what makes "did the config change?"
answerable by comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["InstrumentSpec"]


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """One instrument as configured: adapter, address, startup settings."""

    id: str
    adapter_key: str
    name: str = ""
    connection: Mapping[str, Any] = field(default_factory=dict)
    defaults: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        # Copy the mappings the caller passed: a frozen record that shares a
        # dict with its caller is only frozen by convention, and these come
        # straight off a JSON payload or another spec.
        object.__setattr__(self, "connection", dict(self.connection or {}))
        object.__setattr__(self, "defaults", dict(self.defaults or {}))
        if not self.name:
            object.__setattr__(self, "name", self.adapter_key)

    def with_defaults(self, values: Mapping[str, Any]) -> InstrumentSpec:
        """This spec with `values` merged into its startup settings."""
        return replace(self, defaults={**self.defaults, **values})

    def with_connection(self, values: Mapping[str, Any]) -> InstrumentSpec:
        """This spec pointed at different hardware."""
        return replace(self, connection=dict(values))

    # --- Persistence ------------------------------------------------------
    #
    # The on-disk key names predate this class (they were `DeviceConfig`'s),
    # and instrument-set files people already have use them. Reading and
    # writing them keeps every saved config loadable; what changed is what
    # is *absent* — see the module docstring.

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "adapter_type": self.adapter_key,
            "connection_params": dict(self.connection),
            "custom_settings": dict(self.defaults),
            "is_enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InstrumentSpec:
        """Build a spec from a saved entry or an uploaded config.

        Tolerant on purpose: it accepts either spelling of each field, and
        ignores keys that describe a *run* rather than a configuration
        (`status`, `last_connected`) — which is how a file saved by the
        version that conflated the two still loads, minus the confusion.
        """
        adapter_key = data.get("adapter_key") or data.get("adapter_type")
        if not adapter_key:
            raise ValueError(f"Instrument entry names no adapter: {dict(data)!r}")
        name = data.get("name") or ""
        return cls(
            id=str(data.get("id") or name or adapter_key),
            adapter_key=str(adapter_key),
            name=str(name),
            connection=data.get("connection") or data.get("connection_params") or {},
            defaults=data.get("defaults") or data.get("custom_settings") or {},
            enabled=bool(data.get("enabled", data.get("is_enabled", True))),
        )
