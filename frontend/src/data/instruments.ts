/**
 * Comprehensive Instrument Catalog for LabPilot
 * Organized by manufacturer, category, and dimensionality
 */

export interface Parameter {
  name: string;
  type: 'number' | 'text' | 'select' | 'boolean';
  value: any;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  description?: string;
}

export interface Instrument {
  id: string;
  name: string;
  manufacturer: string;
  modelNumber: string;
  adapterType: string;
  category: string;
  connected: boolean;
  kind: 'detector' | 'source' | 'motor' | 'actuator';
  dimensionality: '0D' | '1D' | '2D' | '3D';
  tags: string[];
  description: string;
  parameters: Record<string, Parameter>;
}

// ============================================================================
// DETECTORS - 0D (Point measurements)
// ============================================================================

export const DETECTOR_0D: Instrument[] = [
  {
    id: 'thorlabs-pm100-001',
    name: 'Power Meter 1',
    manufacturer: 'Thorlabs',
    modelNumber: 'PM100',
    adapterType: 'ThorlabsPM100',
    category: 'Power Meter',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Power Meter', 'USB', 'Detector'],
    description: 'Optical power meter for wavelength 400-2500 nm',
    parameters: {
      power: {
        name: 'Optical Power',
        type: 'number',
        value: 12.5,
        unit: 'mW',
        min: 0,
        max: 500,
      },
      wavelength: {
        name: 'Wavelength',
        type: 'number',
        value: 633,
        unit: 'nm',
        min: 400,
        max: 2500,
      },
      range: {
        name: 'Autorange',
        type: 'boolean',
        value: true,
      },
    },
  },
  {
    id: 'newport-2835-001',
    name: 'Power Meter 2',
    manufacturer: 'Newport',
    modelNumber: '2835-OR',
    adapterType: 'NewportPowerMeter',
    category: 'Power Meter',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Power Meter', 'USB', 'Detector'],
    description: 'Optical power meter with fiber input',
    parameters: {
      power: {
        name: 'Power',
        type: 'number',
        value: 8.3,
        unit: 'mW',
        min: 0,
        max: 50,
      },
      wavelength: {
        name: 'Wavelength',
        type: 'number',
        value: 1550,
        unit: 'nm',
        min: 800,
        max: 1700,
      },
    },
  },
  {
    id: 'srs-sr844-001',
    name: 'Lock-in Amplifier',
    manufacturer: 'Stanford Research Systems',
    modelNumber: 'SR844',
    adapterType: 'SRSSRLockIn',
    category: 'Lock-in Amplifier',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Lock-in', 'Detector', 'Electronics'],
    description: 'RF lock-in amplifier for 0 Hz to 2 MHz',
    parameters: {
      frequency: {
        name: 'Reference Frequency',
        type: 'number',
        value: 100000,
        unit: 'Hz',
        min: 0,
        max: 2000000,
      },
      sensitivity: {
        name: 'Sensitivity',
        type: 'select',
        value: '100 nV',
        options: ['100 nV', '300 nV', '1 µV', '3 µV', '10 µV', '30 µV', '100 µV', '300 µV', '1 mV'],
      },
      phase: {
        name: 'Phase',
        type: 'number',
        value: 0,
        unit: 'degrees',
        min: -180,
        max: 180,
      },
      xOutput: {
        name: 'X Output',
        type: 'number',
        value: 125.3,
        unit: 'mV',
      },
      yOutput: {
        name: 'Y Output',
        type: 'number',
        value: 23.1,
        unit: 'mV',
      },
    },
  },
  {
    id: 'keithley-2400-001',
    name: 'Source Meter',
    manufacturer: 'Keithley',
    modelNumber: '2400',
    adapterType: 'Keithley2400',
    category: 'Source Meter',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Source Meter', 'GPIB', 'Electronics'],
    description: 'Precision voltage/current source and meter',
    parameters: {
      voltage: {
        name: 'Voltage',
        type: 'number',
        value: 5.0,
        unit: 'V',
        min: -200,
        max: 200,
      },
      current: {
        name: 'Current',
        type: 'number',
        value: 0.5,
        unit: 'mA',
        min: -1050,
        max: 1050,
      },
      mode: {
        name: 'Mode',
        type: 'select',
        value: 'Voltage',
        options: ['Voltage', 'Current'],
      },
    },
  },
  {
    id: 'ni-daq-001',
    name: 'Data Acquisition Module',
    manufacturer: 'National Instruments',
    modelNumber: 'USB-6008',
    adapterType: 'NIDAQ',
    category: 'Data Acquisition',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'DAQ', 'USB', 'Detector', 'Analog'],
    description: '12-bit USB DAQ with 8 analog inputs',
    parameters: {
      voltage: {
        name: 'Analog Input 0',
        type: 'number',
        value: 2.45,
        unit: 'V',
        min: 0,
        max: 10,
      },
      channel: {
        name: 'Channel',
        type: 'select',
        value: '0',
        options: ['0', '1', '2', '3', '4', '5', '6', '7'],
      },
      samplingRate: {
        name: 'Sampling Rate',
        type: 'number',
        value: 1000,
        unit: 'Hz',
        min: 1,
        max: 48000,
      },
    },
  },
  {
    id: 'keysight-34461a-001',
    name: 'Multimeter',
    manufacturer: 'Keysight',
    modelNumber: '34461A',
    adapterType: 'KeysightMultimeter',
    category: 'Multimeter',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Multimeter', 'GPIB', 'Electronics'],
    description: '6.5-digit True RMS Multimeter',
    parameters: {
      voltage: {
        name: 'DC Voltage',
        type: 'number',
        value: 12.34,
        unit: 'V',
        min: -300,
        max: 300,
      },
      current: {
        name: 'AC Current',
        type: 'number',
        value: 1.5,
        unit: 'A',
        min: -3,
        max: 3,
      },
    },
  },
  {
    id: 'thorlabs-fls1000-001',
    name: 'Photodiode Detector',
    manufacturer: 'Thorlabs',
    modelNumber: 'FLS1000',
    adapterType: 'ThorlabsPhotodiode',
    category: 'Photodiode',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Photodiode', 'Detector'],
    description: 'Ultra-sensitive photodiode for lock-in detection',
    parameters: {
      voltage: {
        name: 'Output Voltage',
        type: 'number',
        value: 45.2,
        unit: 'mV',
        min: 0,
        max: 100,
      },
      wavelength: {
        name: 'Peak Wavelength',
        type: 'number',
        value: 850,
        unit: 'nm',
        min: 200,
        max: 1700,
      },
    },
  },
  {
    id: 'heidenhain-ls487-001',
    name: 'Position Encoder',
    manufacturer: 'Heidenhain',
    modelNumber: 'LS487',
    adapterType: 'HeidenhainEncoder',
    category: 'Position Encoder',
    connected: true,
    kind: 'detector',
    dimensionality: '0D',
    tags: ['Test', 'Encoder', 'Position', 'Detector'],
    description: 'Linear position encoder with 0.1 mm resolution',
    parameters: {
      position: {
        name: 'Position',
        type: 'number',
        value: 45.23,
        unit: 'mm',
        min: 0,
        max: 500,
      },
      resolution: {
        name: 'Resolution',
        type: 'number',
        value: 0.1,
        unit: 'mm',
      },
    },
  },
];

// ============================================================================
// DETECTORS - 1D (Spectroscopic data)
// ============================================================================

export const DETECTOR_1D: Instrument[] = [
  {
    id: 'ocean-optics-usb2000-001',
    name: 'USB Spectrometer 1',
    manufacturer: 'Ocean Optics',
    modelNumber: 'USB2000',
    adapterType: 'OceanOpticsUSB2000',
    category: 'Spectrometer',
    connected: true,
    kind: 'detector',
    dimensionality: '1D',
    tags: ['Test', 'Spectrometer', 'USB', 'Detector'],
    description: 'Fiber optic spectrometer 200-850 nm',
    parameters: {
      wavelength: {
        name: 'Center Wavelength',
        type: 'number',
        value: 550,
        unit: 'nm',
        min: 200,
        max: 850,
      },
      integrationTime: {
        name: 'Integration Time',
        type: 'number',
        value: 10,
        unit: 'ms',
        min: 1,
        max: 65,
      },
      averaging: {
        name: 'Averaging',
        type: 'number',
        value: 5,
        unit: 'scans',
        min: 1,
        max: 100,
      },
    },
  },
  {
    id: 'andor-shamrock-001',
    name: 'Spectrograph',
    manufacturer: 'Andor',
    modelNumber: 'Shamrock 303',
    adapterType: 'AndorShamrock',
    category: 'Spectrograph',
    connected: true,
    kind: 'detector',
    dimensionality: '1D',
    tags: ['Test', 'Spectrograph', 'Detector', 'High Resolution'],
    description: 'High resolution spectrograph with motorized turret',
    parameters: {
      wavelength: {
        name: 'Wavelength',
        type: 'number',
        value: 632.8,
        unit: 'nm',
        min: 300,
        max: 1000,
      },
      gratingTurret: {
        name: 'Grating',
        type: 'select',
        value: '1200 l/mm',
        options: ['300 l/mm', '600 l/mm', '1200 l/mm'],
      },
      slitWidth: {
        name: 'Slit Width',
        type: 'number',
        value: 50,
        unit: 'µm',
        min: 10,
        max: 1000,
      },
    },
  },
  {
    id: 'thorlabs-ccs100-001',
    name: 'Compact Spectrometer',
    manufacturer: 'Thorlabs',
    modelNumber: 'CCS100',
    adapterType: 'ThorlabsCCS100',
    category: 'Spectrometer',
    connected: true,
    kind: 'detector',
    dimensionality: '1D',
    tags: ['Test', 'Spectrometer', 'USB', 'Compact'],
    description: 'Compact spectrometer 400-1000 nm, 0.7 nm resolution',
    parameters: {
      wavelength: {
        name: 'Peak Wavelength',
        type: 'number',
        value: 633,
        unit: 'nm',
        min: 400,
        max: 1000,
      },
      integrationTime: {
        name: 'Integration Time',
        type: 'number',
        value: 20,
        unit: 'ms',
        min: 1,
        max: 500,
      },
    },
  },
  {
    id: 'keysight-dso9014a-001',
    name: 'Digital Oscilloscope',
    manufacturer: 'Keysight',
    modelNumber: 'DSO9014A',
    adapterType: 'KeysightOscilloscope',
    category: 'Oscilloscope',
    connected: true,
    kind: 'detector',
    dimensionality: '1D',
    tags: ['Test', 'Oscilloscope', 'GPIB', 'Electronics'],
    description: '100 MHz Digital Oscilloscope',
    parameters: {
      frequency: {
        name: 'Frequency',
        type: 'number',
        value: 50,
        unit: 'MHz',
        min: 0,
        max: 100,
      },
      voltage: {
        name: 'Voltage',
        type: 'number',
        value: 2.5,
        unit: 'V',
      },
      timebase: {
        name: 'Timebase',
        type: 'number',
        value: 10,
        unit: 'ns/div',
        min: 1,
        max: 1000,
      },
    },
  },
];

// ============================================================================
// DETECTORS - 2D (Imaging data)
// ============================================================================

export const DETECTOR_2D: Instrument[] = [
  {
    id: 'andor-ixon-001',
    name: 'EMCCD Camera',
    manufacturer: 'Andor',
    modelNumber: 'iXon 897',
    adapterType: 'AndoriXon',
    category: 'Camera',
    connected: true,
    kind: 'detector',
    dimensionality: '2D',
    tags: ['Test', 'Camera', 'EMCCD', 'Detector', 'Imaging'],
    description: '512×512 EMCCD with ultra-low noise',
    parameters: {
      exposure: {
        name: 'Exposure Time',
        type: 'number',
        value: 10,
        unit: 'ms',
        min: 0.1,
        max: 1000,
      },
      gain: {
        name: 'EM Gain',
        type: 'number',
        value: 10,
        unit: '',
        min: 0,
        max: 255,
      },
      temperature: {
        name: 'Temperature',
        type: 'number',
        value: -80,
        unit: '°C',
        min: -80,
        max: 25,
      },
      binning: {
        name: 'Binning',
        type: 'select',
        value: '1x1',
        options: ['1x1', '2x2', '4x4'],
      },
    },
  },
  {
    id: 'flir-a50-001',
    name: 'Thermal Camera',
    manufacturer: 'FLIR',
    modelNumber: 'A50',
    adapterType: 'FLIRA50',
    category: 'Thermal Camera',
    connected: true,
    kind: 'detector',
    dimensionality: '2D',
    tags: ['Test', 'Thermal', 'Camera', 'Detector', 'IR'],
    description: '320×256 uncooled microbolometer thermal camera',
    parameters: {
      temperature: {
        name: 'Temperature',
        type: 'number',
        value: 23.5,
        unit: '°C',
        min: -40,
        max: 80,
      },
      emissivity: {
        name: 'Emissivity',
        type: 'number',
        value: 0.95,
        unit: '',
        min: 0,
        max: 1,
        step: 0.01,
      },
      framerate: {
        name: 'Frame Rate',
        type: 'number',
        value: 30,
        unit: 'Hz',
        min: 1,
        max: 30,
      },
    },
  },
  {
    id: 'thorlabs-dcc3260c-001',
    name: 'RGB Camera',
    manufacturer: 'Thorlabs',
    modelNumber: 'DCC3260C',
    adapterType: 'ThorlabsRGBCamera',
    category: 'Camera',
    connected: true,
    kind: 'detector',
    dimensionality: '2D',
    tags: ['Test', 'Camera', 'RGB', 'Detector', 'USB'],
    description: '2048×2048 RGB CMOS camera USB3.0',
    parameters: {
      exposure: {
        name: 'Exposure Time',
        type: 'number',
        value: 5,
        unit: 'ms',
        min: 0.01,
        max: 100,
      },
      gain: {
        name: 'Gain',
        type: 'number',
        value: 100,
        unit: '',
        min: 0,
        max: 1023,
      },
      framerate: {
        name: 'Frame Rate',
        type: 'number',
        value: 30,
        unit: 'fps',
      },
    },
  },
  {
    id: 'basler-ace2-001',
    name: 'Industrial Camera',
    manufacturer: 'Basler',
    modelNumber: 'ace2 Pro',
    adapterType: 'BaslerAce2',
    category: 'Camera',
    connected: true,
    kind: 'detector',
    dimensionality: '2D',
    tags: ['Test', 'Camera', 'Industrial', 'Detector', 'GigE'],
    description: 'High speed industrial camera GigE PoE',
    parameters: {
      exposure: {
        name: 'Exposure Time',
        type: 'number',
        value: 2,
        unit: 'ms',
        min: 0.01,
        max: 500,
      },
      framerate: {
        name: 'Frame Rate',
        type: 'number',
        value: 60,
        unit: 'fps',
        min: 1,
        max: 286,
      },
    },
  },
];

// ============================================================================
// ACTUATORS - 0D (Single setpoint control)
// ============================================================================

export const ACTUATOR_0D: Instrument[] = [
  {
    id: 'thorlabs-kdc101-001',
    name: 'DC Servo Motor 1',
    manufacturer: 'Thorlabs',
    modelNumber: 'KDC101',
    adapterType: 'ThorlabsKDC101',
    category: 'Servo Motor',
    connected: true,
    kind: 'motor',
    dimensionality: '0D',
    tags: ['Test', 'Motor', 'Actuator', 'USB'],
    description: 'Compact USB DC servo motor controller',
    parameters: {
      velocity: {
        name: 'Velocity',
        type: 'number',
        value: 50,
        unit: '%',
        min: 0,
        max: 100,
      },
      acceleration: {
        name: 'Acceleration',
        type: 'number',
        value: 50,
        unit: '%',
        min: 0,
        max: 100,
      },
    },
  },
  {
    id: 'keysight-n6705b-001',
    name: 'Modular Power Supply',
    manufacturer: 'Keysight',
    modelNumber: 'N6705B',
    adapterType: 'KeysightPowerSupply',
    category: 'Power Supply',
    connected: true,
    kind: 'source',
    dimensionality: '0D',
    tags: ['Test', 'Power Supply', 'Source', 'GPIB'],
    description: 'Modular DC power supply 4 channels',
    parameters: {
      voltage: {
        name: 'Voltage Setpoint',
        type: 'number',
        value: 5.0,
        unit: 'V',
        min: 0,
        max: 20,
      },
      current: {
        name: 'Current Limit',
        type: 'number',
        value: 1.0,
        unit: 'A',
        min: 0,
        max: 10,
      },
    },
  },
  {
    id: 'ophir-proch-001',
    name: 'Optical Chopper',
    manufacturer: 'Ophir',
    modelNumber: 'MC2000-EU',
    adapterType: 'OphirChopper',
    category: 'Chopper',
    connected: true,
    kind: 'actuator',
    dimensionality: '0D',
    tags: ['Test', 'Chopper', 'Actuator'],
    description: 'Optical chopper with frequency control',
    parameters: {
      frequency: {
        name: 'Frequency',
        type: 'number',
        value: 500,
        unit: 'Hz',
        min: 50,
        max: 5000,
      },
      duty: {
        name: 'Duty Cycle',
        type: 'number',
        value: 50,
        unit: '%',
        min: 10,
        max: 90,
      },
    },
  },
  {
    id: 'harvard-peri-001',
    name: 'Peristaltic Pump',
    manufacturer: 'Harvard Apparatus',
    modelNumber: 'Peri-Star Pro',
    adapterType: 'HarvardPeristaltic',
    category: 'Fluidic Pump',
    connected: true,
    kind: 'actuator',
    dimensionality: '0D',
    tags: ['Test', 'Pump', 'Actuator', 'Fluidics'],
    description: 'Peristaltic pump for precise fluid delivery',
    parameters: {
      flowRate: {
        name: 'Flow Rate',
        type: 'number',
        value: 5.0,
        unit: 'ml/min',
        min: 0,
        max: 100,
      },
      tubeID: {
        name: 'Tube ID',
        type: 'number',
        value: 1.6,
        unit: 'mm',
      },
    },
  },
];

// ============================================================================
// ACTUATORS - 1D (Single-axis motion)
// ============================================================================

export const ACTUATOR_1D: Instrument[] = [
  {
    id: 'newport-esp301-001',
    name: 'Motion Controller 1',
    manufacturer: 'Newport',
    modelNumber: 'ESP301',
    adapterType: 'NewportESP301',
    category: 'Motion Controller',
    connected: true,
    kind: 'motor',
    dimensionality: '1D',
    tags: ['Test', 'Motion', 'Actuator', 'Serial'],
    description: '3-axis motion controller for Newport stages',
    parameters: {
      position: {
        name: 'Position',
        type: 'number',
        value: 25.5,
        unit: 'mm',
        min: 0,
        max: 100,
      },
      velocity: {
        name: 'Velocity',
        type: 'number',
        value: 5.0,
        unit: 'mm/s',
        min: 0.1,
        max: 20,
      },
    },
  },
  {
    id: 'smaract-mcs2-001',
    name: 'Piezo Controller 1',
    manufacturer: 'SmarAct',
    modelNumber: 'MCS2',
    adapterType: 'SmarActMCS2',
    category: 'Piezo Controller',
    connected: true,
    kind: 'motor',
    dimensionality: '1D',
    tags: ['Test', 'Piezo', 'Actuator', 'USB'],
    description: 'Multi-channel piezo motion controller',
    parameters: {
      position: {
        name: 'Position',
        type: 'number',
        value: 15.3,
        unit: 'µm',
        min: -50,
        max: 50,
      },
      speed: {
        name: 'Speed',
        type: 'number',
        value: 1.0,
        unit: 'µm/s',
        min: 0.1,
        max: 10,
      },
    },
  },
  {
    id: 'thorlabs-z825b-001',
    name: 'Motorized Translation Stage',
    manufacturer: 'Thorlabs',
    modelNumber: 'Z825B',
    adapterType: 'ThorlabsZ825',
    category: 'Translation Stage',
    connected: true,
    kind: 'motor',
    dimensionality: '1D',
    tags: ['Test', 'Stage', 'Actuator', 'Motor', 'USB'],
    description: 'Motorized Z translation stage with 6 mm travel',
    parameters: {
      position: {
        name: 'Position',
        type: 'number',
        value: 3.0,
        unit: 'mm',
        min: 0,
        max: 6,
      },
      velocity: {
        name: 'Velocity',
        type: 'number',
        value: 1.5,
        unit: 'mm/s',
      },
    },
  },
  {
    id: 'zaber-t-ls13m-001',
    name: 'Linear Motion Stage',
    manufacturer: 'Zaber',
    modelNumber: 'T-LS13M',
    adapterType: 'ZaberLinearStage',
    category: 'Linear Stage',
    connected: true,
    kind: 'motor',
    dimensionality: '1D',
    tags: ['Test', 'Stage', 'Actuator', 'Motor', 'Serial'],
    description: 'Motorized linear stage 130 mm travel',
    parameters: {
      position: {
        name: 'Position',
        type: 'number',
        value: 65.0,
        unit: 'mm',
        min: 0,
        max: 130,
      },
      microsteps: {
        name: 'Microsteps',
        type: 'select',
        value: '16',
        options: ['8', '16', '32', '64'],
      },
    },
  },
];

// ============================================================================
// ACTUATORS - 2D (XY motion)
// ============================================================================

export const ACTUATOR_2D: Instrument[] = [
  {
    id: 'newport-xps-c8-001',
    name: 'XY Motion Stage',
    manufacturer: 'Newport',
    modelNumber: 'XPS-C8',
    adapterType: 'NewportXPS',
    category: 'XY Stage',
    connected: true,
    kind: 'motor',
    dimensionality: '2D',
    tags: ['Test', 'XY Stage', 'Actuator', 'Motion'],
    description: 'Compact XY motion stage with integrated controller',
    parameters: {
      positionX: {
        name: 'X Position',
        type: 'number',
        value: 12.5,
        unit: 'mm',
        min: 0,
        max: 25,
      },
      positionY: {
        name: 'Y Position',
        type: 'number',
        value: 8.3,
        unit: 'mm',
        min: 0,
        max: 25,
      },
      velocity: {
        name: 'Velocity',
        type: 'number',
        value: 5.0,
        unit: 'mm/s',
      },
    },
  },
  {
    id: 'smaract-mcs6-001',
    name: 'XY Piezo Stage',
    manufacturer: 'SmarAct',
    modelNumber: 'MCS6',
    adapterType: 'SmarActMCS6',
    category: 'XY Piezo Stage',
    connected: true,
    kind: 'motor',
    dimensionality: '2D',
    tags: ['Test', 'Piezo', 'XY Stage', 'Actuator', 'USB'],
    description: 'Sub-micron resolution XY piezo stage',
    parameters: {
      positionX: {
        name: 'X Position',
        type: 'number',
        value: 24.7,
        unit: 'µm',
        min: -50,
        max: 50,
      },
      positionY: {
        name: 'Y Position',
        type: 'number',
        value: 18.2,
        unit: 'µm',
        min: -50,
        max: 50,
      },
    },
  },
];

// ============================================================================
// ACTUATORS - 3D (XYZ motion)
// ============================================================================

export const ACTUATOR_3D: Instrument[] = [
  {
    id: 'newport-xyz-mod-001',
    name: 'XYZ Modular Stage',
    manufacturer: 'Newport',
    modelNumber: 'MFN25CC-XYZ',
    adapterType: 'NewportXYZ',
    category: 'XYZ Stage',
    connected: true,
    kind: 'motor',
    dimensionality: '3D',
    tags: ['Test', 'XYZ Stage', 'Actuator', 'Motion', 'Modular'],
    description: 'Modular XYZ motion stage with 25 mm travel',
    parameters: {
      positionX: {
        name: 'X Position',
        type: 'number',
        value: 12.5,
        unit: 'mm',
        min: 0,
        max: 25,
      },
      positionY: {
        name: 'Y Position',
        type: 'number',
        value: 10.0,
        unit: 'mm',
        min: 0,
        max: 25,
      },
      positionZ: {
        name: 'Z Position',
        type: 'number',
        value: 8.5,
        unit: 'mm',
        min: 0,
        max: 25,
      },
      velocity: {
        name: 'Velocity',
        type: 'number',
        value: 5.0,
        unit: 'mm/s',
      },
    },
  },
  {
    id: 'attocube-xyz-001',
    name: 'XYZ Piezo Stage',
    manufacturer: 'attocube systems',
    modelNumber: 'ANPxyz100',
    adapterType: 'AttocubeXYZ',
    category: 'XYZ Piezo Stage',
    connected: true,
    kind: 'motor',
    dimensionality: '3D',
    tags: ['Test', 'Piezo', 'XYZ Stage', 'Actuator', 'Nanopositioning'],
    description: 'Closed-loop XYZ piezo nanopositioning system',
    parameters: {
      positionX: {
        name: 'X Position',
        type: 'number',
        value: 50.0,
        unit: 'µm',
        min: 0,
        max: 100,
      },
      positionY: {
        name: 'Y Position',
        type: 'number',
        value: 50.0,
        unit: 'µm',
        min: 0,
        max: 100,
      },
      positionZ: {
        name: 'Z Position',
        type: 'number',
        value: 50.0,
        unit: 'µm',
        min: 0,
        max: 100,
      },
    },
  },
];

// ============================================================================
// SOURCES (Lasers, etc.)
// ============================================================================

export const SOURCES: Instrument[] = [
  {
    id: 'coherent-tisapph-001',
    name: 'Tunable Laser',
    manufacturer: 'Coherent',
    modelNumber: 'Chameleon Discovery',
    adapterType: 'CoherentTiSapphire',
    category: 'Laser',
    connected: true,
    kind: 'source',
    dimensionality: '0D',
    tags: ['Test', 'Laser', 'Source', 'Tunable', 'IR'],
    description: 'Ti:Sapphire tunable laser 680-1080 nm',
    parameters: {
      wavelength: {
        name: 'Wavelength',
        type: 'number',
        value: 800,
        unit: 'nm',
        min: 680,
        max: 1080,
      },
      power: {
        name: 'Power',
        type: 'number',
        value: 2.5,
        unit: 'W',
        min: 0,
        max: 3,
      },
      repRate: {
        name: 'Rep. Rate',
        type: 'number',
        value: 80,
        unit: 'MHz',
      },
    },
  },
];

// ============================================================================
// COMBINED CATALOG
// ============================================================================

export const INSTRUMENT_CATALOG: Instrument[] = [
  ...DETECTOR_0D,
  ...DETECTOR_1D,
  ...DETECTOR_2D,
  ...ACTUATOR_0D,
  ...ACTUATOR_1D,
  ...ACTUATOR_2D,
  ...ACTUATOR_3D,
  ...SOURCES,
];

/**
 * Get all unique manufacturers
 */
export function getManufacturers(): string[] {
  const manufacturers = new Set(INSTRUMENT_CATALOG.map(i => i.manufacturer));
  return Array.from(manufacturers).sort();
}

/**
 * Get all unique categories
 */
export function getCategories(): string[] {
  const categories = new Set(INSTRUMENT_CATALOG.map(i => i.category));
  return Array.from(categories).sort();
}

/**
 * Get manufacturers for a specific category
 */
export function getManufacturersByCategory(category: string): string[] {
  const manufacturers = new Set(
    INSTRUMENT_CATALOG
      .filter(i => i.category === category)
      .map(i => i.manufacturer)
  );
  return Array.from(manufacturers).sort();
}

/**
 * Get categories for a specific manufacturer
 */
export function getCategoriesByManufacturer(manufacturer: string): string[] {
  const categories = new Set(
    INSTRUMENT_CATALOG
      .filter(i => i.manufacturer === manufacturer)
      .map(i => i.category)
  );
  return Array.from(categories).sort();
}

/**
 * Get instrument models for manufacturer + category
 */
export function getInstrumentsByManufacturerAndCategory(
  manufacturer: string,
  category: string
): Instrument[] {
  return INSTRUMENT_CATALOG.filter(
    i => i.manufacturer === manufacturer && i.category === category
  );
}

/**
 * Get single instrument by ID
 */
export function getInstrumentById(id: string): Instrument | undefined {
  return INSTRUMENT_CATALOG.find(i => i.id === id);
}
