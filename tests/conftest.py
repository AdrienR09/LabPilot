"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest


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
