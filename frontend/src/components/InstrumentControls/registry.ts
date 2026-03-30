import React from 'react';
import { Instrument } from '@/data/instruments';
import {
  PowerMeterUI,
  LaserControlUI,
  MotionStageUI,
  CameraUI,
  SpectrometerUI,
  LockInUI,
  GenericDetectorUI,
  GenericActuatorUI,
} from './SpecificUIs';

interface UIComponentProps {
  instrument: Instrument;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onParameterChange?: (key: string, value: any) => void;
}

// Registry mapping category to React component
const INSTRUMENT_UI_REGISTRY: Record<string, React.ComponentType<UIComponentProps>> = {
  // Power Meters
  'Power Meter': PowerMeterUI,
  'Photodiode': PowerMeterUI,

  // Lasers
  'Laser': LaserControlUI,

  // Motion & Stages
  'Motion Controller': MotionStageUI,
  'Translation Stage': MotionStageUI,
  'Linear Stage': MotionStageUI,
  'XY Stage': MotionStageUI,
  'XYZ Stage': MotionStageUI,
  'Servo Motor': MotionStageUI,
  'Piezo Controller': MotionStageUI,
  'XY Piezo Stage': MotionStageUI,
  'XYZ Piezo Stage': MotionStageUI,

  // Cameras
  'Camera': CameraUI,
  'Thermal Camera': CameraUI,

  // Spectrometers
  'Spectrometer': SpectrometerUI,
  'Spectrograph': SpectrometerUI,

  // Lock-in & Electronics
  'Lock-in Amplifier': LockInUI,
  'Source Meter': GenericDetectorUI,
  'Multimeter': GenericDetectorUI,
  'Data Acquisition': GenericDetectorUI,
  'Position Encoder': GenericDetectorUI,
  'Oscilloscope': GenericDetectorUI,

  // Actuators & Sources
  'Chopper': GenericActuatorUI,
  'Fluidic Pump': GenericActuatorUI,
  'Power Supply': GenericActuatorUI,
};

/**
 * Get the appropriate UI component for an instrument
 * Falls back to generic component if category not in registry
 */
export function getUIComponent(
  category?: string,
  kind?: 'detector' | 'source' | 'motor' | 'actuator',
  dimensionality?: '0D' | '1D' | '2D' | '3D'
): React.ComponentType<UIComponentProps> {
  // Try exact category match first
  if (category && category in INSTRUMENT_UI_REGISTRY) {
    return INSTRUMENT_UI_REGISTRY[category];
  }

  // Fall back to generic based on kind
  if (kind === 'actuator' || kind === 'motor') {
    return GenericActuatorUI;
  }

  // Default to generic detector
  return GenericDetectorUI;
}

/**
 * Export all UI components for direct access if needed
 */
export {
  PowerMeterUI,
  LaserControlUI,
  MotionStageUI,
  CameraUI,
  SpectrometerUI,
  LockInUI,
  GenericDetectorUI,
  GenericActuatorUI,
};
