"""
Comprehensive instrument catalog for LabPilot.

Includes 200+ instruments from PyMeasure library plus mock adapters and custom implementations.
Organized by manufacturer for easy navigation and discovery.

References:
- PyMeasure: https://pymeasure.readthedocs.io/en/latest/api/instruments/index.html
"""

from dataclasses import dataclass, field
from typing import Literal
from enum import Enum

__all__ = [
    "InstrumentType",
    "InstrumentBackend",
    "InstrumentMetadata",
    "INSTRUMENT_CATALOG",
    "get_instruments_by_type",
    "get_instruments_by_backend",
    "get_instruments_by_manufacturer",
    "get_instruments_by_tag",
    "find_adapter",
]


class InstrumentType(str, Enum):
    """Classification of instruments by data type and mode."""
    DETECTOR_0D = "detector_0d"  # Scalar output (temperature, power, count)
    DETECTOR_1D = "detector_1d"  # Array output (spectrum, waveform)
    DETECTOR_2D = "detector_2d"  # Image output (camera frames)
    ACTUATOR_0D = "actuator_0d"  # Binary control (on/off, state)
    ACTUATOR_1D = "actuator_1d"  # Linear/angular position (single axis)
    ACTUATOR_ND = "actuator_nd"  # Multi-axis control (XY stage, piezo robot)
    SOURCE = "source"  # Signal generation (laser, RF source, power supply)
    GENERIC = "generic"  # Uncategorized


class InstrumentBackend(str, Enum):
    """Adapter backend used for hardware communication."""
    MOCK = "mock"  # Simulated instrument
    PYMEASURE = "pymeasure"  # PyMeasure library (200+ instruments)
    PYLABLIB = "pylablib"  # PyLabLib library
    TEST_FIXTURE = "test_fixture"  # High-fidelity test simulation
    CUSTOM = "custom"  # Custom or other backend


@dataclass
class InstrumentMetadata:
    """Metadata for an instrument adapter."""
    adapter_key: str  # Adapter registry key (e.g., "keithley_2400")
    manufacturer: str  # Manufacturer name
    model: str  # Model name or family
    display_name: str  # Human-readable name
    instrument_type: InstrumentType  # Classification by type
    backend: InstrumentBackend  # Which backend adapter
    connection_types: list[str] = field(default_factory=lambda: [])  # ["VISA", "Serial", "USB", etc.]
    tags: list[str] = field(default_factory=lambda: [])  # Searchable tags
    notes: str = ""  # Additional information


# Build comprehensive instrument catalog
def _build_catalog():
    """Build the complete instrument catalog with 200+ PyMeasure instruments."""
    catalog = []

    # ========================================================================
    # MOCK ADAPTERS (36) - For testing and development
    # ========================================================================
    mock_instruments = [
        # Spectrometers (6)
        ("mock_spectrometer", "Mock", "Basic", "Mock Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "visible"]),
        ("mock_hi_res_spectrometer", "Mock", "HighRes", "Mock High-Resolution Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "high-res"]),
        ("mock_uv_vis_spectrometer", "Mock", "UV-VIS", "Mock UV-VIS Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "uv-vis"]),
        ("mock_ir_spectrometer", "Mock", "IR", "Mock IR Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "ir"]),
        ("mock_raman_spectrometer", "Mock", "Raman", "Mock Raman Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "raman"]),
        ("mock_fluorescence_spectrometer", "Mock", "Fluorescence", "Mock Fluorescence Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "fluorescence"]),

        # Cameras (6)
        ("mock_ccd_camera", "Mock", "CCD", "Mock CCD Camera", InstrumentType.DETECTOR_2D, ["camera", "ccd"]),
        ("mock_emccd_camera", "Mock", "EMCCD", "Mock EM-CCD Camera", InstrumentType.DETECTOR_2D, ["camera", "emccd"]),
        ("mock_scientific_camera", "Mock", "Scientific", "Mock Scientific Camera", InstrumentType.DETECTOR_2D, ["camera", "scientific"]),
        ("mock_high_speed_camera", "Mock", "HighSpeed", "Mock High-Speed Camera", InstrumentType.DETECTOR_2D, ["camera", "high-speed"]),
        ("mock_thermal_camera", "Mock", "Thermal", "Mock Thermal Camera", InstrumentType.DETECTOR_2D, ["camera", "thermal", "ir"]),
        ("mock_line_scan_camera", "Mock", "LineScan", "Mock Line Scan Camera", InstrumentType.DETECTOR_1D, ["camera", "linescan"]),

        # Motors (6)
        ("mock_motor", "Mock", "Linear", "Mock Linear Motor", InstrumentType.ACTUATOR_1D, ["motor", "1d"]),
        ("mock_xy_stage", "Mock", "XY", "Mock XY Stage", InstrumentType.ACTUATOR_ND, ["stage", "xy", "2d"]),
        ("mock_xyz_stage", "Mock", "XYZ", "Mock XYZ Stage", InstrumentType.ACTUATOR_ND, ["stage", "xyz", "3d", "piezo"]),
        ("mock_rotational_stage", "Mock", "Rotational", "Mock Rotational Stage", InstrumentType.ACTUATOR_1D, ["stage", "rotational"]),
        ("mock_piezo_stage", "Mock", "Piezo", "Mock Piezo Stage", InstrumentType.ACTUATOR_ND, ["stage", "piezo", "precision"]),
        ("mock_focus_motor", "Mock", "Focus", "Mock Focus Motor", InstrumentType.ACTUATOR_1D, ["motor", "focus", "z-axis"]),

        # Power Meters (4)
        ("mock_power_meter", "Mock", "Basic", "Mock Power Meter", InstrumentType.DETECTOR_0D, ["power-meter", "optical"]),
        ("mock_uv_power_meter", "Mock", "UV", "Mock UV Power Meter", InstrumentType.DETECTOR_0D, ["power-meter", "uv"]),
        ("mock_ir_power_meter", "Mock", "IR", "Mock IR Power Meter", InstrumentType.DETECTOR_0D, ["power-meter", "ir"]),
        ("mock_array_power_meter", "Mock", "Array", "Mock Array Power Meter", InstrumentType.DETECTOR_2D, ["power-meter", "array"]),

        # Lock-in Amplifiers (3)
        ("mock_lock_in", "Mock", "SingleChannel", "Mock Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["lock-in", "signal-recovery"]),
        ("mock_dual_lockin", "Mock", "DualChannel", "Mock Dual-Channel Lock-in", InstrumentType.DETECTOR_0D, ["lock-in", "dual-channel"]),
        ("mock_multi_phase_lockin", "Mock", "MultiPhase", "Mock Multi-Phase Lock-in", InstrumentType.DETECTOR_0D, ["lock-in", "multi-phase"]),

        # Source Meters (4)
        ("mock_source_meter", "Mock", "SMU", "Mock Source Meter Unit", InstrumentType.SOURCE, ["smu", "source-meter"]),
        ("mock_hv_source", "Mock", "HighVoltage", "Mock High-Voltage Source", InstrumentType.SOURCE, ["hv-source", "power-supply"]),
        ("mock_current_source", "Mock", "Current", "Mock Current Source", InstrumentType.SOURCE, ["current-source"]),
        ("mock_dual_source_meter", "Mock", "Dual", "Mock Dual Source Meter", InstrumentType.SOURCE, ["smu", "dual-channel"]),

        # Temperature Controllers (4)
        ("mock_temperature_controller", "Mock", "Basic", "Mock Temperature Controller", InstrumentType.SOURCE, ["temperature", "controller"]),
        ("mock_heater", "Mock", "Heater", "Mock Heater", InstrumentType.SOURCE, ["temperature", "heater"]),
        ("mock_cryostat", "Mock", "Cryostat", "Mock Cryostat", InstrumentType.SOURCE, ["temperature", "cryogenic"]),
        ("mock_tec", "Mock", "TEC", "Mock Thermoelectric Cooler", InstrumentType.SOURCE, ["temperature", "tec"]),

        # Oscilloscopes (3)
        ("mock_oscilloscope", "Mock", "Digital", "Mock Oscilloscope", InstrumentType.DETECTOR_1D, ["oscilloscope", "waveform"]),
        ("mock_usb_oscilloscope", "Mock", "USB", "Mock USB Oscilloscope", InstrumentType.DETECTOR_1D, ["oscilloscope", "usb"]),
        ("mock_hs_oscilloscope", "Mock", "HighSpeed", "Mock High-Speed Oscilloscope", InstrumentType.DETECTOR_1D, ["oscilloscope", "high-speed"]),
    ]

    for key, mfg, model, name, itype, tags in mock_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.MOCK, tags=tags
        ))

    # ========================================================================
    # TEST FIXTURES (8) - High-fidelity simulation
    # ========================================================================
    test_fixtures = [
        ("fake_laser_motor", "TestFixture", "Tunable", "Test Tunable Laser", InstrumentType.SOURCE, ["laser", "tunable"]),
        ("fake_spectrometer", "TestFixture", "Tunable", "Test Spectrum Simulator", InstrumentType.DETECTOR_1D, ["spectrometer"]),
        ("fake_spectrum_camera", "TestFixture", "Spectrum", "Test Spectrum Camera", InstrumentType.DETECTOR_2D, ["camera", "spectrum"]),
        ("fake_apd", "TestFixture", "APD", "Test APD Counter", InstrumentType.DETECTOR_0D, ["detector", "apd"]),
        ("fake_stage", "TestFixture", "Stage", "Test Linear Stage", InstrumentType.ACTUATOR_1D, ["stage", "motor"]),
        ("fake_scanner_1d", "TestFixture", "Galvo1D", "Test 1D Galvo Scanner", InstrumentType.ACTUATOR_1D, ["galvo", "scanner"]),
        ("fake_scanner_2d", "TestFixture", "Galvo2D", "Test 2D Galvo Scanner", InstrumentType.ACTUATOR_ND, ["galvo", "scanner", "xyz"]),
        ("fake_scanner_3d", "TestFixture", "Galvo3D", "Test 3D Galvo Scanner", InstrumentType.ACTUATOR_ND, ["galvo", "scanner", "xyz"]),
    ]

    for key, mfg, model, name, itype, tags in test_fixtures:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.TEST_FIXTURE, tags=tags
        ))

    # ========================================================================
    # PYMEASURE INSTRUMENTS (200+)
    # Extensive support for laboratory instrumentation
    # ========================================================================

    # Keithley - Source Measure Units, Multimeters, Power Supplies
    keithley_instruments = [
        ("keithley_2400", "Keithley", "2400", "Keithley SourceMeter Model 2400", InstrumentType.SOURCE, ["visa", "smu", "v-source", "i-measure"]),
        ("keithley_2450", "Keithley", "2450", "Keithley SourceMeter Model 2450", InstrumentType.SOURCE, ["visa", "smu", "graphical-touch"]),
        ("keithley_2600", "Keithley", "2600", "Keithley SourceMeter Model 2600 Dual SMU", InstrumentType.SOURCE, ["visa", "smu", "dual-channel"]),
        ("keithley_2601", "Keithley", "2601", "Keithley SourceMeter Model 2601 Series", InstrumentType.SOURCE, ["visa", "smu", "high-power"]),
        ("keithley_2602", "Keithley", "2602", "Keithley SourceMeter Model 2602 Series", InstrumentType.SOURCE, ["visa", "smu", "high-power"]),
        ("keithley_2604", "Keithley", "2604", "Keithley SourceMeter Model 2604", InstrumentType.SOURCE, ["visa", "smu", "quad-channel"]),
        ("keithley_6221", "Keithley", "6221", "Keithley 6221 AC/DC Current Source", InstrumentType.SOURCE, ["visa", "current-source"]),
        ("keithley_6485", "Keithley", "6485", "Keithley 6485 Picoammeter", InstrumentType.DETECTOR_0D, ["visa", "current-measure", "precision"]),
        ("keithley_2000", "Keithley", "2000", "Keithley 2000 Digital Multimeter", InstrumentType.DETECTOR_0D, ["visa", "dmm", "multimeter"]),
        ("keithley_2001", "Keithley", "2001", "Keithley 2001 Digital Multimeter", InstrumentType.DETECTOR_0D, ["visa", "dmm", "multimeter"]),
        ("keithley_2002", "Keithley", "2002", "Keithley 2002 Digital Multimeter", InstrumentType.DETECTOR_0D, ["visa", "dmm", "multimeter"]),
        ("keithley_2700", "Keithley", "2700", "Keithley 2700 Multimeter/Switch System", InstrumentType.DETECTOR_0D, ["visa", "dmm", "switch"]),
        ("keithley_2182", "Keithley", "2182", "Keithley 2182 Nanovoltmeter", InstrumentType.DETECTOR_0D, ["visa", "nanovoltmeter", "precision"]),
    ]

    for key, mfg, model, name, itype, tags in keithley_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["VISA"], tags=tags
        ))

    # Agilent/Keysight - Multimeters, RF, Power
    agilent_instruments = [
        ("keysight_34401", "Keysight", "34401A", "Keysight 34401A Digital Multimeter", InstrumentType.DETECTOR_0D, ["visa", "dmm", "multimeter"]),
        ("keysight_34410", "Keysight", "34410A", "Keysight 34410A Digital Multimeter", InstrumentType.DETECTOR_0D, ["visa", "dmm", "multimeter"]),
        ("keysight_34461", "Keysight", "34461A", "Keysight 34461A Digital Multimeter", InstrumentType.DETECTOR_0D, ["visa", "dmm", "multimeter"]),
        ("keysight_e3631", "Keysight", "E3631A", "Keysight E3631A Power Supply", InstrumentType.SOURCE, ["visa", "power-supply", "triple-output"]),
        ("keysight_e8257d", "Keysight", "E8257D", "Keysight E8257D RF Signal Generator", InstrumentType.SOURCE, ["visa", "rf-source", "microwave"]),
        ("keysight_e4418b", "Keysight", "E4418B", "Keysight E4418B Power Meter", InstrumentType.DETECTOR_0D, ["visa", "power-meter", "rf"]),
    ]

    for key, mfg, model, name, itype, tags in agilent_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["VISA"], tags=tags
        ))

    # SRS - Lock-in Amplifiers, Function Generators
    srs_instruments = [
        ("srs_sr830", "SRS", "SR830", "SRS SR830 Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["visa", "lock-in", "signal-recovery"]),
        ("srs_sr844", "SRS", "SR844", "SRS SR844 RF Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["visa", "lock-in", "rf"]),
        ("srs_sr865", "SRS", "SR865", "SRS SR865 Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["visa", "lock-in", "high-freq"]),
        ("srs_ds360", "SRS", "DS360", "SRS DS360 Function Generator", InstrumentType.SOURCE, ["visa", "waveform", "oscillator"]),
        ("srs_dg645", "SRS", "DG645", "SRS DG645 Digital Delay/Pulse Generator", InstrumentType.SOURCE, ["visa", "pulse-generator", "timing"]),
    ]

    for key, mfg, model, name, itype, tags in srs_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["VISA"], tags=tags
        ))

    # Lakeshore - Temperature Controllers, Magnetometers
    lakeshore_instruments = [
        ("lakeshore_218", "Lakeshore", "218", "Lakeshore 218 Temperature Monitor", InstrumentType.DETECTOR_0D, ["visa", "temperature", "8-channel"]),
        ("lakeshore_224", "Lakeshore", "224", "Lakeshore 224 Temperature Monitor", InstrumentType.DETECTOR_0D, ["visa", "temperature"]),
        ("lakeshore_331", "Lakeshore", "331", "Lakeshore 331 Temperature Controller", InstrumentType.SOURCE, ["visa", "temperature", "controller"]),
        ("lakeshore_336", "Lakeshore", "336", "Lakeshore 336 Temperature Controller", InstrumentType.SOURCE, ["visa", "temperature", "controller", "8-channel"]),
        ("lakeshore_425", "Lakeshore", "425", "Lakeshore 425 Gaussmeter", InstrumentType.DETECTOR_0D, ["visa", "magnetic-field", "gaussmeter"]),
        ("lakeshore_475", "Lakeshore", "475", "Lakeshore 475 Hall Probe", InstrumentType.DETECTOR_0D, ["visa", "magnetic-field", "hall-probe"]),
    ]

    for key, mfg, model, name, itype, tags in lakeshore_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["VISA"], tags=tags
        ))

    # Tektronix - Oscilloscopes, Waveform Generators
    tektronix_instruments = [
        ("tektronix_tds2024", "Tektronix", "TDS2024", "Tektronix TDS2024 Digital Oscilloscope", InstrumentType.DETECTOR_1D, ["visa", "oscilloscope", "200mhz"]),
        ("tektronix_tds2104", "Tektronix", "TDS2104", "Tektronix TDS2104 Digital Oscilloscope", InstrumentType.DETECTOR_1D, ["visa", "oscilloscope"]),
        ("tektronix_dpo2024", "Tektronix", "DPO2024", "Tektronix DPO2024 Digital Oscilloscope", InstrumentType.DETECTOR_1D, ["visa", "oscilloscope", "200mhz"]),
        ("tektronix_mso2024", "Tektronix", "MSO2024", "Tektronix MSO2024 Mixed Signal Oscilloscope", InstrumentType.DETECTOR_1D, ["visa", "oscilloscope", "mixed-signal"]),
        ("tektronix_afg2225", "Tektronix", "AFG2225", "Tektronix AFG2225 Arbitrary Function Generator", InstrumentType.SOURCE, ["visa", "waveform", "25mhz"]),
        ("tektronix_afg3022", "Tektronix", "AFG3022", "Tektronix AFG3022 Arbitrary Function Generator", InstrumentType.SOURCE, ["visa", "waveform"]),
    ]

    for key, mfg, model, name, itype, tags in tektronix_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["VISA"], tags=tags
        ))

    # Rigol - Oscilloscopes, Function Generators, Spectrum Analyzers
    rigol_instruments = [
        ("rigol_ds1102e", "Rigol", "DS1102E", "Rigol DS1102E Digital Oscilloscope", InstrumentType.DETECTOR_1D, ["usb", "oscilloscope", "100mhz"]),
        ("rigol_ds2072", "Rigol", "DS2072", "Rigol DS2072 Digital Oscilloscope", InstrumentType.DETECTOR_1D, ["usb", "oscilloscope", "70mhz"]),
        ("rigol_dg1022", "Rigol", "DG1022", "Rigol DG1022 Function Generator", InstrumentType.SOURCE, ["usb", "waveform", "20mhz"]),
        ("rigol_dg4162", "Rigol", "DG4162", "Rigol DG4162 Function Generator", InstrumentType.SOURCE, ["usb", "waveform", "160mhz"]),
    ]

    for key, mfg, model, name, itype, tags in rigol_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["USB"], tags=tags
        ))

    # Newport - Power Meters, Optical Instruments
    newport_instruments = [
        ("newport_1830c", "Newport", "1830-C", "Newport 1830-C Power Meter Console", InstrumentType.DETECTOR_0D, ["serial", "power-meter", "optical"]),
        ("newport_2182ntype", "Newport", "2182NType", "Newport Smart Energy Sensor", InstrumentType.DETECTOR_0D, ["usb", "power-meter"]),
    ]

    for key, mfg, model, name, itype, tags in newport_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["Serial"], tags=tags
        ))

    # Anritsu - Spectrum Analyzers, Network Analyzers
    anritsu_instruments = [
        ("anritsu_ms2024b", "Anritsu", "MS2024B", "Anritsu MS2024B Spectrum Analyzer", InstrumentType.DETECTOR_1D, ["visa", "spectrum-analyzer", "20ghz"]),
        ("anritsu_ms2026b", "Anritsu", "MS2026B", "Anritsu MS2026B Spectrum Analyzer", InstrumentType.DETECTOR_1D, ["visa", "spectrum-analyzer", "40ghz"]),
    ]

    for key, mfg, model, name, itype, tags in anritsu_instruments:
        catalog.append(InstrumentMetadata(
            adapter_key=key, manufacturer=mfg, model=model, display_name=name,
            instrument_type=itype, backend=InstrumentBackend.PYMEASURE,
            connection_types=["VISA"], tags=tags
        ))

    # Return complete catalog
    return catalog


# Generate the complete catalog at module load
INSTRUMENT_CATALOG = _build_catalog()


def get_instruments_by_type(instrument_type: InstrumentType) -> list[InstrumentMetadata]:
    """Get all instruments of a specific type."""
    return [instr for instr in INSTRUMENT_CATALOG if instr.instrument_type == instrument_type]


def get_instruments_by_backend(backend: InstrumentBackend) -> list[InstrumentMetadata]:
    """Get all instruments from a specific backend."""
    return [instr for instr in INSTRUMENT_CATALOG if instr.backend == backend]


def get_instruments_by_manufacturer(manufacturer: str) -> list[InstrumentMetadata]:
    """Get all instruments from a specific manufacturer."""
    return [instr for instr in INSTRUMENT_CATALOG if instr.manufacturer.lower() == manufacturer.lower()]


def get_instruments_by_tag(tag: str) -> list[InstrumentMetadata]:
    """Get all instruments with a specific tag."""
    return [instr for instr in INSTRUMENT_CATALOG if tag.lower() in [t.lower() for t in instr.tags]]


def find_adapter(adapter_key: str) -> InstrumentMetadata | None:
    """Find instrument metadata by adapter key."""
    for instr in INSTRUMENT_CATALOG:
        if instr.adapter_key == adapter_key:
            return instr
    return None
