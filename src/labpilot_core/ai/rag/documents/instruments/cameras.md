# Camera Parameters and Controls

This document describes common parameters for scientific cameras in LabPilot.

## Common Parameters

### Exposure Settings
- `exposure_ms` (0.1-60000): Exposure time in milliseconds
- `exposure_s` (0.0001-60): Exposure time in seconds (alternative unit)
- `gain` (1-100): Analog gain multiplier
- `gain_db` (0-40): Gain in decibels (some cameras)

### Readout Settings
- `binning` ("1x1", "2x2", "4x4", "8x8"): Pixel binning mode
- `readout_speed` ("slow", "medium", "fast"): ADC readout rate
- `roi_x`, `roi_y`, `roi_width`, `roi_height`: Region of Interest settings

### Sensor Information
- `sensor_width`, `sensor_height` (readonly): Sensor dimensions in pixels
- `pixel_size_um` (readonly): Physical pixel size in micrometers
- `bit_depth` (readonly): ADC bit depth (12, 14, 16 bits)
- `sensor_type` (readonly): "CCD", "CMOS", "EMCCD", "sCMOS"

### Output Data
- `frame` or `image`: 2D array of pixel intensities
- `frame_max`: Maximum pixel value in current frame
- `frame_mean`: Mean pixel value in current frame
- `roi_data`: ROI region data when ROI is active
- `roi_statistics`: Statistics (mean, max, std) of ROI region

### Temperature Control (Cooled Cameras)
- `temperature`: Current sensor temperature (°C)
- `target_temperature`: Setpoint for cooling (°C)
- `cooling_enabled`: Enable/disable thermoelectric cooling
- `temperature_stable`: Whether temperature has stabilized

## Manufacturer-Specific Features

### Andor (Clara, Zyla, Marana, Newton)
- Advanced EMCCD gain control (`em_gain`)
- Spurious noise filter (`spurious_noise_filter`)
- Baseline clamping (`baseline_clamp`)
- Frame transfer modes for fast kinetics

### Hamamatsu (ORCA series)
- Lightsheet readout modes
- Precise exposure timing
- Multiple trigger modes
- Defect correction algorithms

### Thorlabs (Quantalux, Zelux, Kiralux)
- Simple USB3/GigE interface
- Color and monochrome variants
- Compact form factor
- Basic exposure/gain control

### Princeton Instruments (PIXIS, ProEM, PyLoN)
- Advanced CCD control
- Precise temperature regulation
- Multiple readout ports
- Spectroscopy-optimized sensors

### Basler (ace, pulse, boost)
- Industrial-grade reliability
- GigE Vision and USB3 Vision
- Programmable I/O
- Advanced trigger capabilities

### PCO (pco.edge, pco.flim, pco.pixelfly)
- High-speed sCMOS technology
- Global shutter operation
- Low noise electronics
- Extended dynamic range

## Common Use Cases

### Live Image Display
```python
image_view(
    source="camera.frame",
    colormap="inferno",
    show_histogram=True,
    show_roi=True
)
```

### Exposure Control
```python
slider(
    "Exposure", "camera", "exposure_ms",
    min=0.1, max=5000, step=0.1
)
```

### ROI Statistics
```python
value_display(
    "ROI Mean", "camera.roi_mean",
    format="{:.1f}", unit="counts"
)
```

### Temperature Monitoring
```python
value_display(
    "Sensor Temp", "camera.temperature",
    format="{:.1f}", unit="°C"
)
```

## Typical Workflows

1. **Fluorescence Imaging**: Long exposures with cooled CCD/sCMOS
2. **Brightfield Microscopy**: Fast CMOS imaging with short exposures
3. **Time-lapse Imaging**: Automated exposure sequences
4. **High-speed Imaging**: Fast frame rates with reduced ROI
5. **Quantitative Imaging**: Calibrated intensities for analysis

## Connection Types
- USB 3.0/3.1 (most common for lab cameras)
- GigE Vision (industrial standard)
- Camera Link (high-speed applications)
- CoaXPress (very high-speed applications)
- PCIe (frame grabber cards)

## Acquisition Modes
- **Single Shot**: One frame per trigger
- **Continuous**: Free-running acquisition
- **Triggered**: External trigger synchronization
- **Burst Mode**: Multiple frames per trigger
- **Kinetic Series**: Time-series with defined intervals

## Performance Considerations
- **Quantum Efficiency**: Sensor sensitivity at different wavelengths
- **Dark Noise**: Thermal noise increases with temperature and exposure
- **Read Noise**: Electronic noise from ADC and amplifiers
- **Dynamic Range**: Ratio of full well to read noise
- **Frame Rate**: Limited by exposure time and readout speed