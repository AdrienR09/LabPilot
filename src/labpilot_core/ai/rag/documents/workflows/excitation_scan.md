# Fluorescence Excitation Scan Workflow

A common scanning spectroscopy experiment where excitation wavelength is varied while measuring emission intensity or spectrum.

## Overview
Excitation scans measure fluorescence intensity as a function of excitation wavelength. The excitation laser is tuned across a range while the detector (spectrometer or photodiode) measures the fluorescence response.

## Required Equipment
- **Tunable Laser**: Ti:Sapphire, OPO, or tunable diode laser
- **Detector**: Spectrometer, PMT, or photodiode
- **Optional**: Monochromator for emission wavelength selection
- **Optional**: Beam shutter for background measurements

## Workflow Parameters
- `start_wavelength` (nm): Starting excitation wavelength
- `end_wavelength` (nm): Ending excitation wavelength
- `step_size` (nm): Wavelength step size
- `integration_time` (ms): Detector integration time per point
- `laser_power` (%): Laser output power level
- `averaging_count`: Number of measurements per wavelength point

## Typical Procedure

### 1. Equipment Setup
```python
# Connect instruments
await session.connect_device("laser", "toptica_ibeam", wavelength_range=(400, 800))
await session.connect_device("spectrometer", "ocean_usb2000", integration_time=100)

# Configure laser
await laser.set("power_percent", 10)  # Low power to avoid saturation
await laser.set("output_enabled", True)

# Configure spectrometer
await spectrometer.set("integration_time_ms", 100)
await spectrometer.set("averaging_count", 3)
```

### 2. Background Measurement
```python
# Block excitation beam
await laser.set("output_enabled", False)

# Measure background
background = await spectrometer.read()
background_intensity = background["peak_intensity"]
```

### 3. Excitation Scan Loop
```python
wavelengths = []
intensities = []

for wavelength in range(start_wavelength, end_wavelength + 1, step_size):
    # Set laser wavelength
    await laser.set("wavelength_nm", wavelength)
    await asyncio.sleep(0.5)  # Allow wavelength to stabilize

    # Enable laser output
    await laser.set("output_enabled", True)
    await asyncio.sleep(0.1)  # Settling time

    # Measure fluorescence
    data = await spectrometer.read()
    intensity = data["peak_intensity"] - background_intensity

    # Store data
    wavelengths.append(wavelength)
    intensities.append(intensity)

    # Disable laser between measurements (optional)
    await laser.set("output_enabled", False)
```

### 4. Data Analysis
```python
def analyse(data: xr.Dataset, params: dict) -> dict:
    import numpy as np
    from scipy.signal import find_peaks

    wavelengths = data["excitation_wavelengths"].values
    intensities = data["fluorescence_intensity"].values

    # Find excitation maximum
    max_idx = np.argmax(intensities)
    max_wavelength = wavelengths[max_idx]
    max_intensity = intensities[max_idx]

    # Find FWHM
    half_max = max_intensity / 2
    indices = np.where(intensities >= half_max)[0]
    if len(indices) > 1:
        fwhm = wavelengths[indices[-1]] - wavelengths[indices[0]]
    else:
        fwhm = float("nan")

    # Find all peaks
    peaks, properties = find_peaks(
        intensities,
        prominence=max_intensity * 0.1,
        width=3
    )

    peak_wavelengths = wavelengths[peaks].tolist()
    peak_intensities = intensities[peaks].tolist()

    return {
        "excitation_maximum_nm": float(max_wavelength),
        "maximum_intensity": float(max_intensity),
        "fwhm_nm": float(fwhm),
        "peak_wavelengths": peak_wavelengths,
        "peak_intensities": peak_intensities,
        "total_integrated_intensity": float(np.trapz(intensities, wavelengths))
    }
```

## GUI Panel for Monitoring
```python
from labpilot_core.qt.dsl import *

w = window("Excitation Scan", layout="vertical")

# Real-time scan progress
w.add(scatter_plot(
    x_source="workflow.current_wavelengths",
    y_source="workflow.fluorescence_intensities",
    xlabel="Excitation Wavelength (nm)",
    ylabel="Fluorescence Intensity"
))

# Scan parameters
w.add(row(
    slider("Start λ", "workflow", "start_wavelength", 400, 700, 1),
    slider("End λ", "workflow", "end_wavelength", 500, 800, 1),
    slider("Step", "workflow", "step_size", 0.5, 10, 0.5),
    slider("Power", "laser", "power_percent", 1, 50, 1)
))

# Current status
w.add(row(
    value_display("Current λ", "laser.wavelength_nm", "{:.1f}", "nm"),
    value_display("Signal", "spectrometer.peak_intensity", "{:.0f}", "counts"),
    value_display("Progress", "workflow.progress_percent", "{:.1f}", "%"),
    text_display("Status", "workflow.status")
))

# Control buttons
w.add(row(
    button("Start Scan", "start", "workflow"),
    button("Pause", "stop", "workflow"),
    button("Resume", "start", "workflow"),
    button("Save Data", "trigger", "workflow")
))

show(w)
```

## Common Variations

### Emission Scan
Fix excitation wavelength, scan emission monochromator or use full spectrum from spectrometer.

### 2D Excitation-Emission Map
Nested loops scanning both excitation and emission wavelengths to create fluorescence landscape.

### Time-Resolved Fluorescence
Add time delays between excitation pulse and detection for lifetime measurements.

### Power Dependence
Include laser power as another scan parameter to study saturation effects.

## Data Output Format
- Primary: Excitation wavelength vs Fluorescence intensity
- Metadata: Laser power, integration time, temperature, etc.
- Analysis results: Peak wavelengths, FWHM, integrated intensity
- Optional: Full spectra at each excitation wavelength

## Considerations
- **Photobleaching**: Use minimum laser power necessary
- **Thermal Stability**: Allow thermal equilibration between measurements
- **Background Subtraction**: Essential for quantitative results
- **Wavelength Calibration**: Verify both excitation and emission calibration
- **Linear Response**: Check detector is not saturated