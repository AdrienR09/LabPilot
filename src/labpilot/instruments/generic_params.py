"""Does this adapter's `write()` actually reach hardware for every key it
advertises as settable?

`AdapterBase.write()`'s `set_<key>` dispatch (instruments/_base.py) is a
naming convention, not something the type system can check, so a schema
can declare a settable parameter that has no setter behind it. The UI
draws the control regardless. `validate_write_dispatch` is the check
`tests/test_adapter_contracts.py` runs over every registered adapter; it
found the Keithley 2600/6221/2400, SR830/SR860 and PM100 adapters each
advertising settable keys with no matching `set_<key>` at all, and seven
of the eight hand-written camera adapters unable to set their own
exposure.

This module used to also carry `GENERIC_PARAMS`: a per-`InstrumentType`
table declaring that every 1-D actuator has a "position", every detector
an "integration_time_ms", and so on, with helpers to separate those
"generic" parameters from an adapter's manufacturer-specific ones. It had
no callers, and what it was reaching for is now expressed on the
parameters themselves, where it is derived from the adapter's own schema
rather than asserted alongside it: `role` says whether a parameter is a
position or a setting, and `tags` marks the cross-vendor ones — so
"the integration time" is `schema.find(settable=True,
tags={INTEGRATION_TIME})` on any device, with no type table to keep in
sync.
"""

from __future__ import annotations

from labpilot.instruments._base import AdapterBase

__all__ = ["validate_write_dispatch"]


def validate_write_dispatch(adapter: AdapterBase) -> list[str]:
    """Settable schema keys this *instance* has no working way to set.

    Needs a live instance rather than just a schema, since only the
    instance can be asked whether `write()` will actually dispatch: an
    adapter that overrides `write()` wholesale (the pymeasure and pylablib
    generics do) handles its own settings and is exempt.

    Returns [] when clean.
    """
    if type(adapter).write is not AdapterBase.write:
        return []
    return [
        key for key in adapter.schema.settable
        if getattr(adapter, f"set_{key}", None) is None
    ]
