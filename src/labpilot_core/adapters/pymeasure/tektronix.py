"""Tektronix oscilloscope adapters.

Wraps PyMeasure Tektronix instruments with accurate DeviceSchema.

Supported instruments:
- Tektronix TDS/DPO series oscilloscopes

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.tektronix import TektronixTDS2014
except ImportError:
    TektronixTDS2014 = None

if TektronixTDS2014 is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class TektronixTDSAdapter(AdapterBase):
        """Tektronix TDS series oscilloscope adapter.

        4-channel digital storage oscilloscope with:
        - Bandwidth: 100 MHz - 200 MHz
        - Sample rate: up to 2 GS/s
        - Record length: 2.5k points per channel
        - VISA/GPIB/USB interface

        Args:
            resource: VISA resource string.
            name: Device name.
        """

        def __init__(self, resource: str, name: str = "tektronix_tds") -> None:
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: TektronixTDS2014 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={
                    "ch1_waveform": "ndarray1d",
                    "ch2_waveform": "ndarray1d",
                    "ch3_waveform": "ndarray1d",
                    "ch4_waveform": "ndarray1d",
                },
                settable={
                    "ch1_scale": "float64",  # V/div
                    "ch2_scale": "float64",
                    "timebase": "float64",  # s/div
                },
                units={
                    "ch1_waveform": "V",
                    "ch2_waveform": "V",
                    "ch3_waveform": "V",
                    "ch4_waveform": "V",
                    "ch1_scale": "V/div",
                    "ch2_scale": "V/div",
                    "timebase": "s/div",
                },
                limits={
                    "ch1_scale": (0.001, 10.0),
                    "ch2_scale": (0.001, 10.0),
                    "timebase": (1e-9, 50.0),
                },
                tags=["Tektronix", "oscilloscope", "TDS", "VISA", "GPIB"],
            )

        def _connect_sync(self) -> None:
            self._instrument = TektronixTDS2014(self._resource)

        def _disconnect_sync(self) -> None:
            if self._instrument:
                try:
                    self._instrument.shutdown()
                except Exception:
                    pass
                self._instrument = None

        def _read_sync(self) -> dict[str, Any]:
            if self._instrument is None:
                raise RuntimeError("Not connected")

            return {
                "ch1_waveform": self._instrument.ch1.read_waveform(),
                "ch2_waveform": self._instrument.ch2.read_waveform(),
                "ch3_waveform": self._instrument.ch3.read_waveform(),
                "ch4_waveform": self._instrument.ch4.read_waveform(),
            }

    adapter_registry.register("tektronix_tds", TektronixTDSAdapter)
