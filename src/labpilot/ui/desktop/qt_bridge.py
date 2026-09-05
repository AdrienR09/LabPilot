#!/usr/bin/env python3
"""Qt bridge exposed to the embedded React app (manager_qt_webview.py).

Its whole job is letting the web manager open *native* windows: the React
Devices and Workflows tabs hand off to a real Qt window when running inside
the Qt shell, and fall back to a degraded in-page view in a plain browser.

Deliberately carries no instrument or workflow data. The manager reaches
live state over the backend's REST/WebSocket API like every other client, and
each launched window fetches what it needs by id — this bridge only starts
processes. (It previously also served a hardcoded set of mock instruments and
workflows through a dozen extra slots; the React side never called any of
them, so they were removed rather than left to drift against the real API.)
"""

from PyQt6.QtCore import QObject, pyqtSlot


class QtBridge(QObject):
    """Bridge object exposed to JavaScript for React → Qt window launching."""

    def __init__(self, parent=None, backend_url: str = "http://localhost:8000"):
        super().__init__(parent)
        self.backend_url = backend_url

    @pyqtSlot(str)
    def launchInstrumentUI(self, instrument_id: str):  # noqa: N802 (JS-facing name)
        """Launch a native Qt/PyQtGraph window for a real instrument, by id.

        Runs as a separate OS process (see launch_instrument.py) so it opens
        as its own window — a crash in one instrument window can't take
        down the manager, and multiple windows can be arranged across
        monitors like Qudi's per-module windows. The window itself fetches
        the instrument's real schema/data from the backend by id; this
        bridge doesn't carry any instrument data itself.
        """
        print(f"[QtBridge] 🚀 Launching UI for instrument: {instrument_id}")
        try:
            from launch_instrument import launch_instrument_window

            pid = launch_instrument_window(instrument_id, self.backend_url)
            if pid is None:
                print(f"[QtBridge] ❌ Failed to launch window for: {instrument_id}")
        except Exception as e:
            print(f"[QtBridge] ❌ Error launching UI: {e}")
            import traceback
            traceback.print_exc()

    @pyqtSlot(str)
    def launchWorkflowUI(self, workflow_id: str):  # noqa: N802 (JS-facing name)
        """Launch the native combined Qt window for a workflow, by id —
        mirrors launchInstrumentUI above exactly, just for
        launch_workflow.py/workflow_window.py instead of the
        single-instrument path."""
        print(f"[QtBridge] 🚀 Launching UI for workflow: {workflow_id}")
        try:
            from launch_workflow import launch_workflow_window

            pid = launch_workflow_window(workflow_id, self.backend_url)
            if pid is None:
                print(f"[QtBridge] ❌ Failed to launch window for workflow: {workflow_id}")
        except Exception as e:
            print(f"[QtBridge] ❌ Error launching workflow UI: {e}")
            import traceback
            traceback.print_exc()
