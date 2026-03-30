"""Test fixtures: fake instruments for testing workflows without hardware.

Organized by dimensionality:

0D Detectors:
- APD: Avalanche photodiode (single photon counter)

1D Detectors:
- TunableSpectrometer: 500-1000nm tunable laser with spectrum acquisition

2D Detectors:
- SpectrumCamera: Simulated spectrum camera with wavelength-dependent response

0D Actuators:
- Switch: Binary on/off switch

1D Actuators:
- Stage: Linear translation stage (0-100mm)
- Scanner1D: Fast scanning along one axis

2D Actuators:
- Scanner2D: XY scanning stage

3D Actuators:
- Scanner3D: XYZ confocal scanning stage

Used for testing workflow automation without real hardware.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from labpilot_core.adapters._base import AdapterBase, adapter_registry
from labpilot_core.device.schema import DeviceSchema


class TunableLaserMotorAdapter(AdapterBase):
    """Test fixture: Tunable laser motor for workflow generation.

    Simulates a tunable laser as a 1D motor device:
    - Wavelength range: 500-1000nm
    - Step size: 0.1nm minimum
    - Fast scanning capability

    Used specifically for spectrum acquisition and wavelength scanning workflows.
    """

    def __init__(self, **kwargs):
        """Initialize tunable laser motor."""
        super().__init__()
        self._resource = kwargs.get("resource", "test://tunable_laser")
        self._wavelength = 650.0  # nm
        self._min_wavelength = 500.0
        self._max_wavelength = 1000.0
        self._step_size = 0.1  # nm

    async def connect(self) -> None:
        """Connect to tunable laser."""
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from tunable laser."""
        self._connected = False

    def _connect_sync(self) -> None:
        """Synchronous connect implementation."""
        pass

    def _disconnect_sync(self) -> None:
        """Synchronous disconnect implementation."""
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Synchronous read implementation."""
        return {
            "wavelength_nm": self._wavelength,
            "position": self._wavelength,
            "units": "nm"
        }

    async def read(self) -> dict[str, Any]:
        """Read current wavelength."""
        return {
            "wavelength_nm": self._wavelength,
            "position": self._wavelength,  # For motor interface compatibility
            "units": "nm"
        }

    async def set(self, **kwargs) -> None:
        """Set laser wavelength."""
        if "wavelength_nm" in kwargs:
            wavelength = float(kwargs["wavelength_nm"])
            if self._min_wavelength <= wavelength <= self._max_wavelength:
                self._wavelength = wavelength
            else:
                raise ValueError(f"Wavelength {wavelength}nm outside range {self._min_wavelength}-{self._max_wavelength}nm")

        if "position" in kwargs:  # Motor interface compatibility
            await self.set(wavelength_nm=kwargs["position"])

    @property
    def schema(self) -> DeviceSchema:
        """Device schema for tunable laser motor."""
        return DeviceSchema(
            name="Tunable Laser Motor",
            kind="motor",  # This is the key - it's a motor, not detector
            tags=["Test", "Laser", "Tunable-Laser", "Motor", "Wavelength"],
            readable={
                "wavelength_nm": "float64",
                "position": "float64",  # Motor interface compatibility
            },
            settable={
                "wavelength_nm": "float64",  # Primary control parameter (1D)
                # Note: position is handled in set() method for compatibility
            },
            units={
                "wavelength_nm": "nm",
                "position": "nm",
            },
            limits={
                "wavelength_nm": (500.0, 1000.0),
            }
        )


class TunableSpectrometerAdapter(AdapterBase):
    """Test fixture: Tunable spectrometer (500-1000nm laser + detector).

    Simulates a laser-based spectrometer with:
    - Tunable laser: 500-1000nm in 1nm steps
    - Detector: Returns realistic spectrum data with Lorentzian peaks
    - Integration time: 1-1000ms
    - Averaging: 1-100 samples

    Perfect for testing spectrum acquisition workflows.
    """

    def __init__(self, name: str = "fake_spectrometer"):
        super().__init__()
        self._name = name
        self._wavelength = 650.0  # Current laser wavelength (nm)
        self._integration_time = 100.0  # Integration time (ms)
        self._averaging = 1  # Number of averages
        self._offset = 0.0  # Dark current offset

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                "wavelength": "float64",
                "spectrum": "array",  # 1D spectrum array
                "timestamp": "float64",
            },
            settable={
                "wavelength": "float64",
                "integration_time": "float64",
                "averaging": "int32",
                "offset": "float64",
            },
            units={
                "wavelength": "nm",
                "integration_time": "ms",
                "offset": "counts",
            },
            limits={
                "wavelength": (500.0, 1000.0),
                "integration_time": (1.0, 1000.0),
                "averaging": (1, 100),
                "offset": (-1000.0, 1000.0),
            },
            tags=["Test", "Spectrometer", "Tunable-Laser", "Detector"],
        )

    def _connect_sync(self) -> None:
        """Simulate connection - nothing to do for fake device."""
        pass

    def _disconnect_sync(self) -> None:
        """Simulate disconnection - nothing to do for fake device."""
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read spectrum data at current wavelength.

        Returns a realistic spectrum with:
        - Strong peak at current laser wavelength
        - Weaker peaks from substrate
        - Realistic noise
        """
        import time

        # Generate wavelength array (400-1100nm at 0.5nm resolution)
        wavelengths = np.arange(400, 1100, 0.5)

        # Create spectrum with Lorentzian peaks
        spectrum = np.zeros_like(wavelengths, dtype=np.float32)

        # Main peak (laser wavelength)
        linewidth = 2.0  # FWHM in nm
        main_peak = 10000 * linewidth**2 / (
            4 * (wavelengths - self._wavelength) ** 2 + linewidth**2
        )
        spectrum += main_peak

        # Secondary peaks (substrate fluorescence, Raman, etc.)
        secondary_peaks = [
            (self._wavelength + 50, 1000),  # Stokes line
            (self._wavelength - 30, 800),  # Anti-Stokes line
            (self._wavelength + 100, 500),  # Fluorescence background
        ]

        for peak_wl, peak_intensity in secondary_peaks:
            peak = peak_intensity * linewidth**2 / (
                4 * (wavelengths - peak_wl) ** 2 + linewidth**2
            )
            spectrum += peak

        # Add realistic noise (shot noise + read noise)
        shot_noise = np.random.poisson(spectrum / 10) * 10
        read_noise = np.random.normal(0, 50, len(spectrum))
        spectrum = spectrum + shot_noise + read_noise

        # Apply integration time scaling (more time = more signal)
        spectrum = spectrum * (self._integration_time / 100.0)

        # Apply averaging
        spectrum = spectrum / self._averaging

        # Add offset
        spectrum += self._offset

        # Ensure no negative values
        spectrum = np.maximum(spectrum, 0)

        return {
            "wavelength": float(self._wavelength),
            "spectrum": spectrum.tolist(),  # Convert to list for JSON serialization
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        """Setup before acquisition - nothing needed for fake device."""
        pass

    def _unstage_sync(self) -> None:
        """Cleanup after acquisition - nothing needed for fake device."""
        pass

    async def set_wavelength(self, wavelength: float) -> None:
        """Set laser wavelength (500-1000nm)."""
        if not 500 <= wavelength <= 1000:
            raise ValueError(f"Wavelength {wavelength} nm out of range (500-1000)")
        self._wavelength = float(wavelength)

    async def set_integration_time(self, time_ms: float) -> None:
        """Set integration time (1-1000ms)."""
        if not 1 <= time_ms <= 1000:
            raise ValueError(f"Integration time {time_ms} ms out of range (1-1000)")
        self._integration_time = float(time_ms)

    async def set_averaging(self, num_samples: int) -> None:
        """Set number of averages (1-100)."""
        if not 1 <= num_samples <= 100:
            raise ValueError(f"Averaging {num_samples} out of range (1-100)")
        self._averaging = int(num_samples)

    async def set_offset(self, offset: float) -> None:
        """Set dark current offset."""
        self._offset = float(offset)


class SpectrumCameraAdapter(AdapterBase):
    """Test fixture: Spectrum camera for recording spectral data.

    Simulates a high-speed camera optimized for spectrum recording:
    - Resolution: 2048 pixels × 1024 pixels
    - Sensor wavelength range: 400-1100nm
    - Exposure time: 0.1-100ms
    - Binning: 1×1, 2×2, 4×4

    Works with TunableSpectrometerAdapter for complete spectroscopy workflow.
    """

    def __init__(self, name: str = "fake_spectrum_camera"):
        super().__init__()
        self._name = name
        self._exposure = 10.0  # Exposure time (ms)
        self._binning = 1  # Binning factor (1, 2, or 4)
        self._temperature = -40.0  # CCD temperature (°C)

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                "frame": "array",  # 2D frame data
                "exposure": "float64",
                "temperature": "float64",
                "timestamp": "float64",
            },
            settable={
                "exposure": "float64",
                "binning": "int32",
                "temperature": "float64",
            },
            units={
                "exposure": "ms",
                "temperature": "C",
            },
            limits={
                "exposure": (0.1, 100.0),
                "binning": (1, 4),
                "temperature": (-80.0, 25.0),
            },
            tags=["Test", "Camera", "Spectrum-Detector", "CCD"],
        )

    def _connect_sync(self) -> None:
        """Simulate connection."""
        pass

    def _disconnect_sync(self) -> None:
        """Simulate disconnection."""
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read a frame from the camera.

        Returns a realistic CCD frame with:
        - Hot pixels (cosmic rays)
        - Read noise
        - Thermal noise (temperature-dependent)
        - Vignetting (edges darker than center)
        """
        import time

        # Calculate actual resolution based on binning
        h = 1024 // self._binning
        w = 2048 // self._binning

        # Create base image with Gaussian blob (simulating spectrum line)
        y, x = np.ogrid[:h, :w]
        center_y, center_x = h // 2, w // 2

        # Main spectrum line (high intensity in center, falls off at edges)
        spectrum_line = 5000 * np.exp(-((y - center_y) ** 2) / (2 * 50**2))
        spectrum_line = spectrum_line * np.exp(
            -((x - center_x) ** 2) / (2 * (w // 8) ** 2)
        )

        # Add vignetting (darker at edges)
        vignette = np.ones((h, w))
        for i in range(h):
            for j in range(w):
                dist = np.sqrt(
                    ((i - center_y) / h) ** 2 + ((j - center_x) / w) ** 2
                )
                vignette[i, j] = 1 - 0.3 * (dist / 0.7) ** 2

        frame = spectrum_line * vignette

        # Add read noise (Gaussian)
        read_noise_sigma = 10
        frame += np.random.normal(0, read_noise_sigma, (h, w))

        # Add thermal noise (temperature-dependent)
        thermal_factor = np.exp((self._temperature + 40) / 10)  # More signal at cold temps
        thermal_noise = np.random.normal(0, thermal_factor, (h, w))
        frame += thermal_noise

        # Add hot pixels (cosmic rays)
        num_hot_pixels = int(h * w / 100000)  # ~1 per 100k pixels
        for _ in range(num_hot_pixels):
            yi = np.random.randint(0, h)
            xi = np.random.randint(0, w)
            frame[yi, xi] += np.random.uniform(1000, 5000)

        # Apply exposure scaling
        frame = frame * (self._exposure / 10.0)

        # Ensure valid range
        frame = np.clip(frame, 0, 65535).astype(np.uint16)

        return {
            "frame": frame.tolist(),
            "exposure": float(self._exposure),
            "temperature": float(self._temperature),
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        """Setup before acquisition."""
        pass

    def _unstage_sync(self) -> None:
        """Cleanup after acquisition."""
        pass

    async def set_exposure(self, time_ms: float) -> None:
        """Set exposure time (0.1-100ms)."""
        if not 0.1 <= time_ms <= 100:
            raise ValueError(f"Exposure {time_ms} ms out of range (0.1-100)")
        self._exposure = float(time_ms)

    async def set_binning(self, binning: int) -> None:
        """Set binning (1, 2, or 4)."""
        if binning not in [1, 2, 4]:
            raise ValueError(f"Binning {binning} must be 1, 2, or 4")
        self._binning = int(binning)

    async def set_temperature(self, temp_c: float) -> None:
        """Set CCD temperature (-80 to +25°C)."""
        if not -80 <= temp_c <= 25:
            raise ValueError(f"Temperature {temp_c}°C out of range (-80 to +25)")
        self._temperature = float(temp_c)


class FakeAPDAdapter(AdapterBase):
    """Test fixture: Avalanche Photodiode (APD) - 0D detector.

    Simulates a single-photon counting detector:
    - Count rate: 0-1MHz
    - Integration time: 0.1-1000ms
    - Returns single scalar value (photon counts)

    Perfect for confocal microscopy and single-photon experiments.
    """

    def __init__(self, name: str = "fake_apd"):
        super().__init__()
        self._name = name
        self._integration_time = 10.0  # ms
        self._background_rate = 1000.0  # counts/sec (dark counts)
        self._signal_rate = 50000.0  # counts/sec (signal when illuminated)

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="detector",
            readable={
                "counts": "float64",  # Total counts in integration window
                "count_rate": "float64",  # Counts per second
                "timestamp": "float64",
            },
            settable={
                "integration_time": "float64",
                "background_rate": "float64",
                "signal_rate": "float64",
            },
            units={
                "counts": "counts",
                "count_rate": "counts/s",
                "integration_time": "ms",
                "background_rate": "counts/s",
                "signal_rate": "counts/s",
            },
            limits={
                "integration_time": (0.1, 1000.0),
                "background_rate": (0.0, 100000.0),
                "signal_rate": (0.0, 1000000.0),
            },
            tags=["Test", "APD", "0D-Detector", "Single-Photon"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read photon counts."""
        import time

        # Simulate Poisson-distributed photon counts
        rate = self._background_rate + self._signal_rate  # total rate
        expected_counts = rate * (self._integration_time / 1000.0)

        # Poisson noise
        counts = np.random.poisson(expected_counts)

        return {
            "counts": float(counts),
            "count_rate": float(counts / (self._integration_time / 1000.0)),
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        pass

    def _unstage_sync(self) -> None:
        pass

    async def set_integration_time(self, time_ms: float) -> None:
        """Set integration time (0.1-1000ms)."""
        if not 0.1 <= time_ms <= 1000:
            raise ValueError(f"Integration time {time_ms} ms out of range")
        self._integration_time = float(time_ms)

    async def set_background_rate(self, rate: float) -> None:
        """Set background count rate (dark counts)."""
        self._background_rate = float(rate)

    async def set_signal_rate(self, rate: float) -> None:
        """Set signal count rate."""
        self._signal_rate = float(rate)


class FakeStageAdapter(AdapterBase):
    """Test fixture: Linear Translation Stage - 1D actuator.

    Simulates a motorized linear stage:
    - Range: 0-100mm
    - Speed: 0.1-10 mm/s
    - Accuracy: 1 µm

    Used for delay lines, sample positioning, etc.
    """

    def __init__(self, name: str = "fake_stage"):
        super().__init__()
        self._name = name
        self._position = 50.0  # mm
        self._speed = 1.0  # mm/s
        self._target = 50.0  # mm

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={
                "position": "float64",
                "speed": "float64",
                "target": "float64",
                "moving": "bool",
                "timestamp": "float64",
            },
            settable={
                "position": "float64",
                "speed": "float64",
            },
            units={
                "position": "mm",
                "speed": "mm/s",
            },
            limits={
                "position": (0.0, 100.0),
                "speed": (0.1, 10.0),
            },
            tags=["Test", "Stage", "1D-Actuator", "Translation"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read stage position."""
        import time

        # Simulate movement towards target
        if abs(self._position - self._target) > 0.001:
            # Move a bit towards target
            direction = 1 if self._target > self._position else -1
            step = min(abs(self._target - self._position), 0.1)
            self._position += direction * step
            moving = True
        else:
            self._position = self._target
            moving = False

        return {
            "position": float(self._position),
            "speed": float(self._speed),
            "target": float(self._target),
            "moving": moving,
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        pass

    def _unstage_sync(self) -> None:
        pass

    async def set_position(self, position: float) -> None:
        """Set target position (0-100mm)."""
        if not 0 <= position <= 100:
            raise ValueError(f"Position {position} mm out of range (0-100)")
        self._target = float(position)

    async def set_speed(self, speed: float) -> None:
        """Set movement speed (0.1-10 mm/s)."""
        if not 0.1 <= speed <= 10:
            raise ValueError(f"Speed {speed} mm/s out of range (0.1-10)")
        self._speed = float(speed)


class FakeScanner1DAdapter(AdapterBase):
    """Test fixture: 1D Scanner - 1D actuator.

    Simulates a fast scanning mirror or galvo:
    - Range: -10 to +10 degrees
    - Speed: Fast scanning (kHz capable)

    Used for line scans in microscopy.
    """

    def __init__(self, name: str = "fake_scanner_1d"):
        super().__init__()
        self._name = name
        self._position = 0.0  # degrees

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={
                "position": "float64",
                "timestamp": "float64",
            },
            settable={
                "position": "float64",
            },
            units={
                "position": "deg",
            },
            limits={
                "position": (-10.0, 10.0),
            },
            tags=["Test", "Scanner", "1D-Actuator", "Galvo"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read scanner position."""
        import time
        return {
            "position": float(self._position),
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        pass

    def _unstage_sync(self) -> None:
        pass

    async def set_position(self, position: float) -> None:
        """Set scanner position (-10 to +10 degrees)."""
        if not -10 <= position <= 10:
            raise ValueError(f"Position {position} deg out of range (-10 to +10)")
        self._position = float(position)


class FakeScanner2DAdapter(AdapterBase):
    """Test fixture: 2D XY Scanner - 2D actuator.

    Simulates a 2D scanning stage or dual galvo system:
    - X range: -10 to +10 mm
    - Y range: -10 to +10 mm

    Used for raster scanning in imaging.
    """

    def __init__(self, name: str = "fake_scanner_2d"):
        super().__init__()
        self._name = name
        self._x = 0.0  # mm
        self._y = 0.0  # mm

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={
                "x": "float64",
                "y": "float64",
                "timestamp": "float64",
            },
            settable={
                "x": "float64",
                "y": "float64",
            },
            units={
                "x": "mm",
                "y": "mm",
            },
            limits={
                "x": (-10.0, 10.0),
                "y": (-10.0, 10.0),
            },
            tags=["Test", "Scanner", "2D-Actuator", "XY"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read XY position."""
        import time
        return {
            "x": float(self._x),
            "y": float(self._y),
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        pass

    def _unstage_sync(self) -> None:
        pass

    async def set_x(self, x: float) -> None:
        """Set X position (-10 to +10 mm)."""
        if not -10 <= x <= 10:
            raise ValueError(f"X position {x} mm out of range (-10 to +10)")
        self._x = float(x)

    async def set_y(self, y: float) -> None:
        """Set Y position (-10 to +10 mm)."""
        if not -10 <= y <= 10:
            raise ValueError(f"Y position {y} mm out of range (-10 to +10)")
        self._y = float(y)


class FakeScanner3DAdapter(AdapterBase):
    """Test fixture: 3D XYZ Confocal Scanner - 3D actuator.

    Simulates a 3D confocal scanning system:
    - X range: -10 to +10 µm
    - Y range: -10 to +10 µm
    - Z range: -50 to +50 µm (focus depth)

    Used for 3D confocal imaging and volume scanning.
    """

    def __init__(self, name: str = "fake_scanner_3d"):
        super().__init__()
        self._name = name
        self._x = 0.0  # µm
        self._y = 0.0  # µm
        self._z = 0.0  # µm

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={
                "x": "float64",
                "y": "float64",
                "z": "float64",
                "timestamp": "float64",
            },
            settable={
                "x": "float64",
                "y": "float64",
                "z": "float64",
            },
            units={
                "x": "um",
                "y": "um",
                "z": "um",
            },
            limits={
                "x": (-10.0, 10.0),
                "y": (-10.0, 10.0),
                "z": (-50.0, 50.0),
            },
            tags=["Test", "Scanner", "3D-Actuator", "XYZ", "Confocal"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read XYZ position."""
        import time
        return {
            "x": float(self._x),
            "y": float(self._y),
            "z": float(self._z),
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        pass

    def _unstage_sync(self) -> None:
        pass

    async def set_x(self, x: float) -> None:
        """Set X position (-10 to +10 µm)."""
        if not -10 <= x <= 10:
            raise ValueError(f"X position {x} µm out of range (-10 to +10)")
        self._x = float(x)

    async def set_y(self, y: float) -> None:
        """Set Y position (-10 to +10 µm)."""
        if not -10 <= y <= 10:
            raise ValueError(f"Y position {y} µm out of range (-10 to +10)")
        self._y = float(y)

    async def set_z(self, z: float) -> None:
        """Set Z position (-50 to +50 µm)."""
        if not -50 <= z <= 50:
            raise ValueError(f"Z position {z} µm out of range (-50 to +50)")
        self._z = float(z)


class FakeSwitchAdapter(AdapterBase):
    """Test fixture: Binary Switch - 0D actuator.

    Simulates an on/off switch:
    - State: 0 (off) or 1 (on)

    Used for shutters, relays, laser enable, etc.
    """

    def __init__(self, name: str = "fake_switch"):
        super().__init__()
        self._name = name
        self._state = 0  # 0 = off, 1 = on

    @property
    def schema(self) -> DeviceSchema:
        return DeviceSchema(
            name=self._name,
            kind="motor",
            readable={
                "state": "int32",
                "timestamp": "float64",
            },
            settable={
                "state": "int32",
            },
            units={},
            limits={
                "state": (0, 1),
            },
            tags=["Test", "Switch", "0D-Actuator", "Binary"],
        )

    def _connect_sync(self) -> None:
        pass

    def _disconnect_sync(self) -> None:
        pass

    def _read_sync(self) -> dict[str, Any]:
        """Read switch state."""
        import time
        return {
            "state": int(self._state),
            "timestamp": time.time(),
        }

    def _stage_sync(self) -> None:
        pass

    def _unstage_sync(self) -> None:
        pass

    async def set_state(self, state: int) -> None:
        """Set switch state (0 or 1)."""
        if state not in [0, 1]:
            raise ValueError(f"State {state} must be 0 or 1")
        self._state = int(state)


# Register fake adapters
adapter_registry.register("fake_tunable_laser", TunableLaserMotorAdapter)
adapter_registry.register("fake_spectrometer", TunableSpectrometerAdapter)
adapter_registry.register("fake_spectrum_camera", SpectrumCameraAdapter)
adapter_registry.register("fake_apd", FakeAPDAdapter)
adapter_registry.register("fake_stage", FakeStageAdapter)
adapter_registry.register("fake_scanner_1d", FakeScanner1DAdapter)
adapter_registry.register("fake_scanner_2d", FakeScanner2DAdapter)
adapter_registry.register("fake_scanner_3d", FakeScanner3DAdapter)
adapter_registry.register("fake_switch", FakeSwitchAdapter)

__all__ = [
    "FakeAPDAdapter",
    "FakeScanner1DAdapter",
    "FakeScanner2DAdapter",
    "FakeScanner3DAdapter",
    "FakeStageAdapter",
    "FakeSwitchAdapter",
    "SpectrumCameraAdapter",
    "TunableLaserMotorAdapter",
    "TunableSpectrometerAdapter",
]
