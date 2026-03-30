"""Base window class for LabPilot Qt windows.

All LabPilot Qt windows inherit from LabPilotWindow which provides:
- EventBus subscription via thread-safe asyncio → Qt bridge
- Window lifecycle management
- Common UI patterns and styling
"""

from __future__ import annotations

import asyncio
import logging
import queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent

    from labpilot_core.core.events import Event, EventBus

__all__ = ["LabPilotWindow"]

log = logging.getLogger(__name__)


class LabPilotWindow:
    """Base class for all LabPilot Qt windows.

    Provides:
    - EventBus subscription with thread-safe updates
    - Window lifecycle management
    - Common styling and behavior
    - Device data source tracking

    Each window has a dedicated asyncio task that reads from its event queue
    and posts updates to the Qt thread via QMetaObject.invokeMethod.

    Example:
        >>> class MyWindow(LabPilotWindow, QMainWindow):
        ...     def __init__(self, window_id: str, source: str):
        ...         QMainWindow.__init__(self)
        ...         LabPilotWindow.__init__(self, window_id, [source])
        ...
        ...     def _update_from_event(self, event: Event) -> None:
        ...         # Handle data update in Qt thread
        ...         pass
    """

    def __init__(self, window_id: str, sources: list[str]) -> None:
        """Initialize base window.

        Args:
            window_id: Unique window identifier.
            sources: List of data sources to subscribe to (format: "device.param").
        """
        self.window_id = window_id
        self.sources = sources
        self.device_names = [src.split(".")[0] for src in sources if "." in src]

        # Event handling
        self._event_queue: queue.Queue[Event] = queue.Queue()
        self._event_task: asyncio.Task | None = None
        self._asyncio_loop: asyncio.AbstractEventLoop | None = None
        self._bus: EventBus | None = None
        self._running = False

        log.debug(f"Initialized window {window_id} with sources: {sources}")

    def start_event_listener(self, bus: EventBus) -> None:
        """Start listening to EventBus for data updates.

        Args:
            bus: EventBus instance to subscribe to.
        """
        self._bus = bus

        try:
            # Get asyncio loop (must be called from asyncio thread)
            self._asyncio_loop = asyncio.get_running_loop()
        except RuntimeError:
            log.warning(f"No asyncio loop running for window {self.window_id}")
            return

        # Start event listener task
        self._event_task = self._asyncio_loop.create_task(self._event_listener())
        self._running = True

        log.info(f"Started event listener for window {self.window_id}")

    def stop_event_listener(self) -> None:
        """Stop listening to EventBus."""
        self._running = False

        if self._event_task is not None:
            self._event_task.cancel()
            self._event_task = None

        log.info(f"Stopped event listener for window {self.window_id}")

    async def _event_listener(self) -> None:
        """Event listener task (runs in asyncio thread).

        Subscribes to EventBus and forwards relevant events to Qt thread
        via thread-safe queue.
        """
        if self._bus is None:
            log.error(f"No bus available for window {self.window_id}")
            return

        try:
            log.debug(f"Starting event subscription for {self.window_id}")

            # Subscribe to READING events
            from labpilot_core.core.events import EventKind
            async for event in self._bus.subscribe(EventKind.READING):
                if not self._running:
                    break

                # Check if event is from one of our devices
                if hasattr(event, 'device_name') and event.device_name in self.device_names:
                    # Forward to Qt thread via thread-safe invoke
                    self._queue_qt_update(event)

        except asyncio.CancelledError:
            log.debug(f"Event listener cancelled for {self.window_id}")
        except Exception as e:
            log.error(f"Event listener error for {self.window_id}: {e}")

    def _queue_qt_update(self, event: Event) -> None:
        """Queue update for Qt thread (thread-safe).

        Args:
            event: Event to process in Qt thread.
        """
        try:
            # Import Qt modules inside method
            from PyQt6.QtCore import QMetaObject, Qt

            # Use QMetaObject.invokeMethod for thread-safe Qt call
            QMetaObject.invokeMethod(
                self,  # Target object (must inherit from QObject)
                "_handle_event_in_qt",  # Method name
                Qt.ConnectionType.QueuedConnection,  # Thread-safe queued call
                event,  # Event argument
            )
        except Exception as e:
            log.error(f"Failed to queue Qt update for {self.window_id}: {e}")

    def _handle_event_in_qt(self, event: Event) -> None:
        """Handle event in Qt thread (called via QMetaObject.invokeMethod).

        Args:
            event: Event from EventBus.
        """
        try:
            self._update_from_event(event)
        except Exception as e:
            log.error(f"Error updating window {self.window_id} from event: {e}")

    def _update_from_event(self, event: Event) -> None:
        """Update window from event (override in subclasses).

        Called in Qt thread when new data arrives from EventBus.

        Args:
            event: Event containing new data.
        """
        # Override in subclasses
        pass

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event.

        Args:
            event: Qt close event.
        """
        log.info(f"Closing window {self.window_id}")

        # Stop event listener
        self.stop_event_listener()

        # Accept close event
        event.accept()

    def _apply_labpilot_style(self) -> None:
        """Apply standard LabPilot window styling."""
        # Standard window styling
        self.setWindowTitle(self.windowTitle())
        self.resize(800, 600)  # Default size

        # Apply dark theme (if available)
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                # Apply dark palette if available
                # TODO: Implement LabPilot dark theme
                pass

        except Exception as e:
            log.warning(f"Failed to apply styling: {e}")

    def _parse_source_data(self, event: Event, source: str) -> Any | None:
        """Parse data for specific source from event.

        Args:
            event: Event containing data dict.
            source: Source string ("device.parameter").

        Returns:
            Data value or None if not found.
        """
        if "." not in source:
            return None

        device, param = source.split(".", 1)

        # Check if event is from correct device
        if hasattr(event, 'device_name') and event.device_name != device:
            return None

        # Extract parameter from event data
        if hasattr(event, 'data') and isinstance(event.data, dict):
            return event.data.get(param)

        return None


# Mixin for QMainWindow + LabPilotWindow
class LabPilotMainWindow:
    """Mixin class combining QMainWindow and LabPilotWindow.

    Use this as base class for Qt main windows with EventBus integration.

    Example:
        >>> class SpectrumWindow(LabPilotMainWindow, QMainWindow):
        ...     def __init__(self, window_id: str, source: str):
        ...         super().__init__()
        ...         self._init_labpilot_window(window_id, [source])
    """

    def _init_labpilot_window(self, window_id: str, sources: list[str]) -> None:
        """Initialize LabPilot window functionality.

        Args:
            window_id: Unique window identifier.
            sources: List of data sources.
        """
        # Initialize LabPilotWindow
        LabPilotWindow.__init__(self, window_id, sources)

        # Apply styling
        self._apply_labpilot_style()

        # Connect to session EventBus if available
        self._connect_to_session_bus()

    def _connect_to_session_bus(self) -> None:
        """Connect to session EventBus if available."""
        try:
            # Get session from global state
            # TODO: Implement proper session registry
            # For now, skip auto-connection
            log.debug(f"EventBus auto-connection not yet implemented for {self.window_id}")

        except Exception as e:
            log.warning(f"Failed to auto-connect to EventBus: {e}")
