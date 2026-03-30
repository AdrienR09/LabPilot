"""Scan plan models with TOML serialisation.

Plans are fully typed Pydantic models that can be saved/loaded as TOML files
for reproducibility and collaboration.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import BaseModel, Field

__all__ = ["ScanPlan"]


class ScanPlan(BaseModel):
    """Base model for 1D scan plans.

    Serialisable to/from TOML for human-readable, version-controllable plans.
    Device names reference Session.devices registry (resolved at runtime).

    Example TOML:
        name = "wavelength_scan"
        motor = "tunable_laser"
        detector = "photodiode"
        start = 1520.0
        stop = 1580.0
        num = 200
        dwell = 0.05

        [metadata]
        sample = "fiber_bragg_grating_01"
        temperature_K = 295

    Example usage:
        >>> plan = ScanPlan(
        ...     name="wavelength_scan",
        ...     motor="tunable_laser",
        ...     detector="photodiode",
        ...     start=1520.0,
        ...     stop=1580.0,
        ...     num=200,
        ... )
        >>> plan.to_toml("scan_plan.toml")
        >>> loaded = ScanPlan.from_toml("scan_plan.toml")
    """

    name: str = Field(description="Human-readable plan identifier")
    motor: str = Field(description="Motor device name (from Session registry)")
    detector: str = Field(description="Detector device name (from Session registry)")
    start: float = Field(description="Scan start position")
    stop: float = Field(description="Scan stop position")
    num: int = Field(ge=1, description="Number of scan points")
    dwell: float = Field(default=0.1, ge=0.0, description="Dwell time per point (s)")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="User-defined metadata"
    )

    def to_toml(self, path: str | Path) -> None:
        """Save plan to TOML file.

        Args:
            path: Output file path.

        Example:
            >>> plan.to_toml("experiments/2024-03-22_wavelength_scan.toml")
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("wb") as f:
            tomli_w.dump(self.model_dump(), f)

    @classmethod
    def from_toml(cls, path: str | Path) -> ScanPlan:
        """Load plan from TOML file.

        Args:
            path: Input file path.

        Returns:
            ScanPlan instance loaded from TOML.

        Raises:
            FileNotFoundError: If path does not exist.
            ValueError: If TOML is invalid or missing required fields.

        Example:
            >>> plan = ScanPlan.from_toml("experiments/archived_scan.toml")
        """
        path = Path(path)
        with path.open("rb") as f:
            data = tomllib.load(f)

        return cls.model_validate(data)

    class Config:
        """Pydantic v2 configuration."""

        extra = "forbid"  # Reject unknown fields for strict validation
