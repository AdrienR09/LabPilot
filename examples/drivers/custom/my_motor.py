"""Example: Custom hardware driver for LabPilot.

This shows how to create a driver for YOUR specific hardware.
Adapt this template for your instrument.
"""

from __future__ import annotations

from typing import Any

import anyio

from labpilot.device.schema import DeviceSchema
from labpilot.drivers.serial._base import SerialDriver


class MyCustomMotor(SerialDriver):
    """Driver for my custom motor controller.

    Example: Newport ESP301 / Thorlabs APT / PI piezo stage / etc.

    Replace the commands below with your instrument's protocol.
    """

    schema = DeviceSchema(
        name="my_custom_motor",
        kind="motor",
        readable={"position": "float64"},
        settable={"position": "float64"},
        units={"position": "mm"},
        limits={"position": (-10.0, 10.0)},
        trigger_modes=["software"],
        tags=["custom", "serial", "motion"],
    )

    def __init__(self, port: str, axis: int = 1) -> None:
        """Initialize motor controller.

        Args:
            port: Serial port (e.g., "/dev/ttyUSB0" or "COM3").
            axis: Axis number (if multi-axis controller).
        """
        super().__init__(port=port, baudrate=115200, timeout=1.0)
        self.axis = axis
        self._staged = False

    async def connect(self) -> None:
        """Connect to motor controller."""
        await super().connect()

        # Send initialization commands
        # Example: Enable motor
        await self._write(f"{self.axis}MO\n".encode())  # Motor ON
        await anyio.sleep(0.1)

        print(f"✓ Connected to motor on {self.port} (axis {self.axis})")

    async def disconnect(self) -> None:
        """Disconnect from motor controller."""
        # Send safe shutdown commands
        # Example: Disable motor
        try:
            await self._write(f"{self.axis}MF\n".encode())  # Motor OFF
            await anyio.sleep(0.1)
        except Exception:
            pass  # Ignore errors during disconnect

        await super().disconnect()
        print(f"✓ Disconnected from motor")

    async def stage(self) -> None:
        """Prepare for scanning."""
        if self._staged:
            return

        # Example: Set velocity limit
        await self._write(f"{self.axis}VA10\n".encode())  # 10 mm/s
        await anyio.sleep(0.05)

        self._staged = True
        print(f"✓ Motor staged (axis {self.axis})")

    async def unstage(self) -> None:
        """Clean up after scanning."""
        self._staged = False
        print(f"✓ Motor unstaged")

    async def set(self, value: float, *, timeout: float = 10.0) -> None:
        """Move to absolute position.

        Args:
            value: Target position in mm.
            timeout: Maximum time to wait for motion (seconds).
        """
        # Validate limits
        limits = self.schema.limits["position"]
        if not (limits[0] <= value <= limits[1]):
            raise ValueError(
                f"Position {value} mm outside limits {limits}"
            )

        # Send move command
        # Example: PA = Position Absolute
        await self._write(f"{self.axis}PA{value:.6f}\n".encode())

        # Wait for motion to complete
        start_time = anyio.current_time()
        while True:
            # Check if done (replace with your instrument's status query)
            await self._write(f"{self.axis}MD?\n".encode())  # Motion Done?
            response = await self._readline()

            if b"1" in response or b"done" in response.lower():
                break  # Motion complete

            # Check timeout
            if (anyio.current_time() - start_time) > timeout:
                raise TimeoutError(f"Motion timeout after {timeout}s")

            await anyio.sleep(0.05)  # Poll every 50ms

    async def stop(self) -> None:
        """Stop motion immediately."""
        await self._write(f"{self.axis}ST\n".encode())  # Stop
        print(f"⚠ Motor stopped!")

    async def where(self) -> float:
        """Get current position.

        Returns:
            Current position in mm.
        """
        # Query position (replace with your command)
        await self._write(f"{self.axis}TP\n".encode())  # Tell Position
        response = await self._readline()

        # Parse response (adjust for your format)
        position = float(response.strip().decode())
        return position

    async def read(self) -> dict[str, Any]:
        """Read current position."""
        return {"position": await self.where()}

    async def self_test(self) -> bool:
        """Verify communication with controller.

        Returns:
            True if communication successful.
        """
        try:
            # Send identification query
            await self._write(b"*IDN?\n")
            response = await self._readline()
            return len(response) > 0
        except Exception:
            return False

    def __repr__(self) -> str:
        """Debug representation."""
        return (
            f"MyCustomMotor(port='{self.port}', "
            f"axis={self.axis}, "
            f"connected={self._connected})"
        )


# ============================================================
# Example usage
# ============================================================

async def test_motor() -> None:
    """Test the custom motor driver."""

    # Create and connect motor
    motor = MyCustomMotor(port="/dev/ttyUSB0", axis=1)

    # For testing without hardware, this will fail gracefully
    try:
        await motor.connect()

        # Test self-test
        if await motor.self_test():
            print("✓ Self-test passed")
        else:
            print("✗ Self-test failed")

        # Read current position
        pos = await motor.where()
        print(f"Current position: {pos:.3f} mm")

        # Move to position
        await motor.stage()
        await motor.set(5.0)
        print(f"Moved to: {await motor.where():.3f} mm")

        await motor.disconnect()

    except Exception as e:
        print(f"⚠ Hardware not connected: {e}")
        print("(This is expected if device is not plugged in)")


if __name__ == "__main__":
    # Test the driver
    anyio.run(test_motor)
