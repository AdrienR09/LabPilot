"""Device schema and metadata model.

Provides structured metadata for hardware devices, enabling auto-GUI generation,
validation, and runtime introspection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["DeviceSchema"]


class DeviceSchema(BaseModel):
    """Pydantic model describing device capabilities and metadata.

    Used for:
    - Runtime type checking (is this device readable? movable?)
    - Auto-GUI generation (what axes exist? what are their limits?)
    - Data validation (are setpoint values in bounds?)
    - Storage metadata (what units are used?)

    Example:
        >>> schema = DeviceSchema(
        ...     name="ocean_insight_usb2000",
        ...     kind="detector",
        ...     readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
        ...     settable={"integration_time_ms": "float64"},
        ...     units={"wavelengths": "nm", "intensities": "counts"},
        ...     limits={"integration_time_ms": (1.0, 60000.0)},
        ...     trigger_modes=["software", "hardware"],
        ...     tags=["spectroscopy", "VISA", "USB"],
        ... )
    """

    name: str = Field(
        description="Unique device identifier (e.g., 'thorlabs_mdt693b_x')"
    )
    kind: Literal["detector", "motor", "source", "counter", "generic"] = Field(
        description="Device category for semantic grouping"
    )
    readable: dict[str, str] = Field(
        default_factory=dict,
        description="Readable axes and their dtypes (e.g., {'position': 'float64'})",
    )
    settable: dict[str, str] = Field(
        default_factory=dict,
        description="Settable parameters and their dtypes",
    )
    units: dict[str, str] = Field(
        default_factory=dict,
        description="Physical units for each axis (e.g., {'position': 'um'})",
    )
    limits: dict[str, tuple[float, float]] = Field(
        default_factory=dict,
        description="Min/max bounds for settable parameters",
    )
    trigger_modes: list[str] = Field(
        default_factory=list,
        description="Supported trigger modes (e.g., ['software', 'hardware'])",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags (e.g., ['spectroscopy', 'NI', 'VISA'])",
    )

    class Config:
        """Pydantic v2 configuration."""

        frozen = True  # Make instances immutable after creation
        extra = "forbid"  # Reject unknown fields
