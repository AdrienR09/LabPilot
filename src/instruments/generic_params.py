"""Generic, type-level parameter contract — the "metaobject" per
`InstrumentType` that distinguishes GENERIC parameters (same name/getter/
setter convention across every instrument of that type, e.g. every 1D
actuator has "position") from MANUFACTURER-SPECIFIC ones (whatever else a
concrete adapter's own `DeviceSchema` declares beyond that set).

No `DeviceSchema` change needed for this split — it's derived, not stored:
anything in an instance's `schema.settable` beyond its type's generic set
*is* the manufacturer-specific surface, by definition (see
`manufacturer_specific_params`).

This also gives a place to catch a real, previously-silent class of bug:
`AdapterBase.write()`'s `set_<key>` dispatch (instruments/_base.py) is a
naming convention, not a validated contract — nothing previously checked
that a `settable` key actually has a matching `set_<key>` method.
`validate_write_dispatch` does that check directly against a live
instance; `validate_generic_schema` checks the narrower "does this type's
generic contract appear in the schema at all" question.
"""

from __future__ import annotations

from dataclasses import dataclass

from instruments._base import AdapterBase
from instruments.catalog import InstrumentType
from core.device.schema import DeviceSchema

__all__ = [
    "ParamSpec",
    "GENERIC_PARAMS",
    "generic_param_names",
    "manufacturer_specific_params",
    "validate_generic_schema",
    "validate_write_dispatch",
]


@dataclass(frozen=True)
class ParamSpec:
    """One generic parameter's expected shape — just enough to describe
    it generically (dtype/unit), not a full DeviceSchema (limits are
    instance-specific, e.g. each stage's real travel range)."""

    dtype: str
    unit: str = ""


# Per InstrumentType, the parameters every instrument of that type should
# expose via the *same* name (settable unless noted read-only) — this is
# intentionally a small, representative starting set, not an exhaustive
# spec; extend as more instrument types get real generic behavior.
#
# ACTUATOR_ND is deliberately minimal: its per-axis position keys (x/y/z,
# axis1/axis2, ...) vary by device and can't be pinned to one generic
# name the way a single-axis actuator's "position" can.
GENERIC_PARAMS: dict[InstrumentType, dict[str, ParamSpec]] = {
    InstrumentType.ACTUATOR_0D: {
        "position": ParamSpec("int32", "state"),
    },
    InstrumentType.ACTUATOR_1D: {
        "position": ParamSpec("float64", "mm"),
        "velocity": ParamSpec("float64", "mm/s"),
    },
    InstrumentType.ACTUATOR_ND: {
        "velocity": ParamSpec("float64", "mm/s"),
    },
    InstrumentType.DETECTOR_0D: {
        "integration_time_ms": ParamSpec("float64", "ms"),
    },
    InstrumentType.DETECTOR_1D: {
        "integration_time_ms": ParamSpec("float64", "ms"),
    },
    InstrumentType.DETECTOR_2D: {
        "integration_time_ms": ParamSpec("float64", "ms"),
    },
    InstrumentType.DETECTOR_ND: {
        "integration_time_ms": ParamSpec("float64", "ms"),
    },
    InstrumentType.SOURCE: {
        "output_enabled": ParamSpec("bool", ""),
    },
    InstrumentType.GENERIC: {},
}


def generic_param_names(instrument_type: InstrumentType) -> set[str]:
    return set(GENERIC_PARAMS.get(instrument_type, {}).keys())


def manufacturer_specific_params(
    instrument_type: InstrumentType, schema_settable: dict[str, str]
) -> dict[str, str]:
    """Everything in this instance's settable schema beyond its type's
    generic set — the manufacturer-specific parameter surface, derived
    rather than separately declared."""
    generic = generic_param_names(instrument_type)
    return {k: v for k, v in schema_settable.items() if k not in generic}


def validate_generic_schema(instrument_type: InstrumentType, schema: DeviceSchema) -> list[str]:
    """Generic parameter names this type expects that the given schema
    declares in neither readable nor settable — a coverage gap (e.g. an
    ACTUATOR_1D adapter with no "position" at all). Returns [] when clean."""
    declared = set(schema.readable) | set(schema.settable)
    return sorted(name for name in generic_param_names(instrument_type) if name not in declared)


def validate_write_dispatch(adapter: AdapterBase) -> list[str]:
    """Settable schema keys this *instance* has no working way to actually
    set — either no `set_<key>` method (the generic write() dispatch
    convention) and no override of `write()` itself. Needs a live
    instance, not just a schema, since only the instance can be asked
    "does write() actually work" (this is exactly the check that would
    have caught the Keithley2600/6221/SR830/SR860/2400/PM100 adapters all
    advertising settable keys with zero matching set_<key> methods, fixed
    this pass). Returns [] when clean."""
    overrides_write = type(adapter).write is not AdapterBase.write
    if overrides_write:
        return []
    missing = []
    for key in adapter.schema.settable:
        if getattr(adapter, f"set_{key}", None) is None:
            missing.append(key)
    return missing
