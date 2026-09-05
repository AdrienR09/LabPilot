"""`Readable` — the minimal contract every device satisfies.

`Movable` and `Triggerable` used to live here too. They were a fourth
parallel taxonomy alongside `DeviceSchema.kind`, `catalog.InstrumentType`
and `instruments/generic_params.py`'s `GENERIC_PARAMS`, and unlike the
other three they were checked nowhere: there was not one `isinstance`
call against either of them anywhere in the tree, 9 of 26 motors
satisfied `Movable`, and 8 of 49 detectors satisfied `Triggerable`. The
adapters that inherited them keep their `set`/`stop`/`where` and
`trigger`/`arm` methods — nothing called those *through* the protocol.

What they were trying to say is now said by the schema, where it can be
acted on: a commandable axis is a `Parameter` with `role=POSITION` (see
`DeviceSchema.position_axes`), and trigger support is
`DeviceSchema.trigger_modes`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from labpilot.core.device.schema import DeviceSchema

__all__ = ["Readable"]


@runtime_checkable
class Readable(Protocol):
    """Device that can be read (detectors, counters, temperature sensors).

    All devices must implement Readable. It is the minimal interface for
    participation in a scan.
    """

    schema: DeviceSchema

    async def read(self) -> dict[str, Any]:
        """Read current device state.

        Returns dict mapping axis names to values. Keys must match those in
        schema.readable.

        Returns:
            Dict of axis_name -> value. Values match dtypes in schema.

        Example:
            >>> data = await detector.read()
            >>> print(data)
            {"wavelengths": np.array([...]), "intensities": np.array([...])}
        """
        ...

    async def stage(self) -> None:
        """Prepare device for data acquisition.

        Called once before scan starts. Use for:
        - Opening hardware connections
        - Allocating buffers
        - Configuring trigger modes
        - Starting background tasks

        Must be idempotent (safe to call multiple times).
        """
        ...

    async def unstage(self) -> None:
        """Clean up after data acquisition.

        Called once after scan completes (even on abort/error). Use for:
        - Closing hardware connections
        - Freeing buffers
        - Stopping background tasks

        Must be idempotent and safe to call even if stage() failed.
        """
        ...
