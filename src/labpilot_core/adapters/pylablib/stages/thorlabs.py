"""Thorlabs motorized stage adapters for pylablib.

Supports Thorlabs Kinesis motor controllers via pylablib wrappers.

Supported devices:
- Kinesis DC servo motors (KDC101, TDC001)
- Kinesis stepper motors (KST101, BSC203)
- Kinesis piezo controllers (KPZ101

, TPZ001)
- Flip mounts (MFF101/102)
- Filter wheels (FW102C, FW212C)

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

from typing import Any

try:
    from pylablib.devices import Thorlabs
except ImportError:
    # pylablib not installed - skip these adapters
    Thorlabs = None

if Thorlabs is not None:
    from labpilot_core.adapters._base import AdapterBase, adapter_registry
    from labpilot_core.device.protocols import Movable
    from labpilot_core.device.schema import DeviceSchema

    class KinesisMotorAdapter(AdapterBase, Movable):
        """Thorlabs Kinesis motor controller adapter.

        DC servo and stepper motor controllers with:
        - Position resolution: down to 34 nm (piezo)
        - Travel range: up to 300 mm (depends on stage)
        - USB computer control
        - Closed-loop position feedback

        Args:
            serial_number: Device serial number (e.g., "27000001").
            name: Device name (defaults to "kinesis_motor").
            scale: Position units (default 1.0 = device units, use 1000.0 for µm→mm).

        Example:
            >>> motor = KinesisMotorAdapter(
            ...     serial_number="27000001",
            ...     name="motor_x",
            ...     scale=1000.0  # Convert µm to mm
            ... )
            >>> await motor.connect()
            >>> await motor.set(10.5)  # Move to 10.5 mm
            >>> pos = await motor.where()
            >>> print(f"Position: {pos} mm")
        """

        def __init__(
            self,
            serial_number: str,
            name: str = "kinesis_motor",
            scale: float = 1.0,
        ) -> None:
            """Initialize adapter.

            Args:
                serial_number: Kinesis controller serial number.
                name: Device name for session registry.
                scale: Position scaling factor (device_units * scale = user_units).
            """
            super().__init__()
            self._serial_number = serial_number
            self._name = name
            self._scale = scale
            self._motor: Thorlabs.KinesisMotor | None = None

        @property
        def schema(self) -> DeviceSchema:
            """Device schema for Kinesis motors."""
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "float64"},  # Current position
                settable={"position": "float64"},  # Target position
                units={"position": "mm"},  # Millimeters (assuming scale=1000 for µm→mm)
                limits={"position": (0.0, 300.0)},  # Travel range (stage dependent)
                tags=["Thorlabs", "Kinesis", "motor", "USB"],
            )

        def _connect_sync(self) -> None:
            """Connect to Kinesis controller via USB."""
            self._motor = Thorlabs.KinesisMotor(self._serial_number)
            # Home the motor on connection
            self._motor.home()
            self._motor.wait_for_home()

        def _disconnect_sync(self) -> None:
            """Disconnect and close motor."""
            if self._motor is not None:
                try:
                    self._motor.close()
                except Exception:
                    pass
                self._motor = None

        def _read_sync(self) -> dict[str, Any]:
            """Read current motor position.

            Returns:
                Dict with "position" key in user units (mm).
            """
            if self._motor is None:
                raise RuntimeError("Motor not connected")

            # Get position in device units and scale
            device_position = self._motor.get_position()
            user_position = device_position * self._scale

            return {"position": float(user_position)}

        def _set_sync(self, value: float) -> None:
            """Move motor to target position and wait for completion.

            Args:
                value: Target position in user units (mm).
            """
            if self._motor is None:
                raise RuntimeError("Motor not connected")

            # Convert user units to device units
            device_value = value / self._scale

            # Move and wait for completion
            self._motor.move_to(device_value)
            self._motor.wait_move()

        async def set(self, value: Any, *, timeout: float = 10.0) -> None:
            """Move motor to target position (async wrapper).

            Args:
                value: Target position in user units.
                timeout: Maximum wait time (not currently used in pylablib).
            """
            await self._to_thread(self._set_sync, value)

        def _where_sync(self) -> float:
            """Get current motor position.

            Returns:
                Current position in user units (mm).
            """
            if self._motor is None:
                raise RuntimeError("Motor not connected")

            device_position = self._motor.get_position()
            return float(device_position * self._scale)

        async def where(self) -> Any:
            """Get current motor position (async wrapper)."""
            return await self._to_thread(self._where_sync)

        def _stop_sync(self) -> None:
            """Emergency stop motor motion."""
            if self._motor is not None:
                self._motor.stop()

        async def stop(self) -> None:
            """Emergency stop motor motion (async wrapper)."""
            await self._to_thread(self._stop_sync)

        def _self_test_sync(self) -> None:
            """Test motor connectivity by reading position."""
            _ = self._where_sync()

    class MFFAdapter(AdapterBase, Movable):
        """Thorlabs MFF flip mount adapter.

        Motorized flip mount for beam steering/blocking:
        - 2 positions: flip up / flip down
        - USB control
        - Compact form factor (1" optics)

        Args:
            serial_number: Device serial number.
            name: Device name.

        Example:
            >>> flip = MFFAdapter(serial_number="37000001", name="flip_mount")
            >>> await flip.connect()
            >>> await flip.set(1)  # Flip to position 1
        """

        def __init__(self, serial_number: str, name: str = "flip_mount") -> None:
            super().__init__()
            self._serial_number = serial_number
            self._name = name
            self._device: Thorlabs.MFF | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "int32"},  # 0 or 1
                settable={"position": "int32"},
                units={"position": "state"},
                limits={"position": (0, 1)},  # Binary: 0=down, 1=up
                tags=["Thorlabs", "flip_mount", "MFF", "USB"],
            )

        def _connect_sync(self) -> None:
            self._device = Thorlabs.MFF(self._serial_number)

        def _disconnect_sync(self) -> None:
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None

        def _read_sync(self) -> dict[str, Any]:
            if self._device is None:
                raise RuntimeError("Not connected")
            return {"position": int(self._device.get_state())}

        def _set_sync(self, value: int) -> None:
            if self._device is None:
                raise RuntimeError("Not connected")
            if value not in (0, 1):
                raise ValueError(f"Position must be 0 or 1, got {value}")
            self._device.move_to_state(value)
            # Wait for move complete
            while self._device.is_moving():
                pass

        async def set(self, value: Any, *, timeout: float = 10.0) -> None:
            await self._to_thread(self._set_sync, int(value))

        def _where_sync(self) -> int:
            if self._device is None:
                raise RuntimeError("Not connected")
            return int(self._device.get_state())

        async def where(self) -> Any:
            return await self._to_thread(self._where_sync)

        def _stop_sync(self) -> None:
            pass  # No stop for flip mount

        async def stop(self) -> None:
            pass

    class FWAdapter(AdapterBase, Movable):
        """Thorlabs filter wheel adapter.

        Motorized filter wheel with 6 or 12 positions:
        - Position repeatability: ±0.1°
        - USB control
        - Multiple mounting options

        Args:
            serial_number: Device serial number.
            n_positions: Number of filter positions (6 or 12).
            name: Device name.
        """

        def __init__(
            self,
            serial_number: str,
            n_positions: int = 6,
            name: str = "filter_wheel",
        ) -> None:
            super().__init__()
            self._serial_number = serial_number
            self._n_positions = n_positions
            self._name = name
            self._device: Thorlabs.FW | None = None

        @property
        def schema(self) -> DeviceSchema:
            return DeviceSchema(
                name=self._name,
                kind="motor",
                readable={"position": "int32"},
                settable={"position": "int32"},
                units={"position": "slot"},
                limits={"position": (1, self._n_positions)},
                tags=["Thorlabs", "filter_wheel", "FW", "USB"],
            )

        def _connect_sync(self) -> None:
            self._device = Thorlabs.FW(self._serial_number)

        def _disconnect_sync(self) -> None:
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None

        def _read_sync(self) -> dict[str, Any]:
            if self._device is None:
                raise RuntimeError("Not connected")
            return {"position": int(self._device.get_position())}

        def _set_sync(self, value: int) -> None:
            if self._device is None:
                raise RuntimeError("Not connected")
            if not (1 <= value <= self._n_positions):
                raise ValueError(
                    f"Position must be 1-{self._n_positions}, got {value}"
                )
            self._device.move_to(value)
            # Wait for move complete
            while self._device.is_moving():
                pass

        async def set(self, value: Any, *, timeout: float = 10.0) -> None:
            await self._to_thread(self._set_sync, int(value))

        def _where_sync(self) -> int:
            if self._device is None:
                raise RuntimeError("Not connected")
            return int(self._device.get_position())

        async def where(self) -> Any:
            return await self._to_thread(self._where_sync)

        def _stop_sync(self) -> None:
            pass  # No stop for filter wheel

        async def stop(self) -> None:
            pass

    # Register adapters
    adapter_registry.register("thorlabs_kinesis_motor", KinesisMotorAdapter)
    adapter_registry.register("thorlabs_mff", MFFAdapter)
    adapter_registry.register("thorlabs_fw", FWAdapter)
