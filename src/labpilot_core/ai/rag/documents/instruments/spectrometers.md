# Spectrometer Parameters and Controls

This document describes common parameters and capabilities for spectrometer instruments in LabPilot.

## Common Parameters

### Timing Controls
- `integration_time_ms` (1-60000): Integration time in milliseconds
- `averaging_count` (1-1000): Number of spectra to average
- `trigger_mode` ("software", "hardware", "external"): Acquisition trigger source

### Spectral Settings
- `wavelength_min_nm` (readonly): Minimum wavelength of detector
- `wavelength_max_nm` (readonly): Maximum wavelength of detector
- `pixel_count` (readonly): Number of detector pixels
- `spectral_resolution_nm` (readonly): Spectral resolution per pixel

### Output Data
- `spectrum` or `intensities`: Array of intensity values (counts)
- `wavelengths`: Array of wavelength values (nm)
- `peak_wavelength`: Detected peak position (nm)
- `peak_intensity`: Peak intensity value (counts)
- `integration_time_actual`: Actual integration time used

### Status Information
- `temperature`: Detector temperature (°C)
- `acquisition_status`: Current acquisition state
- `dark_corrected`: Whether dark correction is applied
- `saturation_level`: Detector saturation threshold

## Manufacturer-Specific Features

### Ocean Insight (USB2000, USB4000, QE65000)
- Built-in dark current correction
- Automatic gain control on some models
- Temperature monitoring on cooled detectors
- Strobe lamp control for some models

### Andor (Shamrock, Newton, iDus)
- CCD/EMCCD temperature control (`target_temperature`)
- Grating position control (`grating_position`)
- Slit width control (`entrance_slit_um`, `exit_slit_um`)
- Kinetic series acquisition modes

### Thorlabs (CCS Series)
- Compact USB-powered design
- Fixed wavelength range (typically 350-700nm or 500-1000nm)
- Simple software triggering
- No temperature control

## Common Use Cases

### Real-time Display
```python
spectrum_plot(
    source="spec.spectrum",
    xlabel="Wavelength (nm)",
    ylabel="Intensity (counts)",
    show_peak=True
)
```

### Integration Time Control
```python
slider(
    "Integration Time", "spec", "integration_time_ms",
    min=1, max=10000, step=1
)
```

### Peak Monitoring
```python
value_display(
    "Peak λ", "spec.peak_wavelength",
    format="{:.2f}", unit="nm"
)
```

## Typical Workflows

1. **Laser Characterization**: Monitor laser line wavelength and intensity
2. **Fluorescence Spectroscopy**: Measure emission spectra from samples
3. **Absorption Spectroscopy**: Measure transmission through samples
4. **Raman Spectroscopy**: Measure Raman-shifted peaks from samples
5. **Wavelength Calibration**: Use known reference lines for calibration

## Connection Types
- USB (most common for lab spectrometers)
- Ethernet (high-end research instruments)
- Serial/RS232 (older instruments)
- PCIe (high-speed data acquisition)

## Performance Considerations
- Integration times: Balance signal/noise vs acquisition speed
- Averaging: Improves SNR but reduces temporal resolution
- Dark correction: Essential for quantitative measurements
- Wavelength calibration: Required for accurate spectral position