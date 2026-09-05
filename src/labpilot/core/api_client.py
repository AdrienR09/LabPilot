"""Thin synchronous HTTP client for the LabPilot backend — no Qt
dependency, so it's usable from anywhere that isn't the desktop app too:
notebooks/IPython consoles (see notebook_api.py, ui/desktop/console_window.py),
scripts, tests.

Failures surface as LabPilot exceptions (`core/errors.py`) carrying the
server's own message, not as httpx errors — see `_check`.

src/ui/desktop/backend_client.py re-exports LabPilotClient as
BackendClient (its historical name there) and adds the Qt-specific
WorkflowStatePoller on top — that file is the one to extend for anything
Qt-signal-based; this one stays framework-agnostic.
"""

from __future__ import annotations

from typing import Any

import httpx

from labpilot.core.errors import (
    DeviceError,
    LabPilotError,
    NotConnectedError,
    ParameterError,
    UnsupportedOperationError,
)

# HTTP status -> the exception the server-side call would have raised. The
# point is that a script gets the same exception type whether it runs
# in-process (a workflow template) or over this client (the console): a
# rejected setpoint is a ParameterError in both, not an httpx error whose
# str() is a link to MDN's page on 422.
_STATUS_TO_ERROR: dict[int, type[LabPilotError]] = {
    409: NotConnectedError,
    422: ParameterError,
    501: UnsupportedOperationError,
}


def _check(response: httpx.Response) -> httpx.Response:
    """Raise the LabPilot exception the server's status code stands for,
    carrying the server's own message.

    `httpx.Response.raise_for_status()` reports the URL and a
    documentation link and drops the response body, so the reason — "50000.0
    is outside the limits [1.0, 5000.0] ms of ..." — never reached the
    console. `status_code` is kept on the exception for callers that
    branch on it.
    """
    if not response.is_error:
        return response

    detail: Any = None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error")
    except Exception:
        detail = None
    if not isinstance(detail, str):
        # FastAPI's own request-validation errors put a list of dicts here.
        detail = f"{response.request.method} {response.request.url.path} "\
                 f"failed with {response.status_code}"

    error = _STATUS_TO_ERROR.get(response.status_code, DeviceError)(detail)
    error.status_code = response.status_code
    raise error


class LabPilotClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")
        # Read gets more room than connect/write: GET .../execution_state
        # returns a workflow's *entire* last_results every call (e.g.
        # omniscan's full flat data array, not a delta — see
        # server.py's get_workflow_execution_state) — a big finished scan
        # can legitimately take longer than a plain request/response
        # round-trip to transfer and JSON-parse, well before anything is
        # actually stuck.
        timeout = httpx.Timeout(5.0, read=30.0)
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def get_instrument(self, instrument_id: str) -> dict[str, Any] | None:
        """Fetch one instrument's status by id from the live registry."""
        resp = self._client.get("/api/dashboard/instruments")
        _check(resp)
        for inst in resp.json()["data"]:
            if inst["id"] == instrument_id:
                return inst
        return None

    def list_instruments(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/dashboard/instruments")
        _check(resp)
        return resp.json()["data"]

    def get_schema(self, instrument_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/dashboard/instruments/{instrument_id}/schema")
        _check(resp)
        return resp.json()["data"]

    def read(self, instrument_id: str) -> dict[str, Any]:
        """Raises NotConnectedError if the instrument isn't connected."""
        resp = self._client.get(f"/api/dashboard/instruments/{instrument_id}/data")
        _check(resp)
        return resp.json()["data"]

    def write(
        self, instrument_id: str, values: dict[str, Any], *, persist: bool = False
    ) -> None:
        """Set one or more settable values.

        `persist=False` (the default) is an ordinary runtime write — moving a
        stage, stepping a source. Pass `persist=True` only for a genuine
        configuration change that should be saved and re-applied on the next
        connect, as the Settings dock does. Every write used to persist, so a
        scan driven from the console rewrote the instrument-set config on each
        point and left its final position saved as that instrument's startup
        value."""
        resp = self._client.post(
            f"/api/dashboard/instruments/{instrument_id}/settings",
            json={"values": values, "persist": persist},
        )
        _check(resp)

    def call_action(self, instrument_id: str, name: str) -> None:
        """Invoke one of an instrument's declared `DeviceSchema.actions`
        (e.g. a microwave source's "cw_on") — a zero-argument adapter
        method that isn't a settable-parameter write. Raises DeviceError
        for an undeclared action name, NotConnectedError if the instrument
        isn't connected."""
        resp = self._client.post(f"/api/dashboard/instruments/{instrument_id}/actions/{name}")
        _check(resp)

    def connect(self, instrument_id: str) -> None:
        resp = self._client.post(f"/api/dashboard/instruments/{instrument_id}/connect")
        _check(resp)

    def disconnect(self, instrument_id: str) -> None:
        resp = self._client.post(f"/api/dashboard/instruments/{instrument_id}/disconnect")
        _check(resp)

    def stage(self, instrument_id: str) -> None:
        """Prepare for acquisition — arm a camera, allocate a counter's
        buffer. Part of every adapter's contract; a scan that skips it runs
        every point on an unarmed device. Raises NotConnectedError if the
        instrument isn't connected."""
        resp = self._client.post(f"/api/dashboard/instruments/{instrument_id}/stage")
        _check(resp)

    def unstage(self, instrument_id: str) -> None:
        """Release after acquisition. See stage()."""
        resp = self._client.post(f"/api/dashboard/instruments/{instrument_id}/unstage")
        _check(resp)

    def get_ui_prefs(self, instrument_id: str) -> dict[str, Any]:
        """This instrument's native-UI display preferences (set via its
        Settings modal in the React Instruments tab — see
        core/config/instrument_ui_prefs.py). Best-effort: returns {} on
        any failure rather than raising, since a missing/unreachable
        prefs endpoint shouldn't block a window from opening."""
        try:
            resp = self._client.get(f"/api/dashboard/instruments/{instrument_id}/ui_prefs")
            _check(resp)
            return resp.json()["data"]
        except Exception:
            return {}

    def list_workflows(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/workflows")
        _check(resp)
        return resp.json()["data"]

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Full graph (nodes/edges/metadata) — see GET /api/workflows/{id}."""
        resp = self._client.get(f"/api/workflows/{workflow_id}")
        _check(resp)
        return resp.json()["data"]

    def get_workflow_script(self, workflow_id: str) -> str | None:
        """Raw script text, or None if this workflow has no script file yet."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/script")
        if resp.status_code == 404:
            return None
        _check(resp)
        return resp.json()["data"]["content"]

    def get_workflow_params(self, workflow_id: str) -> dict[str, Any]:
        """This workflow's own tunable parameters (e.g. a scan's
        range/resolution) — distinct from any bound instrument's own
        settings. See GET /api/workflows/{id}/params."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/params")
        _check(resp)
        return resp.json()["data"]

    def set_workflow_param(self, workflow_id: str, name: str, value: Any) -> Any:
        """Changes one workflow parameter in place. See
        PUT /api/workflows/{id}/params/{name}."""
        resp = self._client.put(f"/api/workflows/{workflow_id}/params/{name}", json={"value": value})
        _check(resp)
        return resp.json()["data"]["value"]

    def start_optimize(
        self, workflow_id: str, axes: list[str] | None = None,
        ranges: dict[str, float] | None = None, points: int = 5,
        points_per_axis: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Starts (as a background task on the server) re-centering a
        workflow's optimizer-capability-bound actuator on its detector's
        local maximum — a small ad-hoc sequence of <=2D sub-scans (any
        number of actuator axes; see `core/workflow/capabilities.py`'s
        `OptimizerCapability`), not a full run of the workflow. `axes`,
        if given, restricts which actuator axes to optimize over
        (omit for every available one — today's default); `ranges`/
        `points_per_axis` override the per-axis search span/resolution
        (an axis not present in either uses the server's own default — a
        fraction of its declared AXIS_RANGES span, and `points`,
        respectively). Returns immediately; poll get_optimize_state() for
        live progress. Raises httpx.HTTPStatusError with status 409 if
        one's already running for this workflow (reported as a
        DeviceError carrying `status_code`). See
        POST /api/workflows/{id}/optimize/start."""
        resp = self._client.post(
            f"/api/workflows/{workflow_id}/optimize/start",
            json={"axes": axes, "ranges": ranges, "points": points, "points_per_axis": points_per_axis},
        )
        _check(resp)
        return resp.json()["data"]

    def stop_optimize(self, workflow_id: str) -> None:
        resp = self._client.post(f"/api/workflows/{workflow_id}/optimize/stop")
        _check(resp)

    def get_optimize_state(self, workflow_id: str) -> dict[str, Any]:
        """{running, progress (the grid so far, live), last_result (the
        final grid once finished), error}. See
        GET /api/workflows/{id}/optimize/state."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/optimize/state")
        _check(resp)
        return resp.json()["data"]

    def execute_workflow(self, workflow_id: str) -> dict[str, Any]:
        resp = self._client.post(f"/api/workflows/{workflow_id}/execute")
        _check(resp)
        return resp.json()["data"]

    def stop_workflow(self, workflow_id: str) -> None:
        resp = self._client.post(f"/api/workflows/{workflow_id}/stop")
        _check(resp)

    def get_workflow_execution_state(self, workflow_id: str) -> dict[str, Any]:
        """Live progress (while running) + last-completed status/results —
        see GET /api/workflows/{id}/execution_state, and
        core/session.py's report_progress() for how "progress" gets
        populated during a run."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/execution_state")
        _check(resp)
        return resp.json()["data"]

    def close(self) -> None:
        self._client.close()
