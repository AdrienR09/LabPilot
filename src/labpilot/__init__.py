"""LabPilot — a data-acquisition framework for laboratory instruments.

Subpackages:
- `labpilot.core` — session, device schema, workflow engine, storage, server
- `labpilot.instruments` — the instrument adapter library and registry
- `labpilot.ui` — the native Qt desktop shell

Importing this package is deliberately cheap: it pulls in no subpackage, so
`import labpilot` never triggers the adapter discovery pass that
`labpilot.instruments` performs on import.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
