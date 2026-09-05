"""Native IPython console window — LabPilot's equivalent of Qudi's own
embedded IPython console (qudikernel.py + a RichJupyterWidget dock in its
main GUI), opened from the Manager's toolbar (see manager_qt_webview.py).

A real, out-of-process IPython kernel — not an in-process one — for the
same reason core/notebook_api.py's LabPilotSession exists: instruments and
the running Session are live objects owned by the backend server process.
This kernel reaches them exactly the way the desktop app's own
BackendClient does, over the REST/WebSocket API, via `lp` (auto-bound by
the startup script below — the same bootstrap mechanism LabPilot's earlier
Jupyter-notebook integration used, before that was replaced by this native
window). No Jupyter server process is involved here at all — qtconsole's
RichJupyterWidget talks to the kernel directly over ZeroMQ.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyqt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow
from qtconsole.manager import QtKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget

_BOOTSTRAP_SOURCE = '''\
"""Auto-run for the LabPilot console kernel — see
ui/desktop/console_window.py. Connects to the live LabPilot server over
its REST/WebSocket API (the same one the desktop app and web UI use) and
binds the result to `lp`.
"""
try:
    from labpilot.core.notebook_api import LabPilotSession
    lp = LabPilotSession()
    print(
        f"Connected to LabPilot at {lp.base_url} "
        f"({len(lp.instruments)} instrument(s) registered)."
    )
    print("Try: lp.instruments, lp['<instrument_id>'].read(), lp.workflows, lp.workflow('<id>').run()")
except Exception as _e:  # pragma: no cover - interactive convenience only
    print(f"Could not auto-connect to LabPilot ({_e}) - check LABPILOT_URL / that the server is up.")
'''


def _write_bootstrap_profile(config_dir: Path) -> Path:
    profile_dir = config_dir / "console" / "ipython_profile"
    startup_dir = profile_dir / "profile_default" / "startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    (startup_dir / "00-labpilot.py").write_text(_BOOTSTRAP_SOURCE)
    return profile_dir


class ConsoleWindow(QMainWindow):
    """One IPython kernel per window — started in __init__, shut down in
    closeEvent. The caller (manager_qt_webview.py) is expected to keep a
    reference so the window (and its kernel) aren't garbage-collected the
    moment the function that opened it returns."""

    def __init__(self, backend_url: str = "http://localhost:8000", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LabPilot Console")
        self.resize(900, 600)
        # So closing the window actually destroys it (running closeEvent
        # and firing Qt's `destroyed` signal) instead of just hiding it —
        # the caller (manager_qt_webview.py) relies on `destroyed` to know
        # it needs to start a fresh kernel next time rather than re-
        # showing a window whose kernel was already shut down.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        repo_src_dir = Path(__file__).resolve().parent.parent.parent
        config_dir = Path.home() / ".labpilot"
        profile_dir = _write_bootstrap_profile(config_dir)

        env = dict(os.environ)
        env["IPYTHONDIR"] = str(profile_dir)
        env["PYTHONPATH"] = str(repo_src_dir) + os.pathsep + env.get("PYTHONPATH", "")
        env["LABPILOT_URL"] = backend_url

        # kernel_cmd is set directly (bypassing kernelspec lookup/
        # registration entirely) since this doesn't need to be discoverable
        # by any other Jupyter tooling — just launched by this window.
        self._kernel_manager = QtKernelManager()
        self._kernel_manager.kernel_cmd = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        self._kernel_manager.start_kernel(env=env)
        self._kernel_client = self._kernel_manager.client()
        self._kernel_client.start_channels()

        widget = RichJupyterWidget()
        widget.kernel_manager = self._kernel_manager
        widget.kernel_client = self._kernel_client
        widget.exit_requested.connect(self.close)
        self.setCentralWidget(widget)
        self._widget = widget

    def closeEvent(self, event) -> None:
        try:
            self._kernel_client.stop_channels()
            self._kernel_manager.shutdown_kernel(now=True)
        except Exception:
            pass
        super().closeEvent(event)
