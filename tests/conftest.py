"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
import tempfile

import pytest

# Redirect all persistent LabPilot state into a throwaway directory for the
# whole test session, before any test module imports the config layer.
#
# Without this the suite writes into the developer's real ~/.labpilot: anything
# that exercises the dashboard manager persists the instruments it creates into
# the active instrument set, which is then loaded back by the next real server
# start. A test that connected a device left that device in the user's lab
# configuration permanently.
_TMP_HOME = tempfile.mkdtemp(prefix="labpilot-test-home-")
os.environ["LABPILOT_HOME"] = _TMP_HOME


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend for pytest-anyio."""
    return "asyncio"


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "hardware: tests that require physical hardware",
    )
    config.addinivalue_line(
        "markers",
        "visa: tests that require VISA instruments",
    )
    config.addinivalue_line(
        "markers",
        "ni: tests that require National Instruments hardware",
    )
    config.addinivalue_line(
        "markers",
        "serial: tests that require serial devices",
    )
    config.addinivalue_line(
        "markers",
        "epics: tests that require EPICS IOCs",
    )
