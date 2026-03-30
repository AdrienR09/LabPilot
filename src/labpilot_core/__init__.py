"""LabPilot Core: Next-generation Python data acquisition framework for laboratory instruments.

Example usage:
    >>> import anyio
    >>> from labpilot_core import Session
    >>> from labpilot_core.plans import ScanPlan
    >>> from labpilot_core.plans.scan import scan
    >>>
    >>> async def main():
    ...     session = await Session.load("lab_config.toml")
    ...     plan = ScanPlan(name="my_scan", motor="stage", detector="spec", ...)
    ...     async for event in scan(plan, motor, detector, session.bus):
    ...         print(event.data)
    >>>
    >>> anyio.run(main)
"""

from __future__ import annotations

from labpilot_core.core.events import Event, EventBus, EventKind
from labpilot_core.core.session import Session

__version__ = "0.1.0"

__all__ = [
    "Event",
    "EventBus",
    "EventKind",
    "Session",
    "__version__",
]
