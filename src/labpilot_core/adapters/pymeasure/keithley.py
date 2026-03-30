"""Keithley SMU (Source Measure Unit) adapters.

Wraps PyMeasure Keithley instruments with accurate DeviceSchema.

Supported instruments:
- Keithley 2400 SourceMeter (±210V, ±1.05A, 22W)
- Keithley 2600 Series SourceMeter
- Keithley 6221 Current Source

Attribution: Wraps PyMeasure by Colin Jermain et al. — MIT licence
"""

from __future__ import annotations

from typing import Any

try:
    from pymeasure.instruments.keithley import Keithley2400, Keithley2600, Keithley6221
except ImportError:
    # pymeasure not installed - skip these adapters
    Keithley2400 = None
    Keithley2600 = None
    Keithley6221 = None

if Keithley2400 is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.schema import DeviceSchema

    class Keithley2400Adapter(AdapterBase):
        """Keithley 2400 SourceMeter adapter.

        Precision source-measure unit with:
        - Voltage source: ±210V (210W compliance)
        - Current source: ±1.05A (21W compliance)
        - 4-wire sensing (Kelvin connections)
        - 6.5-digit measurement resolution

        Args:
            resource: VISA resource string (e.g., "GPIB::24", "USB0::...").
            name: Optional custom device name (defaults to "keithley_2400").

        Example:
            >>> k2400 = Keithley2400Adapter(resource="GPIB::24", name="smu")
            >>> await k2400.connect()
            >>> await k2400.set(0.5)  # Set 0.5V
            >>> data = await k2400.read()  # Measure current
            >>> print(f"Current: {data['current']} A")
        """

        def __init__(self, resource: str, name: str = "keithley_2400") -> None:
            """Initialize adapter.

            Args:
                resource: VISA resource string.
                name: Device name for session registry.
            """
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: Keithley2400 | None = None

        @property
        def schema(self) -> DeviceSchema:
            """Device schema with accurate limits and units."""
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={
                    "voltage": "float64",
                    "current": "float64",
                    "resistance": "float64",
                },
                settable={
                    "voltage": "float64",
                    "current": "float64",
                    "current_range": "float64",
                    "voltage_range": "float64",
                    "compliance_current": "float64",
                    "compliance_voltage": "float64",
                },
                units={
                    "voltage": "V",
                    "current": "A",
                    "resistance": "Ω",
                    "current_range": "A",
                    "voltage_range": "V",
                    "compliance_current": "A",
                    "compliance_voltage": "V",
                },
                limits={
                    "voltage": (-210.0, 210.0),
                    "current": (-1.05, 1.05),
                    "compliance_current": (1e-9, 1.05),
                    "compliance_voltage": (0.1, 210.0),
                },
                tags=["Keithley", "SMU", "SourceMeter", "VISA", "GPIB"],
            )

        def _connect_sync(self) -> None:
            """Connect via VISA and configure for basic operation."""
            self._instrument = Keithley2400(self._resource)
            self._instrument.reset()
            self._instrument.use_front_terminals()
            self._instrument.measure_voltage()
            self._instrument.measure_current()

        def _disconnect_sync(self) -> None:
            """Disconnect and disable output."""
            if self._instrument is not None:
                try:
                    self._instrument.disable_source()
                    self._instrument.shutdown()
                except Exception:
                    pass
                self._instrument = None

        def _read_sync(self) -> dict[str, Any]:
            """Read voltage, current, and resistance."""
            if self._instrument is None:
                raise RuntimeError("Adapter not connected")

            return {
                "voltage": float(self._instrument.voltage),
                "current": float(self._instrument.current),
                "resistance": float(self._instrument.resistance),
            }

        def _stage_sync(self) -> None:
            """Enable source output."""
            if self._instrument is not None:
                self._instrument.enable_source()

        def _unstage_sync(self) -> None:
            """Disable source output."""
            if self._instrument is not None:
                self._instrument.disable_source()

        def _self_test_sync(self) -> None:
            """Test connectivity by reading instrument ID."""
            if self._instrument is None:
                raise RuntimeError("Adapter not connected")
            _ = self._instrument.id

    # --- Additional Keithley adapters ---

    class Keithley2600Adapter(AdapterBase):
        """Keithley 2600 Series SourceMeter adapter.

        Dual-channel SMU with scripting capability.

        Args:
            resource: VISA resource string.
            channel: Channel to control ("a" or "b").
            name: Device name.
        """

        def __init__(
            self, resource: str, channel: str = "a", name: str = "keithley_2600"
        ) -> None:
            super().__init__()
            self._resource = resource
            self._channel = channel
            self._name = name
            self._instrument: Keithley2600 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={"voltage": "float64", "current": "float64"},
                settable={"voltage": "float64", "current": "float64"},
                units={"voltage": "V", "current": "A"},
                limits={"voltage": (-200.0, 200.0), "current": (-1.5, 1.5)},
                tags=["Keithley", "SMU", "SourceMeter", "VISA"],
            )

        def _connect_sync(self) -> None:
            self._instrument = Keithley2600(self._resource)
            self._instrument.reset()

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

            channel = getattr(self._instrument, f"ch_{self._channel}")
            return {
                "voltage": float(channel.voltage),
                "current": float(channel.current),
            }

    class Keithley6221Adapter(AdapterBase):
        """Keithley 6221 Current Source adapter.

        Precision DC and AC current source (±105 mA).

        Args:
            resource: VISA resource string.
            name: Device name.
        """

        def __init__(self, resource: str, name: str = "keithley_6221") -> None:
            super().__init__()
            self._resource = resource
            self._name = name
            self._instrument: Keithley6221 | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="source",
                readable={"current": "float64"},
                settable={"current": "float64", "compliance_voltage": "float64"},
                units={"current": "A", "compliance_voltage": "V"},
                limits={"current": (-0.105, 0.105), "compliance_voltage": (0.1, 105.0)},
                tags=["Keithley", "CurrentSource", "VISA", "GPIB"],
            )

        def _connect_sync(self) -> None:
            self._instrument = Keithley6221(self._resource)
            self._instrument.reset()

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
            return {"current": float(self._instrument.source_current)}

    # Register adapters
    adapter_registry.register("keithley_2400", Keithley2400Adapter)
    adapter_registry.register("keithley_2600", Keithley2600Adapter)
    adapter_registry.register("keithley_6221", Keithley6221Adapter)
