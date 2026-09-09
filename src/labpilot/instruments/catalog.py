"""Static instrument catalog: manufacturer/model/dimensionality metadata.

This complements `adapter_registry` (the source of truth for which adapters
actually exist and their `DeviceSchema`) with the extra classification the
UI needs to auto-generate a window per instrument — display name and
dimensionality (0D/1D/2D/ND) aren't part of `DeviceSchema`.

Every entry here MUST correspond to a real adapter key registered by a
module under `instruments`. Do not add speculative/unsupported
instrument models — use `adapter_registry.list()` to check what's real.

Not yet covered: plugin-discovered instrument frameworks (not a flat class
list — see instruments/README.md). For anything registered but not yet
catalogued here, use `adapter_registry.list_with_schemas()` for its live
`kind`/`tags`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    "find_instrument",
]


class InstrumentType(str, Enum):
    """Classification of instruments by data type and mode."""
    DETECTOR_0D = "detector_0d"  # Scalar output (temperature, power, count)
    DETECTOR_1D = "detector_1d"  # Array output (spectrum, waveform)
    DETECTOR_2D = "detector_2d"  # Image output (camera frames)
    DETECTOR_ND = "detector_nd"  # ND output (hyperspectral cube, etc.)
    ACTUATOR_0D = "actuator_0d"  # Binary control (on/off, state)
    ACTUATOR_1D = "actuator_1d"  # Linear/angular position (single axis)
    ACTUATOR_ND = "actuator_nd"  # Multi-axis control (XY stage, piezo)
    SOURCE = "source"  # Signal generation (laser, RF source, power supply)
    GENERIC = "generic"  # Doesn't fit the 0D/1D/2D taxonomy cleanly


class InstrumentBackend(str, Enum):
    """Adapter backend used for hardware communication."""
    MOCK = "mock"
    PYMEASURE = "pymeasure"
    PYLABLIB = "pylablib"
    TEST_FIXTURE = "test_fixture"
    VENDOR = "vendor"  # the manufacturer's own SDK, an optional extra


@dataclass
class InstrumentMetadata:
    """Metadata for an instrument adapter."""
    adapter_key: str  # Adapter registry key, must exist in adapter_registry
    manufacturer: str
    model: str
    display_name: str
    instrument_type: InstrumentType
    backend: InstrumentBackend
    connection_types: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _mock(key: str, model: str, name: str, itype: InstrumentType, tags: list[str]) -> InstrumentMetadata:
    return InstrumentMetadata(key, "Mock", model, name, itype, InstrumentBackend.MOCK, tags=tags)


def _fixture(key: str, model: str, name: str, itype: InstrumentType, tags: list[str]) -> InstrumentMetadata:
    return InstrumentMetadata(key, "TestFixture", model, name, itype, InstrumentBackend.TEST_FIXTURE, tags=tags)


def _pymeasure(key: str, mfg: str, model: str, name: str, itype: InstrumentType,
               conn: list[str], tags: list[str]) -> InstrumentMetadata:
    return InstrumentMetadata(key, mfg, model, name, itype, InstrumentBackend.PYMEASURE,
                               connection_types=conn, tags=tags)


INSTRUMENT_CATALOG: list[InstrumentMetadata] = [
    # Mock adapters (41) — src/instruments/mock/
    _mock("mock_spectrometer", "Basic", "Mock Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "visible"]),
    _mock("mock_hi_res_spectrometer", "HighRes", "Mock High-Resolution Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "high-res"]),
    _mock("mock_uv_vis_spectrometer", "UV-VIS", "Mock UV-VIS Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "uv-vis"]),
    _mock("mock_ir_spectrometer", "IR", "Mock IR Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "ir"]),
    _mock("mock_raman_spectrometer", "Raman", "Mock Raman Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "raman"]),
    _mock("mock_fluorescence_spectrometer", "Fluorescence", "Mock Fluorescence Spectrometer", InstrumentType.DETECTOR_1D, ["spectrometer", "fluorescence"]),
    _mock("mock_ccd_camera", "CCD", "Mock CCD Camera", InstrumentType.DETECTOR_2D, ["camera", "ccd"]),
    _mock("mock_emccd_camera", "EMCCD", "Mock EM-CCD Camera", InstrumentType.DETECTOR_2D, ["camera", "emccd"]),
    _mock("mock_scientific_camera", "Scientific", "Mock Scientific Camera", InstrumentType.DETECTOR_2D, ["camera", "scientific"]),
    _mock("mock_high_speed_camera", "HighSpeed", "Mock High-Speed Camera", InstrumentType.DETECTOR_2D, ["camera", "high-speed"]),
    _mock("mock_thermal_camera", "Thermal", "Mock Thermal Camera", InstrumentType.DETECTOR_2D, ["camera", "thermal", "ir"]),
    _mock("mock_line_scan_camera", "LineScan", "Mock Line Scan Camera", InstrumentType.DETECTOR_1D, ["camera", "linescan"]),
    _mock("mock_motor", "Linear", "Mock Linear Motor", InstrumentType.ACTUATOR_1D, ["motor", "1d"]),
    _mock("mock_xy_stage", "XY", "Mock XY Stage", InstrumentType.ACTUATOR_ND, ["stage", "xy", "2d"]),
    _mock("mock_xyz_stage", "XYZ", "Mock XYZ Stage", InstrumentType.ACTUATOR_ND, ["stage", "xyz", "3d", "piezo"]),
    _mock("mock_rotational_stage", "Rotational", "Mock Rotational Stage", InstrumentType.ACTUATOR_1D, ["stage", "rotational"]),
    _mock("mock_piezo_stage", "Piezo", "Mock Piezo Stage", InstrumentType.ACTUATOR_ND, ["stage", "piezo", "precision"]),
    _mock("mock_focus_motor", "Focus", "Mock Focus Motor", InstrumentType.ACTUATOR_1D, ["motor", "focus", "z-axis"]),
    _mock("mock_power_meter", "Basic", "Mock Power Meter", InstrumentType.DETECTOR_0D, ["power-meter", "optical"]),
    _mock("mock_uv_power_meter", "UV", "Mock UV Power Meter", InstrumentType.DETECTOR_0D, ["power-meter", "uv"]),
    _mock("mock_ir_power_meter", "IR", "Mock IR Power Meter", InstrumentType.DETECTOR_0D, ["power-meter", "ir"]),
    _mock("mock_array_power_meter", "Array", "Mock Array Power Meter", InstrumentType.DETECTOR_2D, ["power-meter", "array"]),
    _mock("mock_lock_in", "SingleChannel", "Mock Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["lock-in", "signal-recovery"]),
    _mock("mock_dual_lockin", "DualChannel", "Mock Dual-Channel Lock-in", InstrumentType.DETECTOR_0D, ["lock-in", "dual-channel"]),
    _mock("mock_multi_phase_lockin", "MultiPhase", "Mock Multi-Phase Lock-in", InstrumentType.DETECTOR_0D, ["lock-in", "multi-phase"]),
    _mock("mock_source_meter", "SMU", "Mock Source Meter Unit", InstrumentType.SOURCE, ["smu", "source-meter"]),
    _mock("mock_hv_source", "HighVoltage", "Mock High-Voltage Source", InstrumentType.SOURCE, ["hv-source", "power-supply"]),
    _mock("mock_current_source", "Current", "Mock Current Source", InstrumentType.SOURCE, ["current-source"]),
    _mock("mock_dual_source_meter", "Dual", "Mock Dual Source Meter", InstrumentType.SOURCE, ["smu", "dual-channel"]),
    _mock("mock_temperature_controller", "Basic", "Mock Temperature Controller", InstrumentType.SOURCE, ["temperature", "controller"]),
    _mock("mock_heater", "Heater", "Mock Heater", InstrumentType.SOURCE, ["temperature", "heater"]),
    _mock("mock_cryostat", "Cryostat", "Mock Cryostat", InstrumentType.SOURCE, ["temperature", "cryogenic"]),
    _mock("mock_tec", "TEC", "Mock Thermoelectric Cooler", InstrumentType.SOURCE, ["temperature", "tec"]),
    _mock("mock_oscilloscope", "Digital", "Mock Oscilloscope", InstrumentType.DETECTOR_1D, ["oscilloscope", "waveform"]),
    _mock("mock_usb_oscilloscope", "USB", "Mock USB Oscilloscope", InstrumentType.DETECTOR_1D, ["oscilloscope", "usb"]),
    _mock("mock_hs_oscilloscope", "HighSpeed", "Mock High-Speed Oscilloscope", InstrumentType.DETECTOR_1D, ["oscilloscope", "high-speed"]),

    # ODMR/pulsed-sensing instruments (4) — src/instruments/mock/{lasers,
    # microwave_sources,optical_modulators,pulse_rig}.py. Modeled on
    # qudi's MicrowaveInterface/PulserInterface and the real-world PyMoDAQ
    # S2QT ODMR plugin — see docs/workflows.md's ODMR notes.
    _mock("mock_laser", "Pump", "Mock CW Pump Laser", InstrumentType.SOURCE, ["laser", "cw", "odmr"]),
    _mock("mock_microwave_source", "RF", "Mock Microwave Source", InstrumentType.SOURCE, ["microwave", "rf", "signal-generator", "odmr"]),
    _mock("mock_aom", "Gate", "Mock Acousto-Optic Modulator", InstrumentType.ACTUATOR_0D, ["aom", "modulator", "gate", "odmr"]),
    _mock("mock_pulser", "TTL", "Mock Pulser", InstrumentType.GENERIC, ["pulser", "sequencer", "ttl", "odmr", "pulsed"]),
    _mock("mock_gated_counter", "TTL", "Mock Gated Counter", InstrumentType.DETECTOR_0D, ["counter", "gated", "photon", "odmr", "pulsed"]),

    # Hardware-timed scanning — src/instruments/mock/hardware_scan.py.
    # Modeled on Qudi's ScanningProbeInterface/NI hardware module: a single
    # combined position+detector device clocked as one, not a generic
    # actuator+detector pair — see core/workflow/capabilities.py's
    # HardwareTimedScanCapability and core/workflow_library/hardware_timed_scan.py.
    _mock("mock_ni_scanner", "Scanner", "Mock NI-Card Scanner", InstrumentType.GENERIC, ["ni", "daq", "scanner", "hardware-scan"]),

    # Test fixtures (9) — src/instruments/test_fixtures.py, high-fidelity simulations
    _fixture("fake_tunable_laser", "Tunable", "Test Tunable Laser", InstrumentType.SOURCE, ["laser", "tunable"]),
    _fixture("fake_spectrometer", "Tunable", "Test Spectrum Simulator", InstrumentType.DETECTOR_1D, ["spectrometer"]),
    _fixture("fake_spectrum_camera", "Spectrum", "Test Spectrum Camera", InstrumentType.DETECTOR_2D, ["camera", "spectrum"]),
    _fixture("fake_apd", "APD", "Test APD Counter", InstrumentType.DETECTOR_0D, ["detector", "apd"]),
    _fixture("fake_stage", "Stage", "Test Linear Stage", InstrumentType.ACTUATOR_1D, ["stage", "motor"]),
    _fixture("fake_scanner_1d", "Galvo1D", "Test 1D Galvo Scanner", InstrumentType.ACTUATOR_1D, ["galvo", "scanner"]),
    _fixture("fake_scanner_2d", "Galvo2D", "Test 2D Galvo Scanner", InstrumentType.ACTUATOR_ND, ["galvo", "scanner", "xyz"]),
    _fixture("fake_scanner_3d", "Galvo3D", "Test 3D Galvo Scanner", InstrumentType.ACTUATOR_ND, ["galvo", "scanner", "xyz"]),
    _fixture("fake_switch", "Switch", "Test Binary Switch", InstrumentType.ACTUATOR_0D, ["switch", "binary"]),

    # PyMeasure dedicated adapters (6) — hand-written, better schemas than the
    # generic introspection fallback. src/instruments/<Manufacturer>/<type>.py
    _pymeasure("keithley_2400", "Keithley", "2400", "Keithley SourceMeter 2400", InstrumentType.SOURCE, ["VISA"], ["visa", "smu", "v-source", "i-measure"]),
    _pymeasure("keithley_2600", "Keithley", "2600", "Keithley SourceMeter 2600 Dual SMU", InstrumentType.SOURCE, ["VISA"], ["visa", "smu", "dual-channel"]),
    _pymeasure("keithley_6221", "Keithley", "6221", "Keithley 6221 AC/DC Current Source", InstrumentType.SOURCE, ["VISA"], ["visa", "current-source"]),
    _pymeasure("srs_sr830", "SRS", "SR830", "SRS SR830 Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["VISA"], ["visa", "lock-in", "signal-recovery"]),
    _pymeasure("srs_sr860", "SRS", "SR860", "SRS SR860 Lock-in Amplifier", InstrumentType.DETECTOR_0D, ["VISA"], ["visa", "lock-in", "high-freq"]),
    _pymeasure("thorlabs_pm100", "Thorlabs", "PM100USB", "Thorlabs PM100 Power Meter", InstrumentType.DETECTOR_0D, ["VISA", "USB"], ["visa", "power-meter", "optical"]),
]


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


def find_instrument(adapter_key: str) -> InstrumentMetadata | None:
    """Find instrument metadata by adapter key."""
    for instr in INSTRUMENT_CATALOG:
        if instr.adapter_key == adapter_key:
            return instr
    return None


# Bulk-generated entries (182) — verified against installed pymeasure 0.16.0's
# real instrument classes, backed by PyMeasureGenericAdapter (introspection-based).
# instrument_type is a best-effort heuristic from the class name; GENERIC means it
# didn't cleanly match the 0D/1D/2D/actuator/source taxonomy — review before relying
# on it for UI layout.
_BULK_PYMEASURE: list[tuple[str, str, str, InstrumentType]] = [
    ("pymeasure_d_p_series_motor_controller", "anaheimautomation", "DPSeriesMotorController", InstrumentType.ACTUATOR_1D),
    ("pymeasure_a_n_c300_controller", "attocube", "ANC300Controller", InstrumentType.ACTUATOR_1D),
    ("pymeasure_e_s_p300", "newport", "ESP300", InstrumentType.ACTUATOR_1D),
    ("pymeasure_parker_g_v6", "parker", "ParkerGV6", InstrumentType.ACTUATOR_1D),
    ("pymeasure_agilent34410_a", "agilent", "Agilent34410A", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent34450_a", "agilent", "Agilent34450A", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent4284_a", "agilent", "Agilent4284A", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent4294_a", "agilent", "Agilent4294A", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent_b2981", "agilent", "AgilentB2981", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent_b2983", "agilent", "AgilentB2983", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent_b2985", "agilent", "AgilentB2985", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent_b2987", "agilent", "AgilentB2987", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent_e4980", "agilent", "AgilentE4980", InstrumentType.DETECTOR_0D),
    ("pymeasure_ametek7270", "ametek", "Ametek7270", InstrumentType.DETECTOR_0D),
    ("pymeasure_a_h2700_a", "andeenhagerling", "AH2700A", InstrumentType.DETECTOR_0D),
    ("pymeasure_nxds", "edwards", "Nxds", InstrumentType.DETECTOR_0D),
    ("pymeasure_h_p3437_a", "hp", "HP3437A", InstrumentType.DETECTOR_0D),
    ("pymeasure_h_p34401_a", "hp", "HP34401A", InstrumentType.DETECTOR_0D),
    ("pymeasure_h_p3478_a", "hp", "HP3478A", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley2000", "keithley", "Keithley2000", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley2182", "keithley", "Keithley2182", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley2700", "keithley", "Keithley2700", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley2750", "keithley", "Keithley2750", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley6517_b", "keithley", "Keithley6517B", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley_d_a_q6510", "keithley", "KeithleyDAQ6510", InstrumentType.DETECTOR_0D),
    ("pymeasure_keithley_d_m_m6500", "keithley", "KeithleyDMM6500", InstrumentType.DETECTOR_0D),
    ("pymeasure_m_k_s937_b", "mksinst", "MKS937B", InstrumentType.DETECTOR_0D),
    ("pymeasure_m_k_s974_b", "mksinst", "MKS974B", InstrumentType.DETECTOR_0D),
    ("pymeasure_ptw_d_i_a_m_e_n_t_o_r", "ptw", "ptwDIAMENTOR", InstrumentType.DETECTOR_0D),
    ("pymeasure_ptw_u_n_i_d_o_s", "ptw", "ptwUNIDOS", InstrumentType.DETECTOR_0D),
    ("pymeasure_d_s_p7225", "signalrecovery", "DSP7225", InstrumentType.DETECTOR_0D),
    ("pymeasure_d_s_p7265", "signalrecovery", "DSP7265", InstrumentType.DETECTOR_0D),
    ("pymeasure_s_r510", "srs", "SR510", InstrumentType.DETECTOR_0D),
    ("pymeasure_s_r570", "srs", "SR570", InstrumentType.DETECTOR_0D),
    ("pymeasure_t_d_s2000", "tektronix", "TDS2000", InstrumentType.DETECTOR_0D),
    ("pymeasure_smartline_v1", "thyracont", "SmartlineV1", InstrumentType.DETECTOR_0D),
    ("pymeasure_smartline_v2", "thyracont", "SmartlineV2", InstrumentType.DETECTOR_0D),
    ("pymeasure_v_s_h", "thyracont", "VSH", InstrumentType.DETECTOR_0D),
    ("pymeasure_v_s_m", "thyracont", "VSM", InstrumentType.DETECTOR_0D),
    ("pymeasure_v_s_p", "thyracont", "VSP", InstrumentType.DETECTOR_0D),
    ("pymeasure_v_s_r", "thyracont", "VSR", InstrumentType.DETECTOR_0D),
    ("pymeasure_agilent8722_e_s", "agilent", "Agilent8722ES", InstrumentType.DETECTOR_1D),
    ("pymeasure_agilent_e4408_b", "agilent", "AgilentE4408B", InstrumentType.DETECTOR_1D),
    ("pymeasure_agilent_e5062_a", "agilent", "AgilentE5062A", InstrumentType.DETECTOR_1D),
    ("pymeasure_agilent_e5270_b", "agilent", "AgilentE5270B", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s2090_a", "anritsu", "AnritsuMS2090A", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s4642_b", "anritsu", "AnritsuMS4642B", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s4644_b", "anritsu", "AnritsuMS4644B", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s4645_b", "anritsu", "AnritsuMS4645B", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s4647_b", "anritsu", "AnritsuMS4647B", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s464x_b", "anritsu", "AnritsuMS464xB", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s9710_c", "anritsu", "AnritsuMS9710C", InstrumentType.DETECTOR_1D),
    ("pymeasure_anritsu_m_s9740_a", "anritsu", "AnritsuMS9740A", InstrumentType.DETECTOR_1D),
    ("pymeasure_h_p8560_a", "hp", "HP8560A", InstrumentType.DETECTOR_1D),
    ("pymeasure_h_p8561_b", "hp", "HP8561B", InstrumentType.DETECTOR_1D),
    ("pymeasure_keysight_d_s_o_x1102_g", "keysight", "KeysightDSOX1102G", InstrumentType.DETECTOR_1D),
    ("pymeasure_keysight_p_n_a", "keysight", "KeysightPNA", InstrumentType.DETECTOR_1D),
    ("pymeasure_le_croy_t3_d_s_o1204", "lecroy", "LeCroyT3DSO1204", InstrumentType.DETECTOR_1D),
    ("pymeasure_f_s_l", "rohdeschwarz", "FSL", InstrumentType.DETECTOR_1D),
    ("pymeasure_f_s_w", "rohdeschwarz", "FSW", InstrumentType.DETECTOR_1D),
    ("pymeasure_teledyne_m_a_u_i", "teledyne", "TeledyneMAUI", InstrumentType.DETECTOR_1D),
    ("pymeasure_teledyne_oscilloscope", "teledyne", "TeledyneOscilloscope", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6370_c", "yokogawa", "AQ6370C", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6370_d", "yokogawa", "AQ6370D", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6370_e", "yokogawa", "AQ6370E", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6370_series", "yokogawa", "AQ6370Series", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6373", "yokogawa", "AQ6373", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6373_b", "yokogawa", "AQ6373B", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6375", "yokogawa", "AQ6375", InstrumentType.DETECTOR_1D),
    ("pymeasure_a_q6375_b", "yokogawa", "AQ6375B", InstrumentType.DETECTOR_1D),
    ("pymeasure_argos", "aculight", "Argos", InstrumentType.GENERIC),
    ("pymeasure_advantest_r3767_c_g", "advantest", "AdvantestR3767CG", InstrumentType.GENERIC),
    ("pymeasure_advantest_r6245", "advantest", "AdvantestR6245", InstrumentType.GENERIC),
    ("pymeasure_advantest_r6246", "advantest", "AdvantestR6246", InstrumentType.GENERIC),
    ("pymeasure_agilent4156", "agilent", "Agilent4156", InstrumentType.GENERIC),
    ("pymeasure_agilent8257_d", "agilent", "Agilent8257D", InstrumentType.GENERIC),
    ("pymeasure_l_d400_p", "aimtti", "LD400P", InstrumentType.GENERIC),
    ("pymeasure_p_l068_p", "aimtti", "PL068P", InstrumentType.GENERIC),
    ("pymeasure_p_l155_p", "aimtti", "PL155P", InstrumentType.GENERIC),
    ("pymeasure_p_l303_p", "aimtti", "PL303P", InstrumentType.GENERIC),
    ("pymeasure_p_l303_q_m_d_p", "aimtti", "PL303QMDP", InstrumentType.GENERIC),
    ("pymeasure_p_l303_q_m_t_p", "aimtti", "PL303QMTP", InstrumentType.GENERIC),
    ("pymeasure_p_l601_p", "aimtti", "PL601P", InstrumentType.GENERIC),
    ("pymeasure_d_c_x_s", "aja", "DCXS", InstrumentType.GENERIC),
    ("pymeasure_a_h2500_a", "andeenhagerling", "AH2500A", InstrumentType.GENERIC),
    ("pymeasure_b_k_precision9130_b", "bkprecision", "BKPrecision9130B", InstrumentType.GENERIC),
    ("pymeasure_eurotest_h_p_p120256", "eurotest", "EurotestHPP120256", InstrumentType.GENERIC),
    ("pymeasure_fluke7341", "fluke", "Fluke7341", InstrumentType.GENERIC),
    ("pymeasure_velox", "formfactor", "Velox", InstrumentType.GENERIC),
    ("pymeasure_f_w_bell5080", "fwbell", "FWBell5080", InstrumentType.GENERIC),
    ("pymeasure_n_d287", "heidenhain", "ND287", InstrumentType.GENERIC),
    ("pymeasure_h_p11713_a", "hp", "HP11713A", InstrumentType.GENERIC),
    ("pymeasure_h_p33120_a", "hp", "HP33120A", InstrumentType.GENERIC),
    ("pymeasure_h_p437_b", "hp", "HP437B", InstrumentType.GENERIC),
    ("pymeasure_h_p8657_b", "hp", "HP8657B", InstrumentType.GENERIC),
    ("pymeasure_h_p8753_e", "hp", "HP8753E", InstrumentType.GENERIC),
    ("pymeasure_h_p_legacy_instrument", "hp", "HPLegacyInstrument", InstrumentType.GENERIC),
    ("pymeasure_s_q_m160", "inficon", "SQM160", InstrumentType.GENERIC),
    ("pymeasure_keithley2306", "keithley", "Keithley2306", InstrumentType.GENERIC),
    ("pymeasure_keithley2510", "keithley", "Keithley2510", InstrumentType.GENERIC),
    ("pymeasure_keysight_n7776_c", "keysight", "KeysightN7776C", InstrumentType.GENERIC),
    ("pymeasure_m_k_s_instrument", "mksinst", "MKSInstrument", InstrumentType.GENERIC),
    ("pymeasure_fpu60", "novanta", "Fpu60", InstrumentType.GENERIC),
    ("pymeasure_c_n_t91", "pendulum", "CNT91", InstrumentType.GENERIC),
    ("pymeasure_p_m6669", "philips", "PM6669", InstrumentType.GENERIC),
    ("pymeasure_r_o_d4", "proterial", "ROD4", InstrumentType.GENERIC),
    ("pymeasure_racal1992", "racal", "Racal1992", InstrumentType.GENERIC),
    ("pymeasure_razorbill_r_p100", "razorbill", "razorbillRP100", InstrumentType.GENERIC),
    ("pymeasure_red_pitaya_scpi", "redpitaya", "RedPitayaScpi", InstrumentType.GENERIC),
    ("pymeasure_h_m_p4040", "rohdeschwarz", "HMP4040", InstrumentType.GENERIC),
    ("pymeasure_s_f_m", "rohdeschwarz", "SFM", InstrumentType.GENERIC),
    ("pymeasure_t_s_l500_series", "santec", "TSL500Series", InstrumentType.GENERIC),
    ("pymeasure_t_s_l550", "santec", "TSL550", InstrumentType.GENERIC),
    ("pymeasure_t_s_l570", "santec", "TSL570", InstrumentType.GENERIC),
    ("pymeasure_s_d_s1000_x_h_d", "siglenttechnologies", "SDS1000XHD", InstrumentType.GENERIC),
    ("pymeasure_s_d_s1072_c_m_l", "siglenttechnologies", "SDS1072CML", InstrumentType.GENERIC),
    ("pymeasure_c_x_n", "tcpowerconversion", "CXN", InstrumentType.GENERIC),
    ("pymeasure_t_d_k_gen40_38", "tdk", "TDK_Gen40_38", InstrumentType.GENERIC),
    ("pymeasure_t_d_k_gen80_65", "tdk", "TDK_Gen80_65", InstrumentType.GENERIC),
    ("pymeasure_a_t_s_base", "temptronic", "ATSBase", InstrumentType.GENERIC),
    ("pymeasure_thorlabs_m_b_x_series", "thorlabs", "ThorlabsMBXSeries", InstrumentType.GENERIC),
    ("pymeasure_thorlabs_pro8000", "thorlabs", "ThorlabsPro8000", InstrumentType.GENERIC),
    ("pymeasure_velleman_k8090", "velleman", "VellemanK8090", InstrumentType.GENERIC),
    ("pymeasure_yokogawa7651", "yokogawa", "Yokogawa7651", InstrumentType.GENERIC),
    ("pymeasure_yokogawa_g_s200", "yokogawa", "YokogawaGS200", InstrumentType.GENERIC),
    ("pymeasure_a_w_g401x_a_f_g", "activetechnologies", "AWG401x_AFG", InstrumentType.SOURCE),
    ("pymeasure_a_w_g401x_a_w_g", "activetechnologies", "AWG401x_AWG", InstrumentType.SOURCE),
    ("pymeasure_agilent33220_a", "agilent", "Agilent33220A", InstrumentType.SOURCE),
    ("pymeasure_agilent33500", "agilent", "Agilent33500", InstrumentType.SOURCE),
    ("pymeasure_agilent33521_a", "agilent", "Agilent33521A", InstrumentType.SOURCE),
    ("pymeasure_agilent_b1500", "agilent", "AgilentB1500", InstrumentType.SOURCE),
    ("pymeasure_agilent_n8975_a", "agilent", "AgilentN8975A", InstrumentType.SOURCE),
    ("pymeasure_a_m_i430", "ami", "AMI430", InstrumentType.SOURCE),
    ("pymeasure_a_p_s_i_n12_g", "anapico", "APSIN12G", InstrumentType.SOURCE),
    ("pymeasure_anritsu_m_g3692_c", "anritsu", "AnritsuMG3692C", InstrumentType.SOURCE),
    ("pymeasure_danfysik8500", "danfysik", "Danfysik8500", InstrumentType.SOURCE),
    ("pymeasure_s_m7045_d", "deltaelektronika", "SM7045D", InstrumentType.SOURCE),
    ("pymeasure_t_c038", "hcp", "TC038", InstrumentType.SOURCE),
    ("pymeasure_t_c038_d", "hcp", "TC038D", InstrumentType.SOURCE),
    ("pymeasure_h_p6632_a", "hp", "HP6632A", InstrumentType.SOURCE),
    ("pymeasure_h_p6633_a", "hp", "HP6633A", InstrumentType.SOURCE),
    ("pymeasure_h_p6634_a", "hp", "HP6634A", InstrumentType.SOURCE),
    ("pymeasure_h_p8116_a", "hp", "HP8116A", InstrumentType.SOURCE),
    ("pymeasure_l_d_p3811", "ilxlightwave", "LDP3811", InstrumentType.SOURCE),
    ("pymeasure_y_a_r", "ipgphotonics", "YAR", InstrumentType.SOURCE),
    ("pymeasure_keithley2200", "keithley", "Keithley2200", InstrumentType.SOURCE),
    ("pymeasure_keithley2260_b", "keithley", "Keithley2260B", InstrumentType.SOURCE),
    ("pymeasure_keithley2281_s", "keithley", "Keithley2281S", InstrumentType.SOURCE),
    ("pymeasure_keithley2400_legacy", "keithley", "Keithley2400Legacy", InstrumentType.SOURCE),
    ("pymeasure_keithley2450", "keithley", "Keithley2450", InstrumentType.SOURCE),
    ("pymeasure_keithley4200", "keithley", "Keithley4200", InstrumentType.SOURCE),
    ("pymeasure_kepco_b_o_p3612", "kepco", "KepcoBOP3612", InstrumentType.SOURCE),
    ("pymeasure_keysight33250_a", "keysight", "Keysight33250A", InstrumentType.SOURCE),
    ("pymeasure_keysight81160_a", "keysight", "Keysight81160A", InstrumentType.SOURCE),
    ("pymeasure_keysight_e36312_a", "keysight", "KeysightE36312A", InstrumentType.SOURCE),
    ("pymeasure_keysight_e3631_a", "keysight", "KeysightE3631A", InstrumentType.SOURCE),
    ("pymeasure_keysight_n5767_a", "keysight", "KeysightN5767A", InstrumentType.SOURCE),
    ("pymeasure_kusg245_250_a", "kuhneelectronic", "Kusg245_250A", InstrumentType.SOURCE),
    ("pymeasure_lake_shore211", "lakeshore", "LakeShore211", InstrumentType.SOURCE),
    ("pymeasure_lake_shore224", "lakeshore", "LakeShore224", InstrumentType.SOURCE),
    ("pymeasure_lake_shore331", "lakeshore", "LakeShore331", InstrumentType.SOURCE),
    ("pymeasure_lake_shore3xx", "lakeshore", "LakeShore3xx", InstrumentType.SOURCE),
    ("pymeasure_lake_shore421", "lakeshore", "LakeShore421", InstrumentType.SOURCE),
    ("pymeasure_lake_shore425", "lakeshore", "LakeShore425", InstrumentType.SOURCE),
    ("pymeasure_i_p_s120_10", "oxfordinstruments", "IPS120_10", InstrumentType.SOURCE),
    ("pymeasure_i_t_c503", "oxfordinstruments", "ITC503", InstrumentType.SOURCE),
    ("pymeasure_mercuryi_t_c", "oxfordinstruments", "MercuryiTC", InstrumentType.SOURCE),
    ("pymeasure_p_s120_10", "oxfordinstruments", "PS120_10", InstrumentType.SOURCE),
    ("pymeasure_d_g800", "rigol", "DG800", InstrumentType.SOURCE),
    ("pymeasure_s_p_d1168_x", "siglenttechnologies", "SPD1168X", InstrumentType.SOURCE),
    ("pymeasure_s_p_d1305_x", "siglenttechnologies", "SPD1305X", InstrumentType.SOURCE),
    ("pymeasure_spellman_x_r_v", "spellmanhv", "SpellmanXRV", InstrumentType.SOURCE),
    ("pymeasure_l_d_c500_series", "srs", "LDC500Series", InstrumentType.SOURCE),
    ("pymeasure_s_g380", "srs", "SG380", InstrumentType.SOURCE),
    ("pymeasure_a_f_g3152_c", "tektronix", "AFG3152C", InstrumentType.SOURCE),
    ("pymeasure_teledyne_t3_a_f_g", "teledyne", "TeledyneT3AFG", InstrumentType.SOURCE),
    ("pymeasure_a_t_s525", "temptronic", "ATS525", InstrumentType.SOURCE),
    ("pymeasure_a_t_s545", "temptronic", "ATS545", InstrumentType.SOURCE),
    ("pymeasure_e_c_o560", "temptronic", "ECO560", InstrumentType.SOURCE),
    ("pymeasure_texio_p_s_w360_l30", "texio", "TexioPSW360L30", InstrumentType.SOURCE),
    ("pymeasure_thermotron3800", "thermotron", "Thermotron3800", InstrumentType.SOURCE),
    ("pymeasure_i_beam_smart", "toptica", "IBeamSmart", InstrumentType.SOURCE),
]

INSTRUMENT_CATALOG.extend(
    InstrumentMetadata(
        adapter_key=key,
        manufacturer=mfg.capitalize(),
        model=cls,
        display_name=f"{mfg.capitalize()} {cls}",
        instrument_type=itype,
        backend=InstrumentBackend.PYMEASURE,
        tags=["pymeasure", "auto-generated"],
    )
    for key, mfg, cls, itype in _BULK_PYMEASURE
)


# pylablib adapters (24) — src/instruments/<Manufacturer>/<type>.py
INSTRUMENT_CATALOG.extend([
    InstrumentMetadata("ophir", "Ophir", "StarLite", "Ophir Power Meter", InstrumentType.DETECTOR_0D, InstrumentBackend.PYLABLIB, tags=['power-meter', 'optical']),
    InstrumentMetadata("thorlabs_pm160", "Thorlabs", "PM160", "Thorlabs PM160 Power Meter", InstrumentType.DETECTOR_0D, InstrumentBackend.PYLABLIB, tags=['power-meter', 'optical']),
    InstrumentMetadata("pfeiffer_tpg261", "Pfeiffer", "TPG261", "Pfeiffer TPG261 Vacuum Gauge", InstrumentType.DETECTOR_0D, InstrumentBackend.PYLABLIB, tags=['pressure', 'vacuum']),
    InstrumentMetadata("highfinesse_ws6", "HighFinesse", "WS6", "HighFinesse WS6 Wavemeter", InstrumentType.DETECTOR_0D, InstrumentBackend.PYLABLIB, tags=['wavemeter', 'optical']),
    InstrumentMetadata("lakeshore_218", "Lakeshore", "218", "Lakeshore 218 Temperature Monitor", InstrumentType.DETECTOR_0D, InstrumentBackend.PYLABLIB, tags=['temperature', '8-channel']),
    InstrumentMetadata("cryocon_14c", "CryoCon", "14C", "Cryo-Con 14C Temperature Monitor", InstrumentType.DETECTOR_0D, InstrumentBackend.PYLABLIB, tags=['temperature', 'cryogenic']),
    InstrumentMetadata("pi_e516", "PI", "E-516", "PI E-516 Piezo Stage Controller", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=['stage', 'piezo']),
    InstrumentMetadata("newport_picomotor_8742", "Newport", "8742", "Newport/New Focus 8742 Picomotor Controller", InstrumentType.ACTUATOR_ND, InstrumentBackend.PYLABLIB, tags=['motor', 'picomotor', 'multi-axis']),
    InstrumentMetadata("thorlabs_kinesis_motor", "Thorlabs", "Kinesis", "Thorlabs Kinesis Motor Controller", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=['motor', 'kinesis']),
    InstrumentMetadata("thorlabs_mff", "Thorlabs", "MFF", "Thorlabs MFF Motorized Flip Mount", InstrumentType.ACTUATOR_0D, InstrumentBackend.PYLABLIB, tags=['flip-mount', 'binary']),
    InstrumentMetadata("thorlabs_fw", "Thorlabs", "FW", "Thorlabs FW Filter Wheel", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=['filter-wheel', 'rotational']),
    InstrumentMetadata("attocube_anc300", "Attocube", "ANC300", "Attocube ANC300 Piezo Controller", InstrumentType.ACTUATOR_ND, InstrumentBackend.PYLABLIB, tags=['stage', 'piezo', 'multi-axis']),
    InstrumentMetadata("attocube_anc350", "Attocube", "ANC350", "Attocube ANC350 Piezo Controller", InstrumentType.ACTUATOR_ND, InstrumentBackend.PYLABLIB, tags=['stage', 'piezo', 'multi-axis']),
    InstrumentMetadata("toptica_ibeam_smart", "Toptica", "iBeam Smart", "Toptica iBeam Smart Laser", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['laser', 'diode']),
    InstrumentMetadata("m2_solstis", "M Squared", "SolsTiS", "M Squared SolsTiS Tunable Laser", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['laser', 'tunable', 'ti:sapphire']),

    # Pulsed sequencers — src/instruments/{Swabian,SpinCore}/. Both need
    # the manufacturer's own package, and both `describe()` without it, so
    # they are listed and searchable on a machine with no hardware.
    InstrumentMetadata("swabian_pulse_streamer", "Swabian", "Pulse Streamer 8/2", "Swabian Pulse Streamer", InstrumentType.GENERIC, InstrumentBackend.VENDOR, connection_types=['ethernet'], tags=['pulser', 'sequencer', 'ttl', 'digital', 'odmr', 'pulsed']),
    InstrumentMetadata("spincore_pulse_blaster", "SpinCore", "PulseBlaster ESR-PRO", "SpinCore PulseBlaster", InstrumentType.GENERIC, InstrumentBackend.VENDOR, connection_types=['pci'], tags=['pulser', 'sequencer', 'ttl', 'digital', 'odmr', 'pulsed']),
    InstrumentMetadata("laser_quantum_finesse", "Laser Quantum", "Finesse", "Laser Quantum Finesse Laser", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['laser', 'cw']),
    InstrumentMetadata("basler", "Basler", "ace", "Basler ace Camera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera']),
    InstrumentMetadata("photometrics_pvcam", "Photometrics", "PVCAM", "Photometrics PVCAM Camera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera', 'scientific']),
    InstrumentMetadata("princeton_picam", "Princeton Instruments", "PICam", "Princeton Instruments PICam Camera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera', 'scientific']),
    InstrumentMetadata("thorlabs_tlcamera", "Thorlabs", "TLCamera", "Thorlabs Scientific Camera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera']),
    InstrumentMetadata("uc480", "Thorlabs", "uc480", "Thorlabs uc480/UI Camera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera']),
    InstrumentMetadata("andor_sdk2", "Andor", "SDK2", "Andor Camera (SDK2)", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera', 'ccd', 'emccd']),
    InstrumentMetadata("andor_sdk3", "Andor", "SDK3", "Andor Camera (SDK3)", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera', 'scmos']),
    InstrumentMetadata("andor_shamrock", "Andor", "Shamrock", "Andor Shamrock Spectrograph", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=['spectrograph', 'monochromator', 'grating']),
    InstrumentMetadata("pco", "PCO", "pco.edge", "PCO Camera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera', 'scmos']),
    InstrumentMetadata("hamamatsu_dcam", "Hamamatsu", "DCAM", "Hamamatsu Camera (DCAM)", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=['camera']),
    InstrumentMetadata("ni_daq", "National Instruments", "NI-DAQmx", "NI-DAQmx Analog I/O", InstrumentType.GENERIC, InstrumentBackend.PYLABLIB, tags=['daq', 'analog-io', 'ni-daqmx']),
    # Hardware-timed scanning (position output + detector input clocked as
    # one) — see core/workflow/capabilities.py's HardwareTimedScanCapability.
    # Untested against physical hardware (built directly against pylablib's
    # verified API; no NI card in this dev environment — see NIDAQScannerAdapter's docstring).
    InstrumentMetadata("ni_daq_scanner", "National Instruments", "NI-DAQmx Scanner", "NI-DAQmx Hardware-Timed Scanner", InstrumentType.GENERIC, InstrumentBackend.PYLABLIB, tags=['daq', 'ni-daqmx', 'scanner', 'hardware-scan']),
    InstrumentMetadata("pylablib_agilent33220a", "Agilent", "33220A", "Agilent 33220A Function Generator", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['awg', 'function-generator']),
    InstrumentMetadata("pylablib_agilent33500", "Agilent", "33500", "Agilent 33500 Function Generator", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['awg', 'function-generator']),
    InstrumentMetadata("pylablib_rigol_dg1000", "Rigol", "DG1000", "Rigol DG1000 Function Generator", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['awg', 'function-generator']),
    InstrumentMetadata("pylablib_tektronix_afg1000", "Tektronix", "AFG1000", "Tektronix AFG1000 Function Generator", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['awg', 'function-generator']),
    InstrumentMetadata("pylablib_instek_afg2000", "Instek", "AFG2000", "Instek AFG2000 Function Generator", InstrumentType.SOURCE, InstrumentBackend.PYLABLIB, tags=['awg', 'function-generator']),
])


# MockBasic (7) — src/instruments/MockBasic/simple.py, one per InstrumentType,
# used as the dashboard's starter/demo seed instead of a hardcoded fake list.
INSTRUMENT_CATALOG.extend([
    InstrumentMetadata("mock_basic_detector_0d", "MockBasic", "Generic", "Basic 0D Detector", InstrumentType.DETECTOR_0D, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_detector_1d", "MockBasic", "Generic", "Basic 1D Detector", InstrumentType.DETECTOR_1D, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_detector_2d", "MockBasic", "Generic", "Basic 2D Detector", InstrumentType.DETECTOR_2D, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_detector_nd", "MockBasic", "Generic", "Basic ND Detector", InstrumentType.DETECTOR_ND, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_actuator_0d", "MockBasic", "Generic", "Basic 0D Actuator", InstrumentType.ACTUATOR_0D, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_actuator_1d", "MockBasic", "Generic", "Basic 1D Actuator", InstrumentType.ACTUATOR_1D, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_actuator_nd", "MockBasic", "Generic", "Basic ND Actuator", InstrumentType.ACTUATOR_ND, InstrumentBackend.MOCK, tags=["mock-basic"]),
    InstrumentMetadata("mock_basic_source", "MockBasic", "Generic", "Basic Source", InstrumentType.SOURCE, InstrumentBackend.MOCK, tags=["mock-basic"]),
])


# Bulk-generated pylablib entries (20) — generic camera/stage wrappers,
# verified against installed pylablib 1.4.3's real device classes.
INSTRUMENT_CATALOG.extend([
    InstrumentMetadata("pylablib_bonito_i_m_a_q_camera", "AlliedVision", "BonitoIMAQCamera", "AlliedVision BonitoIMAQCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_bit_flow_camera", "BitFlow", "BitFlowCamera", "BitFlow BitFlowCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_i_m_a_q_camera", "IMAQ", "IMAQCamera", "IMAQ IMAQCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_ethernet_i_m_a_qdx_camera", "IMAQdx", "EthernetIMAQdxCamera", "IMAQdx EthernetIMAQdxCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_i_m_a_qdx_camera", "IMAQdx", "IMAQdxCamera", "IMAQdx IMAQdxCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_mightex_s_series_camera", "Mightex", "MightexSSeriesCamera", "Mightex MightexSSeriesCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_i_photon_focus_camera", "PhotonFocus", "IPhotonFocusCamera", "PhotonFocus IPhotonFocusCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_photon_focus_bit_flow_camera", "PhotonFocus", "PhotonFocusBitFlowCamera", "PhotonFocus PhotonFocusBitFlowCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_photon_focus_i_m_a_q_camera", "PhotonFocus", "PhotonFocusIMAQCamera", "PhotonFocus PhotonFocusIMAQCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_photon_focus_si_so_camera", "PhotonFocus", "PhotonFocusSiSoCamera", "PhotonFocus PhotonFocusSiSoCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_silicon_software_camera", "SiliconSoftware", "SiliconSoftwareCamera", "SiliconSoftware SiliconSoftwareCamera", InstrumentType.DETECTOR_2D, InstrumentBackend.PYLABLIB, tags=["pylablib", "camera"]),
    InstrumentMetadata("pylablib_performax2_e_x_stage", "Arcus", "Performax2EXStage", "Arcus Performax2EXStage", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_performax4_e_x_stage", "Arcus", "Performax4EXStage", "Arcus Performax4EXStage", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_performax_d_m_x_j_s_a_stage", "Arcus", "PerformaxDMXJSAStage", "Arcus PerformaxDMXJSAStage", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_p_i_e515", "PhysikInstrumente", "PIE515", "PhysikInstrumente PIE515", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_m_c_s2", "SmarAct", "MCS2", "SmarAct MCS2", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_standa8_s_m_c", "Standa", "Standa8SMC", "Standa Standa8SMC", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_kinesis_piezo_motor", "Thorlabs", "KinesisPiezoMotor", "Thorlabs KinesisPiezoMotor", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("thorlabs_elliptec", "Thorlabs", "Elliptec", "Thorlabs Elliptec Rotation/Linear Mount", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["motor", "elliptec", "rotation-mount"]),
    InstrumentMetadata("thorlabs_mdt69xa", "Thorlabs", "MDT69xA", "Thorlabs MDT69xA Piezo Controller", InstrumentType.ACTUATOR_ND, InstrumentBackend.PYLABLIB, tags=["piezo", "controller", "3-axis"]),
    InstrumentMetadata("pylablib_t_m_c_m1110", "Trinamic", "TMCM1110", "Trinamic TMCM1110", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
    InstrumentMetadata("pylablib_t_m_c_mx110", "Trinamic", "TMCMx110", "Trinamic TMCMx110", InstrumentType.ACTUATOR_1D, InstrumentBackend.PYLABLIB, tags=["pylablib", "stage"]),
])


# Backfill connection_types for every entry that doesn't already declare
# its own (the original 6 hand-written pymeasure entries set specific,
# confirmed values and are left alone) — a mechanical, backend-derived
# default so every catalog entry names *something* connectable
# (see instruments/connections.py) instead of the empty list every
# mock/pylablib/bulk-pymeasure entry defaulted to before. Refine
# per-adapter as real connection requirements get confirmed; this is a
# reasonable starting default, not a verified-per-device fact.
_DEFAULT_CONNECTION_TYPES_BY_BACKEND: dict[InstrumentBackend, list[str]] = {
    InstrumentBackend.MOCK: ["none"],
    InstrumentBackend.TEST_FIXTURE: ["none"],
    InstrumentBackend.PYMEASURE: ["visa"],
    InstrumentBackend.PYLABLIB: ["usb_serial_number", "serial"],
}
for _entry in INSTRUMENT_CATALOG:
    if not _entry.connection_types:
        _entry.connection_types = list(_DEFAULT_CONNECTION_TYPES_BY_BACKEND.get(_entry.backend, []))
del _entry
