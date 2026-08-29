"""Manages a Jupyter server subprocess pre-wired to talk to this running
LabPilot backend — launched on demand from the Manager's Notebook/Console
tabs (see server.py's /api/jupyter/* routes) and documented in
docs/user_guide.md's "Notebooks & console" section.

Why a subprocess, not an in-process kernel: instruments, the Session, and
the WorkflowEngine here are live Python objects (open hardware handles)
owned by THIS process and its asyncio event loop. A Jupyter kernel is a
separate OS process by default and can't share those objects directly —
but it can reach them exactly the way every other out-of-process client
already does (the desktop app's BackendClient, the React frontend): over
the REST/WebSocket API. Every kernel — and every terminal's `ipython`
shell — launched through this server auto-connects via an IPython startup
script (_BOOTSTRAP_SOURCE below) so `lp` (a notebook_api.LabPilotSession)
is ready to use the moment a notebook or console tab opens.

Security note: this server executes arbitrary code on request (that's the
point) and is deliberately configured with relaxed CSRF/CORS/CSP checks
so the Manager can embed it in an iframe — safe only because it binds to
127.0.0.1 and every request still needs its per-launch random token
(never exposed except via this process's own already-authenticated
/api/jupyter/status). Don't change the bind host to 0.0.0.0.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_BOOTSTRAP_SOURCE = '''\
"""Auto-run for every LabPilot notebook/console kernel — see
core/jupyter_launcher.py. Connects to the live LabPilot server over its
REST/WebSocket API (the same one the desktop app and web UI use) and
binds the result to `lp`.
"""
try:
    from core.notebook_api import LabPilotSession
    lp = LabPilotSession()
    print(
        f"Connected to LabPilot at {lp.base_url} "
        f"({len(lp.instruments)} instrument(s) registered)."
    )
    print("Try: lp.instruments, lp['<instrument_id>'].read(), lp.workflows, lp.workflow('<id>').run()")
except Exception as _e:  # pragma: no cover - interactive convenience only
    print(f"Could not auto-connect to LabPilot ({_e}) — check LABPILOT_URL / that the server is up.")
'''


class JupyterLauncher:
    """One instance per LabPilotServer (see server.py) — owns at most one
    Jupyter server subprocess for the lifetime of the backend process."""

    def __init__(self, config_dir: Path, backend_url: str, repo_src_dir: Path) -> None:
        self._jupyter_dir = config_dir / "jupyter"
        self._backend_url = backend_url
        self._repo_src_dir = repo_src_dir
        self._process: subprocess.Popen | None = None
        self._port: int | None = None
        self._token: str | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, Any]:
        if not self.running:
            return {"running": False}
        base = f"http://127.0.0.1:{self._port}"
        return {
            "running": True,
            "port": self._port,
            "token": self._token,
            "base_url": base,
            "notebook_url": f"{base}/tree?token={self._token}",
        }

    def start(self) -> dict[str, Any]:
        if self.running:
            return self.status()

        notebooks_dir = self._jupyter_dir / "notebooks"
        notebooks_dir.mkdir(parents=True, exist_ok=True)
        profile_dir = self._write_bootstrap_profile()
        kernels_root = self._write_kernelspec(profile_dir)
        config_path = self._write_server_config()

        self._port = _free_port()
        self._token = secrets.token_hex(24)

        env = dict(os.environ)
        env["IPYTHONDIR"] = str(profile_dir)
        env["JUPYTER_PATH"] = str(kernels_root)
        env["LABPILOT_URL"] = self._backend_url
        env["PYTHONPATH"] = str(self._repo_src_dir) + os.pathsep + env.get("PYTHONPATH", "")

        cmd = [
            sys.executable, "-m", "notebook",
            "--ServerApp.ip=127.0.0.1",
            f"--ServerApp.port={self._port}",
            f"--ServerApp.token={self._token}",
            f"--ServerApp.root_dir={notebooks_dir}",
            "--ServerApp.open_browser=False",
            f"--ServerApp.config_file={config_path}",
        ]
        self._process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if not _wait_for_port(self._port, timeout=25.0):
            log = ""
            if self._process.stdout is not None:
                log = self._process.stdout.read(4000)
            self.stop()
            raise RuntimeError(f"Jupyter server did not start within 25s.\n{log}")
        return self.status()

    def stop(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            self._port = None
            self._token = None

    def _write_bootstrap_profile(self) -> Path:
        profile_dir = self._jupyter_dir / "ipython_profile"
        startup_dir = profile_dir / "profile_default" / "startup"
        startup_dir.mkdir(parents=True, exist_ok=True)
        (startup_dir / "00-labpilot.py").write_text(_BOOTSTRAP_SOURCE)
        return profile_dir

    def _write_kernelspec(self, profile_dir: Path) -> Path:
        """Registers a "python3" kernel (Jupyter's conventional default
        kernel name) inside our own managed directory, discovered via the
        JUPYTER_PATH env var set in start() — doesn't touch any kernelspec
        the environment may already have installed globally."""
        kernels_root = self._jupyter_dir / "share"
        kernel_dir = kernels_root / "kernels" / "python3"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "LabPilot (Python 3)",
            "language": "python",
            "env": {
                "IPYTHONDIR": str(profile_dir),
                "PYTHONPATH": str(self._repo_src_dir),
                "LABPILOT_URL": self._backend_url,
            },
        }
        (kernel_dir / "kernel.json").write_text(json.dumps(spec, indent=2))
        return kernels_root

    def _write_server_config(self) -> Path:
        config_path = self._jupyter_dir / "jupyter_server_config.py"
        config_path.write_text(
            "c.ServerApp.allow_origin = '*'\n"
            "c.ServerApp.tornado_settings = {\n"
            "    'headers': {'Content-Security-Policy': \"frame-ancestors *\"},\n"
            "}\n"
            "c.ServerApp.disable_check_xsrf = True\n"
            # jupyter_server_terminals reads shell_command from
            # ServerApp.terminado_settings (a plain dict), not from
            # TerminalManager itself — see its app.py's initialize().
            f"c.ServerApp.terminado_settings = {{'shell_command': [{sys.executable!r}, '-m', 'IPython']}}\n"
        )
        return config_path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False
