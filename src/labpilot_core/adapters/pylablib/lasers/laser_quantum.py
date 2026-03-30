"""Laser Quantum laser adapters for pylablib.

Supports Laser Quantum lasers.

Supported lasers:
- Finesse (DPSS laser)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import LaserQuantum
except ImportError:
    LaserQuantum = None

if LaserQuantum is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class LaserQuantumFinesseAdapter(AdapterBase):
        """Laser Quantum Finesse DPSS laser adapter."""

        def __init__(self, port: str, name: str = "lq_finesse") -> None:
            super().__init__()
            self._port = port
            self._name = name
            self._laser: LaserQuantum.Finesse | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={"power": "float64", "enabled": "bool"},
                settable={"power": "float64", "enabled": "bool"},
                units={"power": "mW"},
                limits={"power": (0.0, 2000.0)},
                tags=["LaserQuantum", "laser", "Finesse", "DPSS"],
            )

        def _connect_sync(self) -> None:
            self._laser = LaserQuantum.Finesse(self._port)

        def _disconnect_sync(self) -> None:
            if self._laser:
                try:
                    self._laser.close()
                except Exception:
                    pass
                self._laser = None

        def _read_sync(self) -> dict[str, Any]:
            if self._laser is None:
                raise RuntimeError("Not connected")

            return {
                "power": float(self._laser.get_power()),
                "enabled": bool(self._laser.is_enabled()),
            }

    adapter_registry.register("laser_quantum_finesse", LaserQuantumFinesseAdapter)
