"""Protocol classes for hardware device abstraction.

Uses PEP 544 structural subtyping (Protocol) rather than inheritance. Devices
implement these protocols via duck typing — no explicit inheritance required.

This enables:
- Zero-coupling device drivers (no base class import needed)
- Easy wrapping of third-party drivers (just add methods)
- Compile-time type checking with mypy/pyright
- Runtime type checking with isinstance(device, Readable)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from labpilot_core.device.schema import DeviceSchema

__all__ = ["Movable", "Readable", "Triggerable"]


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


@runtime_checkable
class Movable(Readable, Protocol):
    """Device with settable position (motors, stages, tunable lasers).

    Extends Readable with motion control methods.
    """

    async def set(self, value: Any, *, timeout: float = 10.0) -> None:
        """Move device to target position and wait for completion.

        Args:
            value: Target position. Type depends on device (float, int, tuple).
            timeout: Maximum seconds to wait for motion to complete.

        Raises:
            TimeoutError: If motion does not complete within timeout.
            ValueError: If value is outside limits defined in schema.
        """
        ...

    async def stop(self) -> None:
        """Immediately halt any in-progress motion.

        Should return quickly (< 100ms). Device should remain in a safe state
        after stopping (e.g., motor drivers still enabled).
        """
        ...

    async def where(self) -> Any:
        """Get current device position.

        Returns:
            Current position. Type matches value passed to set().

        Example:
            >>> pos = await motor.where()
            >>> print(f"Current position: {pos} µm")
        """
        ...


@runtime_checkable
class Triggerable(Readable, Protocol):
    """Device that supports external triggering (cameras, DAQ cards).

    Extends Readable with trigger control methods.
    """

    async def trigger(self) -> None:
        """Issue a software trigger.

        Initiates one acquisition cycle. Used in software-triggered scans.
        Should return immediately (acquisition happens in background).
        """
        ...

    async def arm(self, mode: str) -> None:
        """Configure trigger mode.

        Args:
            mode: Trigger mode string. Must be one of schema.trigger_modes.
                  Common values: "software", "hardware", "free_run".

        Raises:
            ValueError: If mode is not in schema.trigger_modes.

        Example:
            >>> await camera.arm("hardware")
            >>> # Now camera waits for external TTL trigger
        """
        ...
