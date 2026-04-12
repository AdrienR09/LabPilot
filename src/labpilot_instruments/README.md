# LabPilot Instruments

Complete instrument library for LabPilot, organized separately from the core framework.

## Organization

```
labpilot_instruments/
├── catalog/           # Instrument metadata and discovery
│   └── __init__.py   # Comprehensive catalog (88 instruments)
└── adapters/         # Adapter implementations by backend
    ├── mock/         # Mock/simulated instruments (36)
    ├── pymeasure/    # PyMeasure library instruments (44+)
    ├── pylablib/     # PyLabLib library adapters
    └── custom/       # Custom implementations
```

## Features

### Comprehensive Catalog
- **88 instruments** catalogued and classified
- **36 Mock adapters** for testing and development
- **44+ PyMeasure** instruments (Keithley, SRS, Lakeshore, Tektronix, etc.)
- **8 Test fixtures** with high-fidelity simulations

### Discovery & Search
```python
from labpilot_instruments.catalog import (
    INSTRUMENT_CATALOG,
    get_instruments_by_type,
    get_instruments_by_backend,
    get_instruments_by_manufacturer,
    get_instruments_by_tag,
    find_adapter,
)

# Find all spectrometers
spectrometers = get_instruments_by_tag("spectrometer")

# Get Keithley instruments
keithley_gear = get_instruments_by_manufacturer("Keithley")

# Find 1D detectors (oscilloscopes, spectrum analyzers)
oscilloscopes = get_instruments_by_type(InstrumentType.DETECTOR_1D)

# Get all PyMeasure-based instruments
pymeasure_instruments = get_instruments_by_backend(InstrumentBackend.PYMEASURE)
```

### Classification System

**By Instrument Type:**
- **Detector 0D**: Scalar measurements (power, temperature, resistance)
- **Detector 1D**: Array data (spectra, waveforms, traces)
- **Detector 2D**: Image data (cameras, thermal imaging)
- **Actuator 0D**: Binary controls (on/off, state)
- **Actuator 1D**: Single-axis motion (motors, focus drives)
- **Actuator ND**: Multi-axis control (stages, scanners)
- **Source**: Signal generation (lasers, power supplies, waveform gens)

**By Backend:**
- **mock**: Simulated instruments for testing
- **pymeasure**: 44+ real instruments via PyMeasure library
- **pylablib**: Camera and motion control via PyLabLib
- **test_fixture**: High-fidelity simulation fixtures
- **custom**: Custom implementations

## PyMeasure Instruments

The catalog includes 44+ instruments from the PyMeasure library:

### Keithley (13 instruments)
- Source Meter Units: 2400, 2450, 2600, 2601, 2602, 2604
- Current Sources: 6221, 6485
- Multimeters: 2000, 2001, 2002, 2700, 2182

### Keysight/Agilent (6 instruments)
- Multimeters: 34401A, 34410A, 34461A
- Power Supplies: E3631A
- RF & Power: E8257D, E4418B

### Lakeshore (6 instruments)
- Temperature Monitors: 218, 224
- Temperature Controllers: 331, 336
- Magnetic Field: 425, 475

### SRS (5 instruments)
- Lock-in Amplifiers: SR830, SR844, SR865
- Function Generators: DS360, DG645

### Tektronix (6 instruments)
- Oscilloscopes: TDS2024, TDS2104, DPO2024, MSO2024
- Function Generators: AFG2225, AFG3022

### Rigol (4 instruments)
- Oscilloscopes: DS1102E, DS2072
- Function Generators: DG1022, DG4162

### Others
- Anritsu: Spectrum Analyzers (2)
- Newport: Power Meters (2)

## Usage

### From Core Framework
```python
from labpilot_instruments.catalog import find_adapter

# Find instrument metadata
metadata = find_adapter("mock_spectrometer")
print(f"Type: {metadata.instrument_type}")
print(f"Backend: {metadata.backend}")
print(f"Tags: {metadata.tags}")
```

### For UI Generation
```python
from labpilot_instruments.catalog import get_instruments_by_type, InstrumentType

# Get all 1D detectors for spectrum plotting
spectrum_instruments = get_instruments_by_type(InstrumentType.DETECTOR_1D)

for instrument in spectrum_instruments:
    # Auto-generate UI component based on type
    ui_component = create_detector_1d_ui(instrument)
```

### For Adapter Discovery
```python
from labpilot_core.adapters._base import adapter_registry
from labpilot_instruments.catalog import find_adapter

# Find adapter by catalog metadata
metadata = find_adapter("keithley_2400")

# Instantiate and use adapter
adapter_class = adapter_registry.get(metadata.adapter_key)
adapter = adapter_class(resource="GPIB::24::INSTR")
await adapter.connect()
data = await adapter.read()
```

## Adding New Instruments

1. **For Mock Instruments**: Add to `src/labpilot_core/adapters/mock/*.py` and implement AdapterBase
2. **For PyMeasure**: Update `labpilot_instruments/catalog/__init__.py` INSTRUMENT_CATALOG
3. **Register**: Call `adapter_registry.register(key, AdapterClass)`
4. **Document**: Add to appropriate list with metadata (type, tags, connection types)

## Future Expansion

- Add more PyMeasure instruments (200+ available)
- Custom adapter implementations for specialized hardware
- Instrument grouping for common workflows (e.g., "fluorescence microscope", "spectroscopy setup")
- Configuration templates for quick instrument setup
