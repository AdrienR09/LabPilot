"""`labpilot app` — the backend, the front end and the manager window
from one command.

This is what `launch.sh` does, without needing bash, conda, `lsof` or
POSIX process groups, because the person most likely to launch the app
this way is on Windows and will never read `launch.sh`.

Three differences from that script, each of which it got away with only
because it ran in a macOS checkout:

* **The front end does not need Node.** If the bundle is already built,
  the backend serves it and no dev server is started at all — which is
  the only path that works on a machine with no `npm`. `--dev` forces the
  dev server anyway, for hot reload while editing `frontend/`.
* **Ports are checked by binding them.** `launch.sh` cleared ports 3000
  and 8000 by killing whatever held them. That is the wrong move on a
  shared machine, and it does not help on Windows at all, where a bind
  inside a Hyper-V/WSL reserved range fails with WinError 10013 while
  nothing is listening. So: try the port you asked for, and fall back to
  one the OS picks rather than killing a stranger's process.
* **Children are killed as trees.** `npm run dev` forks Vite as a
  grandchild, so terminating npm alone leaves Vite holding the port and
  the next launch silently serves a stale bundle — the bug `launch.sh`
  fixed with process groups, which Windows does not have.

The manager window is spawned as a subprocess, never imported: a live
thread of any kind in the same process as `QWebEngineView` crashes it
with a SIGBUS (see `ui/desktop/managed_server.py`). Spawning also keeps
this module inside `core`, which never imports `ui`.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import httpx

from labpilot.core.frontend import frontend_build_dir, frontend_source_dir

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["run_app"]

# Long because startup is dominated by importing 301 adapters, measured
# at ~12-14s on a cold filesystem cache. Same reasoning as
# `ManagedServer.wait_until_ready`.
BACKEND_TIMEOUT = 90.0
FRONTEND_TIMEOUT = 120.0


def _say(message: str) -> None:
    """Print progress immediately.

    stdout is block-buffered when it is not a terminal, and the children
    inherit that same descriptor and write to it unbuffered — so without
    an explicit flush every line below turns up after the output it was
    meant to introduce, or not at all until exit.
    """
    print(message, flush=True)


def _usable_port(host: str, preferred: int) -> int:
    """`preferred` if the OS will really let us bind it, else one it picks.

    Binding is the only reliable test. Windows refuses ports inside a
    Hyper-V/WSL/Docker reserved range with WinError 10013 even though
    nothing is listening, so "can I connect to it?" answers a different
    question than the one that matters.
    """
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
            chosen = int(probe.getsockname()[1])
        if chosen != preferred:
            _say(f"   ⚠️  Port {preferred} is not bindable on {host} — using {chosen} instead")
        return chosen
    raise RuntimeError(f"Could not bind any port on {host}")


def _reachable(host: str) -> str:
    """A host a browser can actually open.

    `0.0.0.0` is a valid thing to *bind* — it means every interface — and
    not a valid thing to connect to: Chromium refuses it, so the webview
    would show an error page for a server that is running perfectly well.
    The wildcard forms become `localhost`; anything else is passed through
    so `--host` still works for reaching a server by name or LAN address.
    """
    return "localhost" if host in ("0.0.0.0", "::", "") else host


def _spawn_kwargs() -> dict:
    """Put each child in its own group, so our Ctrl-C does not race the
    children's own handlers and we can take a whole tree down ourselves."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate(process: subprocess.Popen, name: str) -> None:
    """Stop a child and everything it spawned."""
    if process.poll() is not None:
        return
    _say(f"   Stopping {name}…")
    if os.name == "nt":
        # No process groups to kill, and npm's Vite grandchild outlives a
        # plain terminate(). taskkill /T is Windows' tree kill.
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def _npm_command(npm: str, args: list[str]) -> list[str]:
    """npm on Windows is `npm.cmd`, which CreateProcess cannot run on its
    own — it needs a shell to interpret it."""
    if os.name == "nt":
        return ["cmd", "/c", npm, *args]
    return [npm, *args]


def _wait_for_http(url: str, process: subprocess.Popen, name: str, timeout: float) -> None:
    """Block until `url` answers, or raise saying why it never will."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"The {name} exited during startup (code {process.returncode}) — "
                "its output is above."
            )
        try:
            httpx.get(url, timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError(f"The {name} did not answer at {url} within {timeout:.0f}s")


def _build_frontend(source: Path, npm: str) -> None:
    _say(f"📦 Building the front end in {source} …")
    result = subprocess.run(_npm_command(npm, ["run", "build"]), cwd=source, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "`npm run build` failed — its output is above. If this is a fresh "
            f"checkout, run `npm install` in {source} first."
        )


def _start_backend(host: str, port: int) -> subprocess.Popen:
    """Run the server as a child process rather than in this one, so the
    manager window can be a sibling rather than sharing a process with
    either the server or a thread."""
    labpilot_exe = shutil.which("labpilot")
    cmd = (
        [labpilot_exe, "start"]
        if labpilot_exe
        else [sys.executable, "-m", "labpilot.core.cli", "start"]
    )
    cmd += ["--host", host, "--port", str(port)]
    return subprocess.Popen(cmd, **_spawn_kwargs())


def _start_dev_server(source: Path, npm: str, port: int, backend_url: str) -> subprocess.Popen:
    """Vite, with its `/api` and `/ws` proxy aimed at the backend we
    actually started — `vite.config.js` defaults to port 8000, which is
    wrong the moment `--port` differs or a fallback port was chosen."""
    env = {**os.environ, "LABPILOT_BACKEND": backend_url}
    return subprocess.Popen(
        _npm_command(npm, ["run", "dev", "--", "--port", str(port), "--strictPort"]),
        cwd=source,
        env=env,
        **_spawn_kwargs(),
    )


def _start_manager(frontend_url: str, backend_url: str) -> subprocess.Popen:
    """The Qt shell, pointed at the backend this command already owns.

    `--external-backend` matters: without it the manager starts a *second*
    server on its own default port.
    """
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "labpilot.ui.desktop.manager_qt_webview",
            "--url",
            frontend_url,
            "--external-backend",
            "--backend-url",
            backend_url,
        ],
        **_spawn_kwargs(),
    )


def _install_shutdown_handlers() -> None:
    """Make a signalled shutdown run our cleanup instead of skipping it.

    Python's default SIGTERM disposition kills the process outright, so the
    `finally` that stops the children never runs — they outlive us and keep
    holding the ports the next launch wants. Verified: `kill <launcher pid>`
    left the backend serving. `launch.sh` covered this with
    `trap cleanup EXIT INT TERM`; this is that trap. SIGINT already arrives
    as KeyboardInterrupt, which the same handling catches.
    """

    def _raise(_signum, _frame):
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        received = getattr(signal, name, None)
        if received is None:
            continue  # SIGHUP is POSIX-only, SIGBREAK Windows-only
        # Raises off the main thread, and not every platform has every
        # signal's handler slot writable.
        with contextlib.suppress(ValueError, OSError):
            signal.signal(received, _raise)


def run_app(args) -> int:
    """Start everything, wait, and take it all down together."""
    _install_shutdown_handlers()
    source = frontend_source_dir()
    npm = shutil.which("npm")
    children: list[tuple[str, subprocess.Popen]] = []

    try:
        # --- Decide how the front end gets served, before starting anything ---
        if args.build:
            if source is None or npm is None:
                raise RuntimeError(
                    "--build needs the `frontend/` sources and npm, and this "
                    f"install has {'no npm on PATH' if source else 'no frontend/ directory'}."
                )
            _build_frontend(source, npm)

        build = frontend_build_dir()
        use_dev_server = args.dev or build is None

        if use_dev_server:
            if source is None:
                raise RuntimeError(
                    "No front end to serve: this install has no built bundle and no "
                    "`frontend/` sources to build one from. Either run from a checkout, "
                    "or point $LABPILOT_FRONTEND at a built bundle."
                )
            if npm is None:
                raise RuntimeError(
                    "The Vite dev server needs npm, which is not on PATH. Install "
                    "Node.js, or drop --dev to serve an already-built bundle."
                )

        # --- Backend ---
        backend_port = _usable_port(args.host, args.port)
        backend_url = f"http://{_reachable(args.host)}:{backend_port}"
        _say(f"🚀 Starting the backend on {backend_url} …")
        backend = _start_backend(args.host, backend_port)
        children.append(("backend", backend))
        _wait_for_http(
            f"{backend_url}/api/dashboard/instruments", backend, "backend", BACKEND_TIMEOUT
        )
        _say("✅ Backend ready")

        # --- Front end ---
        if use_dev_server:
            frontend_port = _usable_port("127.0.0.1", args.frontend_port)
            frontend_url = f"http://localhost:{frontend_port}"
            _say(f"⚛️  Starting the Vite dev server on {frontend_url} …")
            dev_server = _start_dev_server(source, npm, frontend_port, backend_url)
            children.append(("dev server", dev_server))
            _wait_for_http(frontend_url, dev_server, "dev server", FRONTEND_TIMEOUT)
            _say("✅ Front end ready (dev server, hot reload)")
        else:
            frontend_url = backend_url
            _say(f"✅ Front end ready (built bundle from {build}, served by the backend)")

        # --- Window ---
        if args.no_window:
            _say(f"\n🌐 Open {frontend_url} in a browser. Ctrl-C here stops everything.")
            waited_on, waited_name = backend, "backend"
        else:
            _say("🪟 Opening the manager window …")
            manager = _start_manager(frontend_url, backend_url)
            children.append(("manager", manager))
            waited_on, waited_name = manager, "manager"

        # Exit when the thing the user is actually looking at exits — the
        # window, or the server in --no-window. A crash in any other child
        # ends the wait too, so a dead dev server is not silently tolerated.
        while waited_on.poll() is None:
            for name, child in children:
                if child is not waited_on and child.poll() is not None:
                    _say(f"\n❌ The {name} exited unexpectedly (code {child.returncode}).")
                    return 1
            time.sleep(0.4)

        if waited_on.returncode not in (0, -signal.SIGTERM, signal.SIGTERM):
            _say(f"\n❌ The {waited_name} exited with code {waited_on.returncode}.")
            return int(waited_on.returncode)
        return 0

    except KeyboardInterrupt:
        _say("\n🛑 Interrupted.")
        return 0
    except (RuntimeError, OSError) as exc:
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1
    finally:
        # Reverse order: the window goes before the server it talks to.
        for name, child in reversed(children):
            _terminate(child, name)
