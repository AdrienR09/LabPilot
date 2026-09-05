"""Launches and owns a `labpilot start` subprocess for
`manager_qt_webview.py`'s manager window — instead of running the
server in-process on a background thread.

A background-thread approach was tried first (same "own thread" pattern
`backend_client.py` uses for its HTTP pollers) and reliably crashed with
a SIGBUS as soon as `QWebEngineView` actually rendered anything —
reproduced both in an offscreen test environment and on real hardware,
with a live thread of ANY kind (not specific to uvicorn/asyncio) present
before/during the webview's event loop. This is the same class of
fork()-safety hazard `launch_instrument.py`/`launch_workflow.py` already
sidestep for instrument/workflow windows by making them genuinely
separate OS processes rather than threads — this module applies that
same fix to the server itself, which now never shares a process with
`QWebEngineView` at all.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

__all__ = ["ManagedServer"]

LOG_PATH = Path.home() / ".labpilot" / "logs" / "manager_server.log"


class ManagedServer:
    """Spawns `labpilot start --host ... --port ...` as a child process
    and owns its lifecycle (started with the manager, stopped with it) —
    same log-to-file-not-discarded convention as
    `launch_instrument.py`/`launch_workflow.py`."""

    def __init__(
        self, host: str = "127.0.0.1", port: int = 8000, config_dir: Optional[Path] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._config_dir = config_dir
        self._process: Optional[subprocess.Popen] = None
        self._start_error: Optional[str] = None

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start(self) -> None:
        labpilot_exe = shutil.which("labpilot") or "labpilot"
        cmd = [labpilot_exe, "start", "--host", self._host, "--port", str(self._port)]
        if self._config_dir is not None:
            cmd += ["--config-dir", str(self._config_dir)]

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            log_file = open(LOG_PATH, "a")
            self._process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
        except OSError as exc:
            self._start_error = str(exc)

    def wait_until_ready(self, timeout: float = 10.0) -> None:
        """Blocks until the spawned server process is actually answering
        requests — or raises, with a clear reason, if it never does."""
        if self._start_error is not None:
            raise RuntimeError(f"Could not launch the LabPilot server process: {self._start_error}")

        # A bind-port-already-in-use failure (e.g. a second manager
        # pointed at a port some OTHER process is already serving)
        # happens fast — but an HTTP GET against that port would happily
        # reach that other, pre-existing process and look "ready" before
        # this one's own subprocess ever gets checked for having already
        # died. Give it a brief head start so a fast failure shows up as
        # an exited process on the very first check below, not a
        # false-positive success against someone else's server.
        time.sleep(0.3)

        deadline = time.monotonic() + timeout
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"LabPilot server process exited early (code {self._process.returncode}) — "
                    f"see {LOG_PATH} for details. Is port {self._port} already in use?"
                )
            try:
                httpx.get(f"{self.base_url}/api/dashboard/instruments", timeout=1.0)
                return
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(0.2)
        raise RuntimeError(
            f"LabPilot server did not become reachable at {self.base_url} within {timeout}s"
        ) from last_error

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5.0)
