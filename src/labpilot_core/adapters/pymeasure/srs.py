"""Stanford Research Systems (SRS) lock-in amplifier adapters.

Wraps PyMeasure SRS instruments with accurate DeviceSchema.

Supported instruments:
- SR830 DSP Lock-in (1 mHz - 102.4 kHz, analog input)
- SR860 Network Lock-in (1 mHz - 500 kHz, digital signal processing)

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.srs import SR830, SR860
except ImportError:
    # pymeasure not installed - skip these adapters
    SR830 = None
    SR860 = None

if SR830 is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class SR830Adapter(AdapterBase):
        """SR830 DSP Lock-in Amplifier adapter.

        Dual-phase lock-in amplifier with:
        - Frequency range: 1 mHz - 102.4 kHz
        - Voltage sensitivity: 2 nV - 1 V (full scale)
        - Current sensitivity: 2 fA - 1 µA (full scale)
        - Dynamic reserve: up to 100 dB
        - Time constants: 10 µs - 30 ks

        Args:
            resource: VISA resource string (e.g., "GPIB::8", "  TCPIP::192.168.1.10::INSTR").
            name: Device name (defaults to "sr830").

        Example:
            >>> lockin = SR830Adapter(resource="GPIB::8", name="lockin")
            >>> await lockin.connect()
            >>> data = await lockin.read()
            >>> print(f"X={data['x']:.3e} V, Y={data['y']:.3e} V")
        """

        def __init__(self, resource: str, name: str = "sr830") -> None:
            """Initialize adapter.

            Args:
                resource: VISA resource string.
                name: Device name for session registry.
            """
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: SR830 | None = None

        @property
        def schema(self) -> DeviceSchema:
            """Device schema with accurate parameters."""
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={
                    "x": "float64",  # In-phase component (V or A)
                    "y": "float64",  # Quadrature component (V or A)
                    "r": "float64",  # Magnitude (V or A)
                    "theta": "float64",  # Phase (degrees)
                    "frequency": "float64",  # Reference frequency (Hz)
                },
                settable={
                    "frequency": "float64",  # Reference frequency (Hz)
                    "amplitude": "float64",  # Sine output amplitude (V)
                    "phase": "float64",  # Reference phase shift (degrees)
                    "time_constant": "float64",  # Filter time constant (s)
                    "sensitivity": "float64",  # Input sensitivity (V)
                },
                units={
                    "x": "V",
                    "y": "V",
                    "r": "V",
                    "theta": "deg",
                    "frequency": "Hz",
                    "amplitude": "V",
                    "phase": "deg",
                    "time_constant": "s",
                    "sensitivity": "V",
                },
                limits={
                    "frequency": (0.001, 102000.0),  # 1 mHz - 102.4 kHz
                    "amplitude": (0.004, 5.0),  # 4 mV - 5 V
                    "phase": (-360.0, 360.0),
                    "time_constant": (1e-5, 30000.0),  # 10 µs - 30 ks
                    "sensitivity": (2e-9, 1.0),  # 2 nV - 1 V
                },
                tags=["SRS", "lock-in", "amplifier", "VISA", "GPIB"],
            )

        def _connect_sync(self) -> None:
            """Connect via VISA."""
            self._instrument = SR830(self._resource)

        def _disconnect_sync(self) -> None:
            """Disconnect."""
            if self._instrument is not None:
                try:
                    self._instrument.shutdown()
                except Exception:
                    pass
                self._instrument = None

        def _read_sync(self) -> dict[str, Any]:
            """Read X, Y, R, theta, and frequency."""
            if self._instrument is None:
                raise RuntimeError("Adapter not connected")

            return {
                "x": float(self._instrument.x),
                "y": float(self._instrument.y),
                "r": float(self._instrument.magnitude),
                "theta": float(self._instrument.theta),
                "frequency": float(self._instrument.frequency),
            }

        def _self_test_sync(self) -> None:
            """Test connectivity by reading ID."""
            if self._instrument is None:
                raise RuntimeError("Not connected")
            _ = self._instrument.id

    class SR860Adapter(AdapterBase):
        """SR860 Network Lock-in Amplifier adapter.

        Modern lock-in with enhanced digital processing:
        - Frequency range: 1 mHz - 500 kHz
        - Voltage input: 1 nV - 1 V (full scale)
        - Current input: 1 fA - 1 µA (full scale)
        - 16-bit dual ADCs, 125 MHz sampling
        - Ethernet and USB interfaces

        Args:
            resource: VISA resource string.
            name: Device name (defaults to "sr860").
        """

        def __init__(self, resource: str, name: str = "sr860") -> None:
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: SR860 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="detector",
                readable={
                    "x": "float64",
                    "y": "float64",
                    "r": "float64",
                    "theta": "float64",
                    "frequency": "float64",
                },
                settable={
                    "frequency": "float64",
                    "amplitude": "float64",
                    "phase": "float64",
                    "time_constant": "float64",
                    "sensitivity": "float64",
                },
                units={
                    "x": "V",
                    "y": "V",
                    "r": "V",
                    "theta": "deg",
                    "frequency": "Hz",
                    "amplitude": "V",
                    "phase": "deg",
                    "time_constant": "s",
                    "sensitivity": "V",
                },
                limits={
                    "frequency": (0.001, 500000.0),  # 1 mHz - 500 kHz
                    "amplitude": (0.001, 2.0),  # 1 mV - 2 V
                    "phase": (-360.0, 360.0),
                    "time_constant": (1e-6, 30000.0),  # 1 µs - 30 ks
                    "sensitivity": (1e-9, 1.0),  # 1 nV - 1 V
                },
                tags=["SRS", "lock-in", "amplifier", "VISA", "Ethernet", "USB"],
            )

        def _connect_sync(self) -> None:
            self._instrument = SR860(self._resource)

        def _disconnect_sync(self) -> None:
            if self._instrument is not None:
                try:
                    self._instrument.shutdown()
                except Exception:
                    pass
                self._instrument = None

        def _read_sync(self) -> dict[str, Any]:
            if self._instrument is None:
                raise RuntimeError("Not connected")

            return {
                "x": float(self._instrument.x),
                "y": float(self._instrument.y),
                "r": float(self._instrument.magnitude),
                "theta": float(self._instrument.theta),
                "frequency": float(self._instrument.frequency),
            }

    # Register adapters
    adapter_registry.register("srs_sr830", SR830Adapter)
    adapter_registry.register("srs_sr860", SR860Adapter)
