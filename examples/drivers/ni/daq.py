"""National Instruments DAQmx analog I/O driver.

Provides async wrappers around nidaqmx for analog input/output operations.
Supports both single-point and buffered acquisition.
"""

from __future__ import annotations

from typing import Any

import anyio
import numpy as np

from labpilot.device.schema import DeviceSchema
from labpilot.drivers._base import BaseDriver

__all__ = ["NIAnalogInput", "NIAnalogOutput"]


class NIAnalogInput(BaseDriver):
    """National Instruments analog input driver.

    Implements Readable protocol for voltage acquisition.

    Example:
        >>> daq = NIAnalogInput(
        ...     device="Dev1",
        ...     channels="ai0:3",
        ...     voltage_range=(-10.0, 10.0),
        ... )
        >>> await daq.connect()
        >>> await daq.stage()
        >>> data = await daq.read()
        >>> print(data["voltages"])  # [v0, v1, v2, v3]
    """

    schema = DeviceSchema(
        name="ni_analog_input",
        kind="detector",
        readable={"voltages": "ndarray1d", "timestamp": "float64"},
        settable={},
        units={"voltages": "V", "timestamp": "s"},
        limits={},
        trigger_modes=["software"],
        tags=["NI", "DAQ", "analog_input"],
    )

    def __init__(
        self,
        device: str,
        channels: str = "ai0",
        voltage_range: tuple[float, float] = (-10.0, 10.0),
        sample_rate: float = 1000.0,
    ) -> None:
        """Initialize NI analog input.

        Args:
            device: NI device name (e.g., "Dev1").
            channels: Channel specification (e.g., "ai0", "ai0:3").
            voltage_range: Min/max voltage range tuple.
            sample_rate: Acquisition sample rate (Hz).
        """
        super().__init__()
        self.device = device
        self.channels = channels
        self.voltage_range = voltage_range
        self.sample_rate = sample_rate
        self._task: Any = None  # nidaqmx.Task
        self._staged = False

    async def connect(self) -> None:
        """Verify NI-DAQmx is available.

        Raises:
            ImportError: If nidaqmx not installed.
        """
        try:
            import nidaqmx  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "nidaqmx not installed. Install with: pip install 'labpilot[ni]'"
            ) from e

        self._connected = True

    async def disconnect(self) -> None:
        """Close DAQ task if open."""
        if self._task is not None:
            await anyio.to_thread.run_sync(self._task.close)
            self._task = None
        self._connected = False

    async def stage(self) -> None:
        """Create and configure DAQ task."""
        if self._staged:
            return

        import nidaqmx
        from nidaqmx.constants import TerminalConfiguration

        def _create_task() -> Any:
            """Create DAQ task (runs in thread)."""
            task = nidaqmx.Task()
            task.ai_channels.add_ai_voltage_chan(
                f"{self.device}/{self.channels}",
                terminal_config=TerminalConfiguration.RSE,
                min_val=self.voltage_range[0],
                max_val=self.voltage_range[1],
            )
            task.timing.cfg_samp_clk_timing(
                rate=self.sample_rate,
                sample_mode=nidaqmx.constants.AcquisitionType.FINITE,
                samps_per_chan=1,
            )
            return task

        self._task = await anyio.to_thread.run_sync(_create_task)
        self._staged = True

    async def unstage(self) -> None:
        """Stop and close DAQ task."""
        if self._task is not None:

            def _close_task() -> None:
                """Close task (runs in thread)."""
                try:
                    self._task.stop()
                    self._task.close()
                except Exception:
                    pass

            await anyio.to_thread.run_sync(_close_task)
            self._task = None

        self._staged = False

    async def read(self) -> dict[str, Any]:
        """Acquire analog input voltages.

        Returns:
            Dict with "voltages" (1D numpy array) and "timestamp" (float).

        Raises:
            RuntimeError: If not staged.
        """
        if not self._staged or self._task is None:
            raise RuntimeError("DAQ not staged. Call stage() first.")

        import time

        def _read_voltages() -> np.ndarray:
            """Read voltages (runs in thread)."""
            data = self._task.read()
            # Convert to numpy array (handles single channel or multi-channel)
            if isinstance(data, list):
                return np.array(data, dtype=np.float64)
            else:
                return np.array([data], dtype=np.float64)

        voltages = await anyio.to_thread.run_sync(_read_voltages)
        timestamp = time.time()

        return {
            "voltages": voltages,
            "timestamp": timestamp,
        }

    async def self_test(self) -> bool:
        """Verify DAQ device is accessible.

        Returns:
            True if device found, False otherwise.
        """
        try:
            import nidaqmx.system

            def _check_device() -> bool:
                """Check device exists (runs in thread)."""
                system = nidaqmx.system.System.local()
                devices = [d.name for d in system.devices]
                return self.device in devices

            return await anyio.to_thread.run_sync(_check_device)
        except Exception:
            return False

    def __repr__(self) -> str:
        """Return debugging representation."""
        return (
            f"NIAnalogInput(device='{self.device}', "
            f"channels='{self.channels}', "
            f"connected={self._connected})"
        )


class NIAnalogOutput(BaseDriver):
    """National Instruments analog output driver.

    Implements Movable protocol for voltage control.

    Example:
        >>> daq = NIAnalogOutput(device="Dev1", channel="ao0")
        >>> await daq.connect()
        >>> await daq.stage()
        >>> await daq.set(5.0)  # Set output to 5V
    """

    schema = DeviceSchema(
        name="ni_analog_output",
        kind="source",
        readable={"voltage": "float64"},
        settable={"voltage": "float64"},
        units={"voltage": "V"},
        limits={"voltage": (-10.0, 10.0)},
        trigger_modes=["software"],
        tags=["NI", "DAQ", "analog_output"],
    )

    def __init__(
        self,
        device: str,
        channel: str = "ao0",
        voltage_range: tuple[float, float] = (-10.0, 10.0),
    ) -> None:
        """Initialize NI analog output.

        Args:
            device: NI device name (e.g., "Dev1").
            channel: Channel specification (e.g., "ao0").
            voltage_range: Min/max voltage range tuple.
        """
        super().__init__()
        self.device = device
        self.channel = channel
        self.voltage_range = voltage_range
        self._task: Any = None
        self._staged = False
        self._current_voltage = 0.0

    async def connect(self) -> None:
        """Verify NI-DAQmx is available."""
        try:
            import nidaqmx  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "nidaqmx not installed. Install with: pip install 'labpilot[ni]'"
            ) from e

        self._connected = True

    async def disconnect(self) -> None:
        """Close DAQ task."""
        if self._task is not None:
            await anyio.to_thread.run_sync(self._task.close)
            self._task = None
        self._connected = False

    async def stage(self) -> None:
        """Create and configure output task."""
        if self._staged:
            return

        import nidaqmx

        def _create_task() -> Any:
            """Create task (runs in thread)."""
            task = nidaqmx.Task()
            task.ao_channels.add_ao_voltage_chan(
                f"{self.device}/{self.channel}",
                min_val=self.voltage_range[0],
                max_val=self.voltage_range[1],
            )
            return task

        self._task = await anyio.to_thread.run_sync(_create_task)
        self._staged = True

    async def unstage(self) -> None:
        """Set output to 0V and close task."""
        if self._task is not None:

            def _close_task() -> None:
                """Close task (runs in thread)."""
                try:
                    self._task.write(0.0)  # Safe state
                    self._task.stop()
                    self._task.close()
                except Exception:
                    pass

            await anyio.to_thread.run_sync(_close_task)
            self._task = None

        self._staged = False
        self._current_voltage = 0.0

    async def set(self, value: float, *, timeout: float = 10.0) -> None:
        """Set output voltage.

        Args:
            value: Target voltage (V).
            timeout: Unused (output is immediate).

        Raises:
            ValueError: If value outside limits.
            RuntimeError: If not staged.
        """
        if not self._staged or self._task is None:
            raise RuntimeError("DAQ not staged. Call stage() first.")

        if not (self.voltage_range[0] <= value <= self.voltage_range[1]):
            raise ValueError(
                f"Voltage {value}V outside limits {self.voltage_range}"
            )

        def _write_voltage() -> None:
            """Write voltage (runs in thread)."""
            self._task.write(value)

        await anyio.to_thread.run_sync(_write_voltage)
        self._current_voltage = value

    async def stop(self) -> None:
        """Stop output (set to 0V)."""
        await self.set(0.0)

    async def where(self) -> float:
        """Get current output voltage.

        Returns:
            Current voltage setting (V).
        """
        return self._current_voltage

    async def read(self) -> dict[str, Any]:
        """Read current output voltage.

        Returns:
            Dict with "voltage" key.
        """
        return {"voltage": self._current_voltage}

    async def self_test(self) -> bool:
        """Verify device is accessible."""
        try:
            import nidaqmx.system

            def _check_device() -> bool:
                """Check device (runs in thread)."""
                system = nidaqmx.system.System.local()
                devices = [d.name for d in system.devices]
                return self.device in devices

            return await anyio.to_thread.run_sync(_check_device)
        except Exception:
            return False

    def __repr__(self) -> str:
        """Return debugging representation."""
        return (
            f"NIAnalogOutput(device='{self.device}', "
            f"channel='{self.channel}', "
            f"voltage={self._current_voltage}V, "
            f"connected={self._connected})"
        )
