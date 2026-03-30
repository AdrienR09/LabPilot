"""Qt Bridge - QApplication in background thread with thread-safe window spawning.

Runs QApplication in a dedicated daemon thread with thread-safe communication
via queue. Provides open_window(), close_window(), and list_windows() methods
that can be called from async code.

Communication pattern:
  asyncio thread → _spawn_queue (thread-safe) → Qt thread (QTimer poll)
  Qt thread → asyncio_loop.call_soon_threadsafe() → asyncio callbacks
"""

from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Import guards to prevent loading Qt in async code
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMainWindow

__all__ = ["QtBridge", "get_bridge", "set_bridge"]

log = logging.getLogger(__name__)

# Global bridge instance
_global_bridge: QtBridge | None = None


class QtBridge:
    """Thread-safe bridge between asyncio and Qt.

    Runs QApplication in a dedicated daemon thread. Provides thread-safe
    window spawning via queue polled by QTimer every 50ms.

    Example:
        >>> bridge = QtBridge()
        >>> bridge.start()
        >>> bridge.open_window("spec_plot", {"type": "spectrum_plot", ...})
        >>> # Qt window appears in separate thread
    """

    def __init__(self) -> None:
        """Initialize Qt bridge."""
        self._qt_thread: threading.Thread | None = None
        self._qt_app: QApplication | None = None
        self._spawn_queue: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._windows: dict[str, QMainWindow] = {}
        self._timer: QTimer | None = None
        self._running = False
        self._asyncio_loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Start Qt thread and application.

        Idempotent - safe to call multiple times.
        """
        if self._qt_thread is not None and self._qt_thread.is_alive():
            log.debug("Qt bridge already running")
            return

        log.info("Starting Qt bridge thread")

        # Store asyncio loop for callbacks
        try:
            self._asyncio_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._asyncio_loop = None
            log.warning("No asyncio loop running - callbacks will be disabled")

        # Start Qt in daemon thread
        self._qt_thread = threading.Thread(
            target=self._run_qt,
            name="QtBridge",
            daemon=True,
        )
        self._qt_thread.start()

        # Wait for Qt app to initialize
        max_wait = 5.0  # seconds
        start_time = time.time()
        while self._qt_app is None and (time.time() - start_time) < max_wait:
            time.sleep(0.01)

        if self._qt_app is None:
            raise RuntimeError("Failed to initialize Qt application")

        log.info("Qt bridge started successfully")

    def stop(self) -> None:
        """Stop Qt thread and application."""
        if not self._running:
            return

        log.info("Stopping Qt bridge")
        self._running = False

        # Signal Qt thread to quit
        if self._qt_app is not None:
            # Use QTimer.singleShot to call quit in Qt thread
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._qt_app.quit)

        # Wait for thread to finish
        if self._qt_thread is not None:
            self._qt_thread.join(timeout=2.0)

        log.info("Qt bridge stopped")

    def open_window(self, window_id: str, spec: dict[str, Any]) -> None:
        """Open Qt window from specification (thread-safe).

        Args:
            window_id: Unique window identifier.
            spec: Window specification dictionary from DSL.
        """
        if not self._running:
            raise RuntimeError("Qt bridge not running")

        log.debug(f"Queuing window open: {window_id}")
        self._spawn_queue.put(("open", window_id, spec))

    def close_window(self, window_id: str) -> None:
        """Close Qt window by ID (thread-safe).

        Args:
            window_id: Window identifier to close.
        """
        if not self._running:
            log.warning("Qt bridge not running")
            return

        log.debug(f"Queuing window close: {window_id}")
        self._spawn_queue.put(("close", window_id))

    def list_windows(self) -> list[str]:
        """Get list of open window IDs (thread-safe).

        Returns:
            List of window IDs currently open.
        """
        return list(self._windows.keys())

    def _run_qt(self) -> None:
        """Run Qt application in dedicated thread (internal)."""
        try:
            # Import Qt modules inside thread
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QApplication

            log.debug("Initializing Qt application in thread")

            # Create QApplication
            self._qt_app = QApplication(sys.argv if hasattr(sys, 'argv') else [])
            self._qt_app.setQuitOnLastWindowClosed(False)  # Keep running when windows close

            # Create timer to process spawn queue
            self._timer = QTimer()
            self._timer.timeout.connect(self._process_spawn_queue)
            self._timer.start(50)  # Process every 50ms

            self._running = True
            log.info("Qt application starting event loop")

            # Run Qt event loop (blocks until quit)
            self._qt_app.exec()

            log.info("Qt application event loop finished")

        except Exception as e:
            log.error(f"Qt thread error: {e}")
            raise
        finally:
            self._running = False
            self._qt_app = None
            self._timer = None

    def _process_spawn_queue(self) -> None:
        """Process window spawn requests (runs in Qt thread)."""
        try:
            # Process all queued requests
            while True:
                try:
                    command = self._spawn_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    if command[0] == "open":
                        _, window_id, spec = command
                        self._open_window(window_id, spec)
                    elif command[0] == "close":
                        _, window_id = command
                        self._close_window(window_id)
                    else:
                        log.warning(f"Unknown command: {command[0]}")
                except Exception as e:
                    log.error(f"Error processing command {command}: {e}")

        except Exception as e:
            log.error(f"Error in _process_spawn_queue: {e}")

    def _open_window(self, window_id: str, spec: dict[str, Any]) -> None:
        """Open Qt window from spec (runs in Qt thread).

        Args:
            window_id: Unique window identifier.
            spec: Window specification from DSL.
        """
        log.info(f"Opening window: {window_id}")

        try:
            # Import window factory
            from labpilot_core.qt.factory import WindowFactory

            # Create window from specification
            window = WindowFactory.create_window(window_id, spec)

            # Store window reference
            self._windows[window_id] = window

            # Show window
            window.show()

            # Emit callback to asyncio thread if available
            if self._asyncio_loop is not None:
                self._asyncio_loop.call_soon_threadsafe(
                    self._on_window_opened, window_id, spec
                )

            log.debug(f"Window opened successfully: {window_id}")

        except Exception as e:
            log.error(f"Failed to open window {window_id}: {e}")

            # Emit error callback to asyncio thread if available
            if self._asyncio_loop is not None:
                self._asyncio_loop.call_soon_threadsafe(
                    self._on_window_error, window_id, str(e)
                )

    def _close_window(self, window_id: str) -> None:
        """Close Qt window by ID (runs in Qt thread).

        Args:
            window_id: Window identifier to close.
        """
        log.info(f"Closing window: {window_id}")

        window = self._windows.pop(window_id, None)
        if window is None:
            log.warning(f"Window not found: {window_id}")
            return

        try:
            # Close and delete window
            window.close()
            window.deleteLater()

            # Emit callback to asyncio thread if available
            if self._asyncio_loop is not None:
                self._asyncio_loop.call_soon_threadsafe(
                    self._on_window_closed, window_id
                )

            log.debug(f"Window closed successfully: {window_id}")

        except Exception as e:
            log.error(f"Error closing window {window_id}: {e}")

    def _on_window_opened(self, window_id: str, spec: dict[str, Any]) -> None:
        """Callback when window opens (runs in asyncio thread).

        Args:
            window_id: Window that was opened.
            spec: Window specification.
        """
        log.debug(f"Window opened callback: {window_id}")

    def _on_window_closed(self, window_id: str) -> None:
        """Callback when window closes (runs in asyncio thread).

        Args:
            window_id: Window that was closed.
        """
        log.debug(f"Window closed callback: {window_id}")

    def _on_window_error(self, window_id: str, error: str) -> None:
        """Callback when window creation fails (runs in asyncio thread).

        Args:
            window_id: Window that failed to open.
            error: Error message.
        """
        log.error(f"Window error callback: {window_id} - {error}")


def get_bridge() -> QtBridge | None:
    """Get global Qt bridge instance.

    Returns:
        Global QtBridge instance or None if not set.
    """
    return _global_bridge


def set_bridge(bridge: QtBridge) -> None:
    """Set global Qt bridge instance.

    Args:
        bridge: QtBridge instance to set as global.
    """
    global _global_bridge
    _global_bridge = bridge
