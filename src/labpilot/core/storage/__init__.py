"""Data storage backends for LabPilot.

`RunStore` is the entry point: it writes each run to HDF5 and indexes it
in the `Catalogue`. See `runs.py` for why both existed unwired until now.
"""

from __future__ import annotations

from labpilot.core.storage.catalogue import Catalogue
from labpilot.core.storage.runs import RunStore, run_data_dir

__all__ = ["Catalogue", "RunStore", "run_data_dir"]
