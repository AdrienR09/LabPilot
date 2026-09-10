"""Mock RF/microwave signal generator, for ODMR and similar spin-resonance
workflows.

Modeled on qudi's `MicrowaveInterface` (two modes — CW: constant
frequency/power; scan: an equidistant sweep of frequencies at constant
power, stepped by an *external* trigger rather than free-running on its
own timer — "An external hardware trigger must be supplied to actually
step through the scan frequencies", straight from that interface's
docstring) and the real-world PyMoDAQ ODMR plugin
(Montpellier-S2QT/pymodaq_plugins_s2qt_odmr's `DAQ_1DViewer_ODMR`, which
wires an NI card's clock to trigger both this stepping and the photon
counter's gate). `trigger_next()`/`reset_scan()` below stand in for that
external trigger — a future ODMR capability calls them once per
detector-gated point, the same relationship real hardware has.

No pulse/gating logic here — see optical_modulators.py/pulse_rig.py
for that. A real pulsed-ODMR sequence typically gates this source's RF
output with a separate digital line rather than relying on this source's
own scan-mode advance.
"""

from typing import Any

import numpy as np

from labpilot.core.device.parameter import FREQUENCY, POWER, Parameter, ParamRole
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments._base import AdapterBase, adapter_registry


class MockMicrowaveSource(AdapterBase):
    """CW + externally-triggered-scan RF/microwave source mock."""

    def __init__(self, name: str = "mock_microwave_source") -> None:
        super().__init__()
        self._name = name
        # 2.87 GHz: the NV center's zero-field spin splitting — a common,
        # recognizable default for anyone testing an ODMR workflow with this.
        self.cw_frequency = 2.87e9  # Hz
        self.cw_power = -10.0  # dBm
        self.scan_start = 2.82e9  # Hz
        self.scan_stop = 2.92e9  # Hz
        self.scan_points = 101
        self.scan_power = -10.0  # dBm
        self._mode = "cw"  # "cw" | "scan"
        self._output_on = False
        self._scan_index = 0

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="source",
            readable={
                "frequency": "float64", "power": "float64", "mode": "str",
                "output_on": "bool", "scan_index": "int32",
                # Deliberately a different name from settable's "scan_points"
                # (both otherwise mean the same thing) — a shared name here
                # would make MoveControlComponent's move_axes() treat it as
                # a live-commandable position/"move to" axis, which a point
                # count isn't; this is read-only scan progress context.
                "scan_total_points": "int32",
            },
            # The two a sweep actually needs are declared as `Parameter`s
            # so they can be *found* rather than guessed at. `odmr_sweep`
            # used to take the first settable whose name did not contain
            # "power", which a source with a settable phase or modulation
            # depth silently gets wrong — and getting it wrong means
            # sweeping the wrong quantity and fitting a resonance in it.
            parameters=(
                Parameter(
                    "cw_frequency", unit="Hz", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(1e5, 20e9),
                    tags=frozenset({FREQUENCY}),
                    description="Frequency emitted in CW mode",
                ),
                Parameter(
                    "cw_power", unit="dBm", role=ParamRole.SETTING,
                    settable=True, readable=False, limits=(-60.0, 20.0),
                    tags=frozenset({POWER}),
                    description="Level emitted in CW mode",
                ),
            ),
            settable={
                "scan_start": "float64", "scan_stop": "float64",
                "scan_points": "int32", "scan_power": "float64",
            },
            units={
                "frequency": "Hz", "power": "dBm",
                "scan_start": "Hz", "scan_stop": "Hz", "scan_power": "dBm",
            },
            limits={
                "scan_start": (1e5, 20e9), "scan_stop": (1e5, 20e9),
                "scan_points": (2, 10001), "scan_power": (-60.0, 20.0),
            },
            tags=["Mock", "Microwave", "RF", "SignalGenerator", "ODMR"],
            actions=["cw_on", "scan_on", "off", "reset_scan", "trigger_next"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        if self._mode == "cw":
            freq, power = self.cw_frequency, self.cw_power
        else:
            freq, power = self._scan_frequencies()[self._scan_index], self.scan_power
        return {
            "frequency": float(freq), "power": float(power), "mode": self._mode,
            "output_on": self._output_on, "scan_index": self._scan_index,
            "scan_total_points": int(self.scan_points),
        }

    async def set_cw_frequency(self, value: float) -> None:
        self.cw_frequency = float(value)

    async def set_cw_power(self, value: float) -> None:
        self.cw_power = float(value)

    async def set_scan_start(self, value: float) -> None:
        self.scan_start = float(value)

    async def set_scan_stop(self, value: float) -> None:
        self.scan_stop = float(value)

    async def set_scan_points(self, value: int) -> None:
        self.scan_points = int(value)

    async def set_scan_power(self, value: float) -> None:
        self.scan_power = float(value)

    def _scan_frequencies(self) -> np.ndarray:
        return np.linspace(self.scan_start, self.scan_stop, int(self.scan_points))

    # ---- explicit hardware actions (qudi's cw_on/scan_on/off; the S2QT
    # plugin's sweep_on/reset_sweep_position) — not schema "settable"
    # params, since these arm/move hardware rather than set a config value ----

    async def cw_on(self) -> None:
        self._mode = "cw"
        self._output_on = True

    async def scan_on(self) -> None:
        self._mode = "scan"
        self._output_on = True

    async def off(self) -> None:
        self._output_on = False

    async def reset_scan(self) -> None:
        """Rewinds to the first scan point — call before starting a new sweep."""
        self._scan_index = 0

    async def trigger_next(self) -> None:
        """Advances to the next scan point — stands in for the external
        hardware trigger edge a real scan-mode source needs (see module
        docstring). No-op past the last point."""
        if self._scan_index < self.scan_points - 1:
            self._scan_index += 1

    @property
    def is_scanning(self) -> bool:
        return self._mode == "scan" and self._output_on


adapter_registry.register("mock_microwave_source", MockMicrowaveSource)
