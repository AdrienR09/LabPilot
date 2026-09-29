"""`labpilot app`: front-end resolution, port selection, and the SPA fallback.

The routing tests below are a regression net for a real mistake. The SPA
fallback was first written as a `@app.get("/{path:path}")` catch-all, which
quietly broke two things the API contract depends on: a GET on a POST-only
endpoint answered 404 instead of 405, and a POST to a nonexistent path
answered 405 (it matched the catch-all's path but not its method) instead
of 404. Hooking the 404 instead leaves Starlette's method handling alone.
"""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from labpilot.core.frontend import (
    BUILD_ENV_VAR,
    SOURCE_ENV_VAR,
    frontend_build_dir,
    frontend_source_dir,
)
from labpilot.core.launcher import _reachable, _usable_port
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
