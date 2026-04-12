"""
LabPilot Instruments Package

Comprehensive instrument library separate from core framework.
Organized by manufacturer and instrument type for easy discovery and adaptation.

Structure:
- adapters/: Per-manufacturer adapter implementations
- catalog/: Instrument metadata and discovery

This separation allows the instruments package to grow independently
while keeping labpilot_core focused on framework functionality.
"""

from labpilot_instruments.catalog import (
    INSTRUMENT_CATALOG,
    InstrumentType,
    InstrumentBackend,
    get_instruments_by_type,
    get_instruments_by_backend,
    get_instruments_by_manufacturer,
    get_instruments_by_tag,
    find_adapter,
)

__all__ = [
    "INSTRUMENT_CATALOG",
    "InstrumentType",
    "InstrumentBackend",
    "get_instruments_by_type",
    "get_instruments_by_backend",
    "get_instruments_by_manufacturer",
    "get_instruments_by_tag",
    "find_adapter",
]
