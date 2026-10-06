"""A failed connect says why in the terminal, not only in the HTTP body.

Every hardware failure the dashboard meets becomes an HTTPException whose
`detail` carries the reason. That is right for the caller and was useless at
the bench: uvicorn's access log prints the status line and never the body, so
bringing up a Mad City Labs stage with its vendor DLL missing looked like

    POST /api/dashboard/instruments/MCL_Nano_Drive/connect 502 Bad Gateway

four times over, with the explanation — which named the DLL, the paths tried
and the fact that it ships with MCL's driver rather than from PyPI — nowhere
a person could see it.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from labpilot.core.api import dashboard as dashboard_module


@pytest.fixture
def rest(monkeypatch):
    """The connect route over a manager that fails the way a missing
    vendor library does."""

    reason = (
        "Talking to a Mad City Labs Nano-Drive needs Mad City Labs' own library, "
        "which comes with their driver installation rather than from PyPI"
    )

    class _Manager:
        async def connect_instrument(self, instrument_id):
            raise ImportError(reason)

        async def disconnect_instrument(self, instrument_id):
            raise OSError("the stage stopped answering")

    monkeypatch.setattr(dashboard_module, "get_dashboard_manager", _Manager)

    app = FastAPI()
    app.include_router(dashboard_module.router)
    return TestClient(app, raise_server_exceptions=False), reason


def test_the_caller_still_gets_the_reason_in_the_body(rest):
    client, reason = rest
    response = client.post("/api/dashboard/instruments/stage/connect")

    assert response.status_code == 502
    assert reason in response.json()["detail"]


def test_the_reason_is_logged_as_well(rest, caplog):
    client, reason = rest
    with caplog.at_level(logging.WARNING, logger=dashboard_module.logger.name):
        client.post("/api/dashboard/instruments/stage/connect")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert reason in logged
    assert "stage" in logged


def test_the_log_carries_the_traceback(rest, caplog):
    """`exc_info` is what turns "it failed" into a line of vendor code."""
    client, _ = rest
    with caplog.at_level(logging.WARNING, logger=dashboard_module.logger.name):
        client.post("/api/dashboard/instruments/stage/connect")

    assert any(record.exc_info for record in caplog.records)


def test_a_failed_disconnect_is_logged_too(rest, caplog):
    client, _ = rest
    with caplog.at_level(logging.WARNING, logger=dashboard_module.logger.name):
        response = client.post("/api/dashboard/instruments/stage/disconnect")

    assert response.status_code == 502
    assert "stopped answering" in "\n".join(r.getMessage() for r in caplog.records)


# --- And it has to be visible once uvicorn owns the logging ----------------


def test_the_server_routes_labpilot_logs_through_uvicorns_handler():
    """Otherwise a warning reaches stderr only via `logging.lastResort`,
    as a bare message with no level or timestamp beside uvicorn's own
    formatted lines — present, but not obviously part of the log."""
    from labpilot.core.cli import _log_config

    config = _log_config("info")
    assert config["loggers"]["labpilot"]["handlers"] == ["default"]
    assert config["loggers"]["labpilot"]["level"] == "INFO"
    # uvicorn's own loggers must survive the addition.
    assert "uvicorn.access" in config["loggers"]


def test_the_log_config_does_not_mutate_uvicorns_module_level_dict():
    """It is a module global; editing it in place would leak into any other
    uvicorn in the process, including the one `labpilot app` spawns."""
    import uvicorn.config

    from labpilot.core.cli import _log_config

    _log_config("debug")
    assert "labpilot" not in uvicorn.config.LOGGING_CONFIG["loggers"]


def test_a_dashboard_warning_is_emitted_by_that_configuration(capsys):
    """The end of the chain: apply the config, log, read stderr."""
    import logging.config

    from labpilot.core.cli import _log_config

    package_logger = logging.getLogger("labpilot")
    saved = (package_logger.handlers[:], package_logger.level, package_logger.propagate)
    try:
        logging.config.dictConfig(_log_config("info"))
        dashboard_module.logger.warning("Connecting %s failed: %s", "stage", "no Madlib.dll")
        assert "no Madlib.dll" in capsys.readouterr().err
    finally:
        package_logger.handlers, package_logger.level, package_logger.propagate = saved
