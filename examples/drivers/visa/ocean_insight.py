"""Ocean Insight USB spectrometer driver via VISA.

Supports Ocean Insight USB2000/USB4000 series spectrometers with VISA interface.
"""

from __future__ import annotations

from typing import Any

import anyio
import numpy as np

from labpilot.device.schema import DeviceSchema
from labpilot.drivers.visa._base import VISADriver

__all__ = ["OceanInsight"]


class OceanInsight(VISADriver):
    """Ocean Insight USB spectrometer via VISA.

    Implements Readable and Triggerable protocols for use in scans.

    Example:
        >>> spec = OceanInsight(
        ...     resource="USB0::0x2457::0x101E::1::INSTR",
        ...     integration_time_ms=100.0,
        ... )
        >>> await spec.connect()
        >>> await spec.stage()
        >>> data = await spec.read()
        >>> print(data["wavelengths"], data["intensities"])
    """

    schema = DeviceSchema(
        name="ocean_insight",
        kind="detector",
        readable={"wavelengths": "ndarray1d", "intensities": "ndarray1d"},
        settable={"integration_time_ms": "float64"},
        units={"wavelengths": "nm", "intensities": "counts"},
        limits={"integration_time_ms": (1.0, 60000.0)},
        trigger_modes=["software", "hardware"],
        tags=["spectroscopy", "VISA", "USB"],
    )

    def __init__(
        self, resource: str, integration_time_ms: float = 100.0, timeout: float = 10.0
    ) -> None:
        """Initialize Ocean Insight spectrometer.

        Args:
            resource: VISA resource string (e.g., "USB0::0x2457::0x101E::1::INSTR").
            integration_time_ms: Integration time in milliseconds.
            timeout: Communication timeout in seconds.
        """
        super().__init__(resource, timeout)
        self.integration_time_ms = integration_time_ms
        self._wavelengths: np.ndarray | None = None
        self._staged = False

    async def stage(self) -> None:
        """Prepare spectrometer for acquisition.

        Reads wavelength calibration and sets integration time.
        """
        if self._staged:
            return

        # Set integration time
        await self._write(f"SINT {int(self.integration_time_ms)}")

        # Read wavelength calibration (if not already cached)
        if self._wavelengths is None:
            num_pixels_str = await self._query("GDET 0")  # Get detector pixels
            num_pixels = int(num_pixels_str)

            # Read wavelength coefficients (simplified; real implementation
            # would parse full calibration polynomial)
            wl_start = 200.0  # nm, typical UV start
            wl_stop = 1100.0  # nm, typical NIR stop
            self._wavelengths = np.linspace(wl_start, wl_stop, num_pixels)

        self._staged = True

    async def unstage(self) -> None:
        """Clean up after acquisition."""
        self._staged = False

    async def read(self) -> dict[str, Any]:
        """Acquire spectrum.

        Returns:
            Dict with keys "wavelengths" (1D array, nm) and "intensities"
            (1D array, counts).

        Raises:
            RuntimeError: If not staged or not connected.
        """
        if not self._staged:
            raise RuntimeError("Spectrometer not staged. Call stage() first.")

        # Trigger acquisition
        await self._write("TRIG 1")

        # Wait for acquisition to complete (integration time + readout overhead)
        await anyio.sleep(self.integration_time_ms / 1000.0 + 0.1)

        # Read spectrum data
        spectrum_str = await self._query("GETSPEC")
        intensities = np.array(
            [float(x) for x in spectrum_str.split(",")], dtype=np.float64
        )

        return {
            "wavelengths": self._wavelengths,
            "intensities": intensities,
        }

    async def trigger(self) -> None:
        """Issue software trigger for acquisition.

        Used in triggered scan modes. Starts acquisition but does not wait
        for completion (use read() to retrieve data).
        """
        await self._write("TRIG 1")

    async def arm(self, mode: str) -> None:
        """Configure trigger mode.

        Args:
            mode: Trigger mode ("software" or "hardware").

        Raises:
            ValueError: If mode not in schema.trigger_modes.
        """
        if mode not in self.schema.trigger_modes:
            raise ValueError(
                f"Invalid trigger mode '{mode}'. "
                f"Supported: {self.schema.trigger_modes}"
            )

        if mode == "software":
            await self._write("TMODE 0")  # Software trigger mode
        elif mode == "hardware":
            await self._write("TMODE 1")  # External trigger mode

    async def self_test(self) -> bool:
        """Verify communication without acquiring data.

        Returns:
            True if communication successful, False otherwise.
        """
        try:
            idn = await self._query("*IDN?")
            return "Ocean" in idn or "OceanInsight" in idn
        except Exception:
            return False

    def __repr__(self) -> str:
        """Return debugging representation."""
        return (
            f"OceanInsight(resource='{self.resource}', "
            f"integration_time_ms={self.integration_time_ms}, "
            f"connected={self._connected})"
        )
