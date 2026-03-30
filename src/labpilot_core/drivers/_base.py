"""Base classes and mixins for device drivers.

Provides common lifecycle management (connect/disconnect) that all drivers
should implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["BaseDriver"]


class BaseDriver(ABC):
    """Base class for all device drivers.

    Provides abstract connect/disconnect lifecycle methods. Drivers should
    inherit from this AND implement the appropriate Protocol (Readable/Movable).

    Note: This is a convenience base class. Drivers can also just implement
    the Protocol without inheritance if they provide connect/disconnect methods.
    """

    def __init__(self) -> None:
        """Initialize driver in disconnected state."""
        self._connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Establish hardware connection.

        Should be idempotent (safe to call multiple times). Sets self._connected
        to True on success.

        Raises:
            ConnectionError: If hardware not found or communication fails.
            TimeoutError: If connection attempt times out.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close hardware connection and clean up resources.

        Should be idempotent and safe to call even if connect() failed.
        Sets self._connected to False.
        """
        ...

    @property
    def connected(self) -> bool:
        """Check if driver is connected to hardware.

        Returns:
            True if connected, False otherwise.
        """
        return self._connected
