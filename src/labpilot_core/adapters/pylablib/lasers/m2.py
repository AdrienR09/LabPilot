"""M2 laser adapters for pylablib.

Supports M2 Solstis tunable lasers.

Supported lasers:
- M2 Solstis (wavelength-tunable Ti:Sapphire laser)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import M2
except ImportError:
    M2 = None

if M2 is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class M2SolstisAdapter(AdapterBase):
        """M2 Solstis tunable laser adapter.

        Wavelength-tunable Ti:Sapphire CW laser with:
        - Tuning range: typically 710-980 nm
        - Output power: up to 4.5 W
        - Linewidth: < 100 kHz
        - TCP/IP control

        Args:
            host: IP address of laser controller.
            port: TCP port (default 39933).
            name: Device name.
        """

        def __init__(self, host: str, port: int = 39933, name: str = "m2_solstis") -> None:
            super().__init__()
            self._host = host
            self._port = port
            self._name = name
            self._laser: M2.Solstis | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={
                    "wavelength": "float64",
                    "power": "float64",
                    "status": "str",
                },
                settable={
                    "wavelength": "float64",
                   "power": "float64",
                },
                units={"wavelength": "nm", "power": "W"},
                limits={
                    "wavelength": (710.0, 980.0),
                    "power": (0.0, 4.5),
                },
                tags=["M2", "laser", "Solstis", "tunable", "TCP/IP"],
            )

        def _connect_sync(self) -> None:
            self._laser = M2.Solstis(addr=(self._host, self._port))

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
                "wavelength": float(self._laser.get_wavelength()),
                "power": float(self._laser.get_power()),
                "status": str(self._laser.get_status()),
            }

    adapter_registry.register("m2_solstis", M2SolstisAdapter)
