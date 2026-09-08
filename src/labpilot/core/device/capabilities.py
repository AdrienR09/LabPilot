"""What a device can do beyond read and write.

`DeviceSchema.kind` answers "what sort of thing is this?" with one of five
strings, and that is the right question for a stage or a photodiode. It is
the wrong question for a device whose interesting behaviour is a contract
of its own: a hardware-timed scanner and a pulse sequencer are both
`kind="generic"`, which says only that neither fits the other four.

The existing answer was one `isinstance` in `kinds._build`:

    if kind == "generic":
        return Scanner(adapter) if isinstance(adapter, HardwareScanMixin) \\
               else GenericInstrument(adapter)

That line works, and it is why `HardwareScanMixin` is the one typed-device
mechanism in this repo that earned its keep. But it does not compose — a
second contract means a second `isinstance` and an ordering question
between them, a device implementing both cannot be expressed at all, and
the fact is invisible outside the process: `ui_blocks.toml` selects blocks
on `(kind, dimensionality)`, so every `kind="generic"` device lands in one
shared bucket regardless of what it actually implements.

A capability is a string a mixin declares and `capabilities_of` composes
off the MRO. It is on the schema, so it serialises, which is what lets a
config file, the REST payload and the Qt window all select on the same
fact the wrapper does.

Declaring one:

    class PulserMixin:
        CAPABILITY = PULSER
        async def write_sequence(self, samples, name): ...

    class MyPulser(PulserMixin, AdapterBase): ...

An adapter may also name capabilities directly on its schema, for a device
that satisfies a contract without inheriting the mixin.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "GATED_COUNTER",
    "HARDWARE_SCAN",
    "PULSER",
    "capabilities_of",
    "with_capabilities",
]

HARDWARE_SCAN = "hardware_scan"
"""Drives a position waveform and reads a detector back on one shared
hardware timebase — `instruments/hardware_scan_mixin.py`."""

PULSER = "pulser"
"""Plays a sampled pulse sequence on its channels."""

GATED_COUNTER = "gated_counter"
"""Counts events into time bins, gated by a trigger per laser pulse."""


def capabilities_of(adapter: Any) -> frozenset[str]:
    """Every capability this adapter has, from its mixins and its schema.

    Takes an adapter or an adapter class, so a capability can be reported
    by `describe()` without hardware present — which is what puts it in
    the catalogue listing, not just on a live instrument.

    Composed off the MRO rather than tested one class at a time, so a
    device implementing two contracts reports both and no call site has to
    decide which to check first. Read from each class's own `__dict__`
    rather than by `getattr`, so an adapter cannot shadow the declaration
    with an instance attribute.
    """
    found: set[str] = set()
    classes = adapter.__mro__ if isinstance(adapter, type) else type(adapter).__mro__
    for base in classes:
        capability = base.__dict__.get("CAPABILITY")
        if isinstance(capability, str) and capability:
            found.add(capability)
        declared = base.__dict__.get("CAPABILITIES")
        if declared:
            found.update(str(c) for c in declared)

    if not isinstance(adapter, type):
        schema = getattr(adapter, "schema", None)
        found.update(getattr(schema, "capabilities", None) or ())
    return frozenset(found)


def with_capabilities(schema: Any, adapter: Any) -> Any:
    """`schema`, with the adapter's composed capabilities on it.

    A schema is written by the adapter and a capability comes from its
    mixins, so the two are only joined here. Doing it at the accessors
    (`InstrumentHandle.schema`, `describe()`) rather than asking every
    adapter to restate its mixins keeps the declaration in one place — the
    mixin — and still puts the fact on the wire, where `ui_blocks.toml`
    and the REST clients can select on it.
    """
    capabilities = capabilities_of(adapter)
    if not capabilities or capabilities == (schema.capabilities or frozenset()):
        return schema
    return schema.model_copy(update={"capabilities": capabilities})
