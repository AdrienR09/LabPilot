"""Config-driven instrument instantiation.

The "general instrument structure" already exists: `AdapterBase` (in
`_base.py`) is the common concrete base every adapter subclasses, and
`core.device.protocols.Readable`/`Movable`/`Triggerable` are PEP 544
Protocols describing what an adapter can do structurally. Both already use
Python's metaclass machinery (`ABCMeta` / `_ProtocolMeta`) — there's no need
for a bespoke metaclass on top of that; what was actually missing was a
uniform way to go from a config entry to a live instance, since the 257
registered adapter classes don't share one constructor signature (some take
`resource=`, some `port=`, the pymeasure-generic ones take
`instrument_class=` + `resource=`, etc).

This module is that missing piece: `create_adapter()` introspects the target
adapter class's `__init__` and fills in only the parameters it actually
declares, so one call site works uniformly across every backend (mock,
pymeasure, pylablib).
"""

from __future__ import annotations

import inspect
from typing import Any

from labpilot.instruments._base import AdapterBase, adapter_registry


class UnknownAdapterError(KeyError):
    """Raised when a config references an adapter_type that isn't registered."""


def create_adapter(
    adapter_type: str,
    connection_params: dict[str, Any] | None = None,
    name: str | None = None,
    **overrides: Any,
) -> AdapterBase:
    """Instantiate a registered adapter by key, from a plain config shape.

    Args:
        adapter_type: Key in `adapter_registry` (e.g. "keithley_2400",
            "mock_spectrometer", "pymeasure_agilent34410_a").
        connection_params: Dict of connection args (port, resource, address,
            baud_rate, ...). Only keys matching the adapter's `__init__`
            parameters are used — extras are ignored, not errors, since the
            same config can be reused across adapters that need different
            subsets (e.g. `resource` vs `port`).
        name: Device name. Passed through if the adapter accepts a `name`
            parameter; otherwise ignored (the adapter picks its own default).
        **overrides: Passed through as-is on top of `connection_params`,
            taking precedence — for adapter-specific kwargs not worth
            standardizing (e.g. `channel` on the Lakeshore adapter).

    Returns:
        A connected-but-not-yet-`connect()`-ed adapter instance.

    Raises:
        UnknownAdapterError: If `adapter_type` isn't in `adapter_registry`.
        TypeError: If the adapter's required parameters aren't satisfiable
            from `connection_params`/`overrides` (surfaces the adapter's own
            error message — this factory doesn't second-guess it).

    Example:
        >>> create_adapter("keithley_2400", {"resource": "GPIB::24"})
        >>> create_adapter("mock_spectrometer", {}, name="spec1")
        >>> create_adapter(
        ...     "pymeasure_generic",
        ...     {"resource": "GPIB::8"},
        ...     instrument_class="pymeasure.instruments.srs.SR830",
        ... )
    """
    try:
        adapter_cls = adapter_registry.get(adapter_type)
    except KeyError as e:
        raise UnknownAdapterError(
            f"No adapter registered under {adapter_type!r}. "
            f"See adapter_registry.list() for what's available."
        ) from e

    connection_params = connection_params or {}
    sig = inspect.signature(adapter_cls.__init__)
    accepted = set(sig.parameters) - {"self"}

    kwargs: dict[str, Any] = {
        k: v for k, v in connection_params.items() if k in accepted
    }
    if name is not None and "name" in accepted:
        kwargs["name"] = name
    kwargs.update(overrides)

    return adapter_cls(**kwargs)


def create_adapter_from_config(config: "labpilot.core.config.DeviceConfig") -> AdapterBase:  # noqa: F821
    """Instantiate an adapter from a `core.config.DeviceConfig`.

    Thin convenience wrapper around `create_adapter()` for the config shape
    already used by `ConfigPersistence`/`lab_config.toml`'s `[[devices]]`.
    """
    return create_adapter(
        adapter_type=config.adapter_type,
        connection_params=config.connection_params,
        name=config.name,
        **(config.custom_settings or {}),
    )
