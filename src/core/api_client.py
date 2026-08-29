"""Thin synchronous HTTP client for the LabPilot backend — no Qt
dependency, so it's usable from anywhere that isn't the desktop app too:
notebooks/IPython consoles (see notebook_api.py, ui/desktop/console_window.py),
scripts, tests.

src/ui/desktop/backend_client.py re-exports LabPilotClient as
BackendClient (its historical name there) and adds the Qt-specific
WorkflowStatePoller on top — that file is the one to extend for anything
Qt-signal-based; this one stays framework-agnostic.
"""

from __future__ import annotations

from typing import Any

import httpx


class LabPilotClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=5.0)

    def get_instrument(self, instrument_id: str) -> dict[str, Any] | None:
        """Fetch one instrument's status by id from the live registry."""
        resp = self._client.get("/api/dashboard/instruments")
        resp.raise_for_status()
        for inst in resp.json()["data"]:
            if inst["id"] == instrument_id:
                return inst
        return None

    def list_instruments(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/dashboard/instruments")
        resp.raise_for_status()
        return resp.json()["data"]

    def get_schema(self, instrument_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/dashboard/instruments/{instrument_id}/schema")
        resp.raise_for_status()
        return resp.json()["data"]

    def read(self, instrument_id: str) -> dict[str, Any]:
        """Raises httpx.HTTPStatusError with status 409 if not connected."""
        resp = self._client.get(f"/api/dashboard/instruments/{instrument_id}/data")
        resp.raise_for_status()
        return resp.json()["data"]

    def write(self, instrument_id: str, values: dict[str, Any]) -> None:
        resp = self._client.post(
            f"/api/dashboard/instruments/{instrument_id}/settings",
            json={"values": values},
        )
        resp.raise_for_status()

    def connect(self, instrument_id: str) -> None:
        resp = self._client.post(f"/api/dashboard/instruments/{instrument_id}/connect")
        resp.raise_for_status()

    def get_ui_prefs(self, instrument_id: str) -> dict[str, Any]:
        """This instrument's native-UI display preferences (set via its
        Settings modal in the React Instruments tab — see
        core/config/instrument_ui_prefs.py). Best-effort: returns {} on
        any failure rather than raising, since a missing/unreachable
        prefs endpoint shouldn't block a window from opening."""
        try:
            resp = self._client.get(f"/api/dashboard/instruments/{instrument_id}/ui_prefs")
            resp.raise_for_status()
            return resp.json()["data"]
        except Exception:
            return {}

    def list_workflows(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/workflows")
        resp.raise_for_status()
        return resp.json()["data"]

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Full graph (nodes/edges/metadata) — see GET /api/workflows/{id}."""
        resp = self._client.get(f"/api/workflows/{workflow_id}")
        resp.raise_for_status()
        return resp.json()["data"]

    def get_workflow_script(self, workflow_id: str) -> str | None:
        """Raw script text, or None if this workflow has no script file yet."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/script")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()["data"]["content"]

    def get_workflow_params(self, workflow_id: str) -> dict[str, Any]:
        """This workflow's own tunable parameters (e.g. a scan's
        range/resolution) — distinct from any bound instrument's own
        settings. See GET /api/workflows/{id}/params."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/params")
        resp.raise_for_status()
        return resp.json()["data"]

    def set_workflow_param(self, workflow_id: str, name: str, value: Any) -> Any:
        """Changes one workflow parameter in place. See
        PUT /api/workflows/{id}/params/{name}."""
        resp = self._client.put(f"/api/workflows/{workflow_id}/params/{name}", json={"value": value})
        resp.raise_for_status()
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
        one's already running for this workflow. See
        POST /api/workflows/{id}/optimize/start."""
        resp = self._client.post(
            f"/api/workflows/{workflow_id}/optimize/start",
            json={"axes": axes, "ranges": ranges, "points": points, "points_per_axis": points_per_axis},
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def stop_optimize(self, workflow_id: str) -> None:
        resp = self._client.post(f"/api/workflows/{workflow_id}/optimize/stop")
        resp.raise_for_status()

    def get_optimize_state(self, workflow_id: str) -> dict[str, Any]:
        """{running, progress (the grid so far, live), last_result (the
        final grid once finished), error}. See
        GET /api/workflows/{id}/optimize/state."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/optimize/state")
        resp.raise_for_status()
        return resp.json()["data"]

    def execute_workflow(self, workflow_id: str) -> dict[str, Any]:
        resp = self._client.post(f"/api/workflows/{workflow_id}/execute")
        resp.raise_for_status()
        return resp.json()["data"]

    def stop_workflow(self, workflow_id: str) -> None:
        resp = self._client.post(f"/api/workflows/{workflow_id}/stop")
        resp.raise_for_status()

    def get_workflow_execution_state(self, workflow_id: str) -> dict[str, Any]:
        """Live progress (while running) + last-completed status/results —
        see GET /api/workflows/{id}/execution_state, and
        core/session.py's report_progress() for how "progress" gets
        populated during a run."""
        resp = self._client.get(f"/api/workflows/{workflow_id}/execution_state")
        resp.raise_for_status()
        return resp.json()["data"]

    def close(self) -> None:
        self._client.close()
