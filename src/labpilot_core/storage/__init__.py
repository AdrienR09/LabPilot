"""Data storage backends for LabPilot."""

from __future__ import annotations

from labpilot_core.storage.catalogue import Catalogue
from labpilot_core.storage.hdf5 import HDF5Writer

__all__ = ["Catalogue", "HDF5Writer"]
