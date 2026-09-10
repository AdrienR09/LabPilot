"""A simulated Ocean Optics spectrometer — the same model table, no driver.

There are already six mock spectrometers here, and none of them is any
particular instrument: they invent a pixel count and a range. This one is
whichever model you name, with that model's real pixel count, ADC full
scale and exposure limits — so a QE Pro refuses to expose for less than
8 ms on a laptop exactly as it will on the bench, and an acquisition
configured against the mock is configured against the instrument.

The physics is deliberately ordinary: a few emission lines on a broad
background, shot noise that scales as the square root of the signal, a
dark offset, and hard clipping at full scale. That last part is what makes
the `saturated` flag worth having — turn the exposure up and the peaks
flatten and the flag comes back true, which is the failure this reports
and nothing else in the repo simulates.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from labpilot.instruments._base import AdapterBase, adapter_registry
from labpilot.instruments.OceanOptics.spectrometer import (
    _SpectrometerConfig,
    spectrometer_schema,
)

__all__ = ["MockOceanOptics"]

#: (centre nm, width nm, brightness) — a mercury-argon calibration lamp is
#: what is actually plugged into a spectrometer half the time.
_LINES = (
    (253.7, 0.6, 0.35),
    (365.0, 0.7, 0.55),
    (435.8, 0.8, 1.00),
    (546.1, 0.9, 0.85),
    (696.5, 1.0, 0.45),
    (763.5, 1.1, 0.30),
    (912.3, 1.4, 0.20),
)


class MockOceanOptics(_SpectrometerConfig, AdapterBase):
    """A simulated spectrometer. Same arguments as `OceanOpticsAdapter`,
    plus the wavelength range its grating covers — on real hardware that
    comes from the factory calibration, which depends on the grating and
    slit fitted rather than on the model."""

    def __init__(
        self,
        serial_number: str = "MOCK0001",
        model: str = "USB2000+",
        integration_time_ms: float = 10.0,
        scans_to_average: int = 1,
        boxcar_width: int = 0,
        correct_dark: bool = False,
        correct_nonlinearity: bool = False,
        name: str = "mock_ocean_optics",
        wavelength_range: tuple[float, float] = (200.0, 1100.0),
    ) -> None:
        AdapterBase.__init__(self)
        _SpectrometerConfig.__init__(
            self, serial_number=serial_number, model=model or "USB2000+",
            integration_time_ms=integration_time_ms,
            scans_to_average=scans_to_average, boxcar_width=boxcar_width,
            correct_dark=correct_dark, correct_nonlinearity=correct_nonlinearity,
            name=name,
        )
        self._range = (float(wavelength_range[0]), float(wavelength_range[1]))
        self._wavelengths = np.linspace(*self._range, self.pixels)
        self._integration_ms, _ = self.quantise_exposure(self._integration_ms)

    @property
    def schema(self):
        """The shared schema, plus a Mock tag."""
        return spectrometer_schema(
            self._name, self.model, self.pixels, tags=("Mock",)
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _self_test_sync(self) -> None:
        pass

    # --- The simulated spectrum -------------------------------------------

    def _frame(self) -> np.ndarray:
        model = self.model
        assert model is not None  # a mock always names a model
        wavelengths = self._wavelengths

        # Counts per millisecond at full brightness, scaled so a default
        # 10 ms exposure lands around a third of full scale — bright
        # enough to be interesting, dim enough that turning it up
        # saturates, which is the behaviour worth simulating.
        per_ms = model.max_counts / 30.0
        signal = np.zeros_like(wavelengths)
        for centre, width, brightness in _LINES:
            signal += brightness * np.exp(
                -((wavelengths - centre) ** 2) / (2.0 * width**2)
            )
        # A broad fluorescence-like background, so the baseline is not flat.
        signal += 0.05 * np.exp(-((wavelengths - 600.0) ** 2) / (2.0 * 180.0**2))

        counts = signal * per_ms * self._integration_ms
        dark = 0.0 if self._correct_dark else model.max_counts * 0.01
        noisy = np.random.poisson(np.clip(counts, 0.0, None)) + dark
        noisy = noisy + np.random.normal(0.0, model.max_counts * 0.001, noisy.shape)
        return np.clip(noisy, 0.0, model.max_counts)

    def _read_sync(self) -> dict[str, Any]:
        frames = [self._frame() for _ in range(self._average)]
        reading: dict[str, Any] = {
            "wavelengths": self._wavelengths.tolist(),
            **self._finish(np.mean(frames, axis=0)),
            **self._settings(),
        }
        if self.model is not None and self.model.cooled:
            reading["tec_setpoint_c"] = self._tec_setpoint
            reading["tec_temperature_c"] = self._tec_setpoint + float(
                np.random.normal(0.0, 0.1)
            )
        return reading

    async def write(self, values: dict[str, Any]) -> None:
        for key, value in self.validate_write(values).items():
            if key == "integration_time_ms":
                # `validate_write` has already refused anything outside
                # this model's limits — which is the point of naming a
                # model on a machine with no hardware attached.
                self._integration_ms = float(value)
            elif key == "scans_to_average":
                self._average = max(int(value), 1)
            elif key == "boxcar_width":
                self._boxcar = max(int(value), 0)
            elif key == "correct_dark":
                self._correct_dark = bool(value)
            elif key == "correct_nonlinearity":
                self._correct_nonlinearity = bool(value)
            elif key == "trigger_mode":
                self._trigger_mode = int(value)
            elif key == "tec_setpoint_c":
                self._tec_setpoint = float(value)

    async def reconcile(self) -> dict[str, Any]:
        model = self.model
        return {
            "model": model.model if model else "",
            "device": {
                "model": model.model if model else "",
                "serial_number": self._serial,
                "pixels": self.pixels,
                "max_counts": model.max_counts if model else 0,
            },
            "differences": {},
            "warning": "",
        }


adapter_registry.register("mock_ocean_optics", MockOceanOptics)
