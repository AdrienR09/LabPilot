"""`labpilot app`: front-end resolution, port selection, and the SPA fallback.

The routing tests below are a regression net for a real mistake. The SPA
fallback was first written as a `@app.get("/{path:path}")` catch-all, which
quietly broke two things the API contract depends on: a GET on a POST-only
endpoint answered 404 instead of 405, and a POST to a nonexistent path
answered 405 (it matched the catch-all's path but not its method) instead
of 404. Hooking the 404 instead leaves Starlette's method handling alone.
"""

from __future__ import annotations

import os
import socket
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from labpilot.core.frontend import (
    BUILD_ENV_VAR,
    SOURCE_ENV_VAR,
    frontend_build_dir,
    frontend_source_dir,
)
from labpilot.core.launcher import (
    DESKTOP_REQUIREMENTS,
    _bundle_is_stale,
    _install_dependencies,
    _missing_desktop_packages,
    _reachable,
    _usable_port,
)
from labpilot.core.server import create_app

# --- Finding the front end -------------------------------------------------


def test_a_built_bundle_is_found_by_its_entry_point(tmp_path, monkeypatch):
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("<!doctype html><title>t</title>")
    monkeypatch.setenv(BUILD_ENV_VAR, str(build))
    assert frontend_build_dir() == build


def test_an_empty_build_directory_is_not_a_front_end(tmp_path, monkeypatch):
    """An interrupted `npm run build` leaves the directory behind. Serving
    that is worse than reporting no front end, because the fallback (the
    dev server) still works and a half-built bundle does not."""
    empty = tmp_path / "build"
    empty.mkdir()
    monkeypatch.setenv(BUILD_ENV_VAR, str(empty))
    # Falls through to the checkout, which in this repo does have one.
    assert frontend_build_dir() != empty


def test_the_source_tree_is_found_by_its_package_json(tmp_path, monkeypatch):
    source = tmp_path / "frontend"
    source.mkdir()
    (source / "package.json").write_text("{}")
    monkeypatch.setenv(SOURCE_ENV_VAR, str(source))
    assert frontend_source_dir() == source


def test_resolution_does_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    """The whole point: the server used to look for `frontend/build`
    relative to the process's cwd, so an installed package served no
    browser UI from anywhere but a repo root — silently."""
    monkeypatch.chdir(tmp_path)
    assert frontend_build_dir() is not None


# --- Choosing a port -------------------------------------------------------


def test_a_bindable_port_is_used_as_asked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    assert _usable_port("127.0.0.1", free) == free


def test_an_unbindable_port_falls_back_instead_of_failing():
    """`launch.sh` freed its ports by killing whatever held them. Taking
    a different port is the better move on a shared machine, and the only
    one that helps on Windows, where a reserved range refuses the bind
    with nothing listening to kill."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        taken = held.getsockname()[1]
        chosen = _usable_port("127.0.0.1", taken)
    assert chosen != taken
    assert chosen > 0


@pytest.mark.parametrize("wildcard", ["0.0.0.0", "::", ""])
def test_a_wildcard_bind_address_is_advertised_as_localhost(wildcard):
    """`0.0.0.0` is a valid address to bind and not one to connect to —
    Chromium refuses it, so the window would show an error page for a
    server that is running fine."""
    assert _reachable(wildcard) == "localhost"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "lab-pc.local", "192.168.1.20"])
def test_a_real_host_is_passed_through(host):
    assert _reachable(host) == host


# --- Managing the front end itself ----------------------------------------


def _fake_checkout(tmp_path, *, stale: bool):
    """A `frontend/` whose bundle is either newer or older than its sources.

    Every watched path gets an explicit mtime, including `package.json` — a
    file left at the current time is newer than any bundle we then backdate,
    which made the first version of this helper report "stale" always.
    """
    source = tmp_path / "frontend"
    (source / "src").mkdir(parents=True)
    build = source / "build"
    build.mkdir()

    early, late = 1_000_000, 2_000_000
    source_time, build_time = (late, early) if stale else (early, late)

    for relative, content in (
        ("package.json", "{}"),
        ("vite.config.ts", "export default {}"),
        ("index.html", "<!doctype html>"),
        ("src/App.tsx", "export default 1"),
    ):
        path = source / relative
        path.write_text(content)
        os.utime(path, (source_time, source_time))

    (build / "index.html").write_text("<!doctype html>")
    os.utime(build / "index.html", (build_time, build_time))
    return source, build


def test_a_bundle_built_after_its_sources_is_not_stale(tmp_path):
    source, build = _fake_checkout(tmp_path, stale=False)
    assert _bundle_is_stale(source, build) is False


def test_a_bundle_older_than_its_sources_is_stale(tmp_path):
    source, build = _fake_checkout(tmp_path, stale=True)
    assert _bundle_is_stale(source, build) is True


def test_staleness_is_not_an_error_when_there_is_no_bundle(tmp_path):
    """Reported, never acted on — and never allowed to raise, because it runs
    on the ordinary launch path where a bundle has just been served."""
    source = tmp_path / "frontend"
    source.mkdir()
    assert _bundle_is_stale(source, tmp_path / "nonexistent") is False


def test_dependencies_are_installed_only_when_missing(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "labpilot.core.launcher._run_npm",
        lambda source, npm, args, what: calls.append(args),
    )
    source = tmp_path / "frontend"
    source.mkdir()

    _install_dependencies(source, "npm")
    assert calls == [["install"]], "a missing node_modules should be installed"

    (source / "node_modules" / "vite").mkdir(parents=True)
    _install_dependencies(source, "npm")
    assert calls == [["install"]], "an existing node_modules should be left alone"


def test_a_node_modules_without_vite_is_reinstalled(tmp_path, monkeypatch):
    """A half-finished or interrupted `npm install` leaves the directory
    behind, and trusting its mere existence is how `launch.sh` failed
    obscurely rather than fixing itself."""
    calls = []
    monkeypatch.setattr(
        "labpilot.core.launcher._run_npm",
        lambda source, npm, args, what: calls.append(args),
    )
    source = tmp_path / "frontend"
    (source / "node_modules").mkdir(parents=True)
    _install_dependencies(source, "npm")
    assert calls == [["install"]]


# --- The desktop packages ------------------------------------------------


def test_the_desktop_check_reports_nothing_missing_in_this_environment():
    """The dev environment has the `app` extra, so this is also a check that
    the requirement list names real, importable modules rather than modules
    that were renamed at some point."""
    assert _missing_desktop_packages() == []


def test_a_missing_desktop_module_is_named_by_its_distribution(monkeypatch):
    """`No module named 'pyqtgraph'` is not actionable; `pip install
    "labpilot[app]"` is. The mapping is what turns one into the other."""
    monkeypatch.setitem(DESKTOP_REQUIREMENTS, "labpilot_not_a_real_module", "Some-Dist")
    assert _missing_desktop_packages() == ["Some-Dist"]


def test_the_check_covers_what_the_manager_imports_at_module_level():
    """Import-time requirements only. `pymodaq_gui` and `vispy` ship in the
    same extra but load when an instrument window opens, so requiring them
    would refuse to start a manager that would have worked."""
    assert set(DESKTOP_REQUIREMENTS) == {
        "PyQt6.QtWidgets",
        "PyQt6.QtWebEngineWidgets",
        "pyqtgraph",
        "qtconsole",
    }


# --- Serving the built bundle ---------------------------------------------


@pytest.fixture
def served(tmp_path, monkeypatch):
    build = tmp_path / "build"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>shell</title>")
    (build / "assets" / "app.js").write_text("console.log(1)")
    (build / "icon.svg").write_text("<svg/>")
    monkeypatch.setenv(BUILD_ENV_VAR, str(build))
    return TestClient(create_app())


def test_the_root_serves_the_app_shell(served):
    assert served.get("/").status_code == 200
    assert "shell" in served.get("/").text


@pytest.mark.parametrize("route", ["/devices", "/workflows", "/flow", "/data", "/settings"])
def test_client_side_routes_serve_the_shell(served, route):
    """The app routes with `BrowserRouter`, so these are URLs the browser
    requests directly on a reload. Without the fallback they 404 and the
    app looks broken only after a refresh."""
    response = served.get(route)
    assert response.status_code == 200
    assert "shell" in response.text


def test_a_root_level_build_file_is_served_as_itself(served):
    response = served.get("/icon.svg")
    assert response.status_code == 200
    assert response.text == "<svg/>"


def test_an_api_miss_stays_a_json_404(served):
    """Answering it with the HTML shell would hand every fetch() caller a
    body it cannot parse, turning a clear 404 into a JSON parse error."""
    response = served.get("/api/nonexistent")
    assert response.status_code == 404
    assert "json" in response.headers["content-type"]


def test_the_fallback_does_not_turn_a_405_into_a_404(served):
    """GET on a POST-only endpoint. The catch-all route this replaced
    matched the path and swallowed the method mismatch."""
    assert served.get("/api/devices/connect").status_code == 405


def test_the_fallback_does_not_turn_a_404_into_a_405(served):
    """POST to a path with no route. Against a GET-only catch-all this
    matched the path but not the method, and answered 405."""
    assert served.post("/api/invalid/endpoint").status_code == 404


@pytest.mark.parametrize(
    "attempt",
    [
        "/../../../etc/passwd",
        "/%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/..%2f..%2f..%2fetc%2fpasswd",
        "/assets/../../../../etc/passwd",
    ],
)
def test_the_fallback_does_not_serve_files_outside_the_bundle(served, attempt):
    response = served.get(attempt)
    assert "root:" not in response.text


# --- The first paint must not depend on the network ------------------------
#
# The built page loaded two webfont stylesheets from fonts.googleapis.com
# with a plain `rel="stylesheet"`, which is render-blocking. On a lab PC
# with no internet — or behind a firewall that drops the connection rather
# than refusing it — Chromium painted nothing while it waited, so the Qt
# manager window sat completely dark with its title stuck at "Loading 0%".
# Nothing in the app is remote except those fonts, and Tailwind already
# declares local fallbacks for both, so this is pure cost.


class _Externals(HTMLParser):
    """Remote resources that hold up the first paint."""

    def __init__(self) -> None:
        super().__init__()
        self.blocking: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: (value or "") for name, value in attrs}
        href = attributes.get("href", "") or attributes.get("src", "")
        if not href.startswith(("http://", "https://")):
            return
        if tag == "link" and attributes.get("rel", "").lower() == "stylesheet":
            # `media="print"` (swapped to "all" on load) is the standard way
            # to fetch a stylesheet without blocking the render.
            if attributes.get("media", "all").lower() in ("", "all"):
                self.blocking.append(href)
        elif tag == "script" and "defer" not in attributes and "async" not in attributes:
            self.blocking.append(href)


def _blocking_remote_resources(html: str) -> list[str]:
    parser = _Externals()
    parser.feed(html)
    return parser.blocking


def test_the_front_end_source_blocks_its_first_paint_on_nothing_remote():
    source = frontend_source_dir()
    if source is None:
        pytest.skip("no front-end sources in this install")
    blocking = _blocking_remote_resources((source / "index.html").read_text())
    assert not blocking, (
        "These are fetched from the internet before the page can paint, so the app "
        f"hangs on a machine with no network: {blocking}"
    )


def test_the_built_bundle_blocks_its_first_paint_on_nothing_remote():
    build = frontend_build_dir()
    if build is None:
        pytest.skip("no built bundle in this install")
    blocking = _blocking_remote_resources((build / "index.html").read_text())
    assert not blocking, (
        "The built page blocks its first paint on the internet — rebuild it "
        f"(`labpilot app --build`) if the sources are already fixed: {blocking}"
    )


# --- Handing the window its rendering escape hatch -------------------------
#
# A manager window that opens blank on a machine where the same URL loads
# fine in a browser is a QtWebEngine problem, not a server one, and the
# remedies are Chromium flags in the window's own process. `--safe-graphics`
# has to reach it; the flags themselves are composed there, before anything
# builds a QApplication.


class _FakePopen:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.returncode = None

    def poll(self):
        return None


def _manager_command(monkeypatch, **kwargs) -> list[str]:
    import labpilot.core.launcher as launcher

    monkeypatch.setattr(launcher.subprocess, "Popen", _FakePopen)
    spawned = launcher._start_manager("http://localhost:8000", "http://localhost:8000", **kwargs)
    return spawned.command


def test_the_window_renders_normally_unless_safe_graphics_is_asked_for(monkeypatch):
    assert "--safe-graphics" not in _manager_command(monkeypatch)


def test_safe_graphics_reaches_the_window_process(monkeypatch):
    assert "--safe-graphics" in _manager_command(monkeypatch, safe_graphics=True)


def test_the_window_is_always_told_not_to_start_its_own_server(monkeypatch):
    """Without this it starts a second backend on its own default port."""
    assert "--external-backend" in _manager_command(monkeypatch)
