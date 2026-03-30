import React, { useState } from 'react';
import {
  ParameterInput,
  ParameterGrid,
  ActionButton,
  DataDisplay,
  StatusIndicator,
  ConnectDisconnectPanel,
} from './BaseComponents';
import { Instrument } from '@/data/instruments';

interface SpecificUIProps {
  instrument: Instrument;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onParameterChange?: (key: string, value: any) => void;
}

/**
 * Power Meter UI - Shows power readings with range selectors
 */
export const PowerMeterUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Main Reading */}
      <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/10 rounded-lg p-6">
        <DataDisplay
          label="Optical Power"
          value={instrument.parameters.power?.value || 0}
          unit={instrument.parameters.power?.unit || 'mW'}
          precision={1}
        />
      </div>

      {/* Controls */}
      <div className="space-y-4">
        <ParameterInput
          name="Wavelength"
          value={instrument.parameters.wavelength?.value || 633}
          onChange={(val) => onParameterChange?.('wavelength', val)}
          unit={instrument.parameters.wavelength?.unit || 'nm'}
          min={instrument.parameters.wavelength?.min}
          max={instrument.parameters.wavelength?.max}
          disabled={!instrument.connected}
        />
        {instrument.parameters.range && (
          <ParameterInput
            name="Autorange"
            value={instrument.parameters.range?.value || true}
            onChange={(val) => onParameterChange?.('range', val)}
            type="boolean"
            disabled={!instrument.connected}
          />
        )}
      </div>

      {/* Connect/Disconnect */}
      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Laser Control UI - Wavelength, power, and pulse controls
 */
export const LaserControlUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Main Controls */}
      <div className="bg-gradient-to-br from-red-50 to-orange-100 dark:from-red-900/20 dark:to-orange-900/10 rounded-lg p-6">
        <DataDisplay
          label="Output Power"
          value={instrument.parameters.power?.value || 0}
          unit={instrument.parameters.power?.unit || 'W'}
          precision={2}
        />
      </div>

      {/* Parameters */}
      <div className="space-y-4">
        <ParameterInput
          name="Wavelength"
          value={instrument.parameters.wavelength?.value || 800}
          onChange={(val) => onParameterChange?.('wavelength', val)}
          unit={instrument.parameters.wavelength?.unit || 'nm'}
          min={instrument.parameters.wavelength?.min}
          max={instrument.parameters.wavelength?.max}
          disabled={!instrument.connected}
        />
        <ParameterInput
          name="Power"
          value={instrument.parameters.power?.value || 0}
          onChange={(val) => onParameterChange?.('power', val)}
          unit={instrument.parameters.power?.unit || 'W'}
          min={instrument.parameters.power?.min}
          max={instrument.parameters.power?.max}
          disabled={!instrument.connected}
        />
        {instrument.parameters.repRate && (
          <ParameterInput
            name="Repetition Rate"
            value={instrument.parameters.repRate?.value || 80}
            onChange={(val) => onParameterChange?.('repRate', val)}
            unit={instrument.parameters.repRate?.unit || 'MHz'}
            disabled={!instrument.connected}
          />
        )}
      </div>

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Motion Stage UI - Position readout, move buttons, speed control
 */
export const MotionStageUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Position Display */}
      {instrument.parameters.positionX !== undefined && instrument.parameters.positionY !== undefined ? (
        <div className="grid grid-cols-2 gap-4">
          <DataDisplay
            label="X Position"
            value={instrument.parameters.positionX?.value || 0}
            unit={instrument.parameters.positionX?.unit || 'mm'}
          />
          <DataDisplay
            label="Y Position"
            value={instrument.parameters.positionY?.value || 0}
            unit={instrument.parameters.positionY?.unit || 'mm'}
          />
        </div>
      ) : (
        <DataDisplay
          label="Position"
          value={instrument.parameters.position?.value || 0}
          unit={instrument.parameters.position?.unit || 'mm'}
        />
      )}

      {/* Controls */}
      <div className="space-y-4">
        <ParameterInput
          name="Velocity"
          value={instrument.parameters.velocity?.value || 5}
          onChange={(val) => onParameterChange?.('velocity', val)}
          unit={instrument.parameters.velocity?.unit || 'mm/s'}
          min={instrument.parameters.velocity?.min}
          max={instrument.parameters.velocity?.max}
          disabled={!instrument.connected}
        />
      </div>

      {/* Action Buttons */}
      <div className="grid grid-cols-2 gap-3">
        <ActionButton
          label="Move ←"
          onClick={() => console.log('Move left')}
          variant="secondary"
          disabled={!instrument.connected}
        />
        <ActionButton
          label="Move →"
          onClick={() => console.log('Move right')}
          variant="secondary"
          disabled={!instrument.connected}
        />
      </div>

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Camera UI - Exposure, gain, binning controls
 */
export const CameraUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Camera Status */}
      <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-4">
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600 dark:text-gray-400">Camera Ready</span>
          <StatusIndicator connected={instrument.connected} showLabel={false} />
        </div>
      </div>

      {/* Exposure & Gain Controls */}
      <div className="space-y-4">
        <ParameterInput
          name="Exposure Time"
          value={instrument.parameters.exposure?.value || 10}
          onChange={(val) => onParameterChange?.('exposure', val)}
          unit={instrument.parameters.exposure?.unit || 'ms'}
          min={instrument.parameters.exposure?.min}
          max={instrument.parameters.exposure?.max}
          disabled={!instrument.connected}
        />
        {instrument.parameters.gain && (
          <ParameterInput
            name="Gain"
            value={instrument.parameters.gain?.value || 100}
            onChange={(val) => onParameterChange?.('gain', val)}
            min={instrument.parameters.gain?.min}
            max={instrument.parameters.gain?.max}
            disabled={!instrument.connected}
          />
        )}
        {instrument.parameters.binning && (
          <ParameterInput
            name="Binning"
            value={instrument.parameters.binning?.value || '1x1'}
            onChange={(val) => onParameterChange?.('binning', val)}
            type="select"
            options={instrument.parameters.binning?.options}
            disabled={!instrument.connected}
          />
        )}
      </div>

      {/* Capture Button */}
      <ActionButton
        label="Capture Frame"
        onClick={() => console.log('Capture')}
        variant="primary"
        disabled={!instrument.connected}
      />

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Spectrometer UI - Wavelength, integration time, averaging
 */
export const SpectrometerUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Spectrum Display */}
      <div className="bg-blue-100 dark:bg-blue-900/20 rounded-lg p-6 h-40 flex items-center justify-center">
        <div className="text-center text-gray-600 dark:text-gray-400">
          <div className="text-sm">Spectrum Display</div>
          <div className="text-xs mt-1">(Connected to PyQtGraph)</div>
        </div>
      </div>

      {/* Controls */}
      <div className="space-y-4">
        <ParameterInput
          name="Center Wavelength"
          value={instrument.parameters.wavelength?.value || 550}
          onChange={(val) => onParameterChange?.('wavelength', val)}
          unit={instrument.parameters.wavelength?.unit || 'nm'}
          disabled={!instrument.connected}
        />
        <ParameterInput
          name="Integration Time"
          value={instrument.parameters.integrationTime?.value || 10}
          onChange={(val) => onParameterChange?.('integrationTime', val)}
          unit={instrument.parameters.integrationTime?.unit || 'ms'}
          min={instrument.parameters.integrationTime?.min}
          max={instrument.parameters.integrationTime?.max}
          disabled={!instrument.connected}
        />
        <ParameterInput
          name="Averaging Scans"
          value={instrument.parameters.averaging?.value || 5}
          onChange={(val) => onParameterChange?.('averaging', val)}
          min={instrument.parameters.averaging?.min}
          max={instrument.parameters.averaging?.max}
          disabled={!instrument.connected}
        />
      </div>

      {/* Action Buttons */}
      <ActionButton
        label="Acquire Spectrum"
        onClick={() => console.log('Acquire')}
        variant="primary"
        disabled={!instrument.connected}
      />

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Lock-in Amplifier UI - Frequency, phase, sensitivity, demodulation
 */
export const LockInUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Output Display */}
      <div className="grid grid-cols-2 gap-4">
        <DataDisplay
          label="X Output"
          value={instrument.parameters.xOutput?.value || 0}
          unit={instrument.parameters.xOutput?.unit || 'mV'}
          precision={1}
        />
        <DataDisplay
          label="Y Output"
          value={instrument.parameters.yOutput?.value || 0}
          unit={instrument.parameters.yOutput?.unit || 'mV'}
          precision={1}
        />
      </div>

      {/* Configuration */}
      <div className="space-y-4">
        <ParameterInput
          name="Reference Frequency"
          value={instrument.parameters.frequency?.value || 100000}
          onChange={(val) => onParameterChange?.('frequency', val)}
          unit={instrument.parameters.frequency?.unit || 'Hz'}
          disabled={!instrument.connected}
        />
        <ParameterInput
          name="Phase"
          value={instrument.parameters.phase?.value || 0}
          onChange={(val) => onParameterChange?.('phase', val)}
          unit={instrument.parameters.phase?.unit || '°'}
          min={-180}
          max={180}
          disabled={!instrument.connected}
        />
        <ParameterInput
          name="Sensitivity"
          value={instrument.parameters.sensitivity?.value || '100 nV'}
          onChange={(val) => onParameterChange?.('sensitivity', val)}
          type="select"
          options={instrument.parameters.sensitivity?.options}
          disabled={!instrument.connected}
        />
      </div>

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Generic Detector UI - Fallback for unknown detectors
 */
export const GenericDetectorUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Generic Parameter Grid */}
      <ParameterGrid
        parameters={instrument.parameters || {}}
        onParameterChange={onParameterChange}
        disabled={!instrument.connected}
      />

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};

/**
 * Generic Actuator UI - Fallback for unknown motors/actuators
 */
export const GenericActuatorUI: React.FC<SpecificUIProps> = ({
  instrument,
  onConnect,
  onDisconnect,
  onParameterChange,
}) => {
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {instrument.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {instrument.manufacturer} {instrument.modelNumber}
        </p>
      </div>

      {/* Generic Controls */}
      <ParameterGrid
        parameters={instrument.parameters || {}}
        onParameterChange={onParameterChange}
        disabled={!instrument.connected}
      />

      {/* Action Buttons */}
      <div className="grid grid-cols-2 gap-3">
        <ActionButton
          label="Start"
          onClick={() => console.log('Start')}
          variant="primary"
          disabled={!instrument.connected}
        />
        <ActionButton
          label="Stop"
          onClick={() => console.log('Stop')}
          variant="danger"
          disabled={!instrument.connected}
        />
      </div>

      <ConnectDisconnectPanel
        connected={instrument.connected}
        onConnect={() => {
          setLoading(true);
          setTimeout(() => {
            onConnect?.();
            setLoading(false);
          }, 500);
        }}
        onDisconnect={() => {
          setLoading(true);
          setTimeout(() => {
            onDisconnect?.();
            setLoading(false);
          }, 500);
        }}
        loading={loading}
      />
    </div>
  );
};
