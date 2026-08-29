"""Ergonomic interactive wrapper around core.api_client.LabPilotClient —
what the native IPython console (ui/desktop/console_window.py) binds to
`lp` (see that module's bootstrap startup script). Talks to the live
LabPilot server over the same REST/WebSocket API the desktop app and web
UI use — see api_client.LabPilotClient's docstring for why (instruments
are live hardware handles owned by the server process; an out-of-process
kernel reaches them the same way every other external client does).

Typical console use:

    >>> lp.instruments
    ['mock_xyz_stage_2', 'fake_apd_8', ...]
    >>> lp['fake_apd_8'].read()
    {'counts': 1023.4}
    >>> lp['mock_xyz_stage_2'].write(x=1.0, y=0.5)
    >>> lp.workflows
    ['omniscan', ...]
    >>> wf = lp.workflow('641a113f-...')
    >>> wf.params
    {'AXIS_RANGES': {...}, ...}
    >>> wf.run()
    >>> wf.state()['running']
"""

from __future__ import annotations

import os
import time
from typing import Any

from core.api_client import LabPilotClient


class InstrumentHandle:
    """One instrument, bound to its id — see LabPilotSession.__getitem__."""

    def __init__(self, client: LabPilotClient, instrument_id: str) -> None:
        self._client = client
        self.id = instrument_id

    def read(self) -> dict[str, Any]:
        """Current readable values. Raises if not connected — see .connect()."""
        return self._client.read(self.id)

    def write(self, **values: Any) -> None:
        """Set one or more settable values, e.g. `.write(x=1.0, y=0.5)`."""
        self._client.write(self.id, values)

    def connect(self) -> None:
        self._client.connect(self.id)

    @property
    def schema(self) -> dict[str, Any]:
        """readable/settable parameter names, dtypes, units, limits."""
        return self._client.get_schema(self.id)

    @property
    def status(self) -> dict[str, Any]:
        return self._client.get_instrument(self.id) or {}

    def __repr__(self) -> str:
        return f"<InstrumentHandle {self.id!r}>"


class WorkflowHandle:
    """One workflow, bound to its id — see LabPilotSession.workflow()."""

    def __init__(self, client: LabPilotClient, workflow_id: str) -> None:
        self._client = client
        self.id = workflow_id

    @property
    def params(self) -> dict[str, Any]:
        return self._client.get_workflow_params(self.id)

    def set_param(self, name: str, value: Any) -> Any:
        return self._client.set_workflow_param(self.id, name, value)

    @property
    def script(self) -> str | None:
        return self._client.get_workflow_script(self.id)

    def run(self) -> dict[str, Any]:
        """Starts execution and returns immediately — poll .state() or
        .wait() for progress/completion."""
        return self._client.execute_workflow(self.id)

    def stop(self) -> None:
        self._client.stop_workflow(self.id)

    def state(self) -> dict[str, Any]:
        """Live progress while running, plus the last completed run's
        status/results — see LabPilotClient.get_workflow_execution_state."""
        return self._client.get_workflow_execution_state(self.id)

    def wait(self, poll_interval: float = 0.5, timeout: float | None = None) -> dict[str, Any]:
        """Blocks until the current/most recent run stops running, then
        returns the final state. Convenient for a notebook cell that
        should finish only once the scan has (`wf.run(); wf.wait()`)."""
        start = time.monotonic()
        while True:
            state = self.state()
            if not state.get("running"):
                return state
            if timeout is not None and time.monotonic() - start > timeout:
                raise TimeoutError(f"Workflow {self.id} still running after {timeout}s")
            time.sleep(poll_interval)

    def __repr__(self) -> str:
        return f"<WorkflowHandle {self.id!r}>"


class LabPilotSession:
    """Entry point for interactive (notebook/IPython) use — see module
    docstring. Wraps a LabPilotClient with nicer ergonomics; use
    `.client` directly for anything not exposed here."""

    def __init__(self, base_url: str | None = None) -> None:
        base_url = base_url or os.environ.get("LABPILOT_URL", "http://localhost:8000")
        self.client = LabPilotClient(base_url)

    @property
    def base_url(self) -> str:
        return self.client.base_url

    @property
    def instruments(self) -> list[str]:
        """Every registered instrument's id."""
        return [inst["id"] for inst in self.client.list_instruments()]

    def __getitem__(self, instrument_id: str) -> InstrumentHandle:
        return InstrumentHandle(self.client, instrument_id)

    @property
    def workflows(self) -> list[str]:
        """Every loaded workflow's id."""
        return [wf["id"] for wf in self.client.list_workflows()]

    def workflow(self, workflow_id: str) -> WorkflowHandle:
        return WorkflowHandle(self.client, workflow_id)

    def __repr__(self) -> str:
        return f"<LabPilotSession {self.base_url!r}>"
