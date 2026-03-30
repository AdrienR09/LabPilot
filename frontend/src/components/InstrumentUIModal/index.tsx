import React, { useState, useEffect } from 'react';
import {
  X,
  Activity,
  Gauge,
  Camera,
  Move3D,
  Play,
  Square,
  Settings,
  Download,
  RefreshCw,
  Zap,
  Target,
  BarChart3,
} from 'lucide-react';
import { DashboardInstrument } from '@/api';

interface InstrumentUIModalProps {
  instrument: DashboardInstrument | null;
  isOpen: boolean;
  onClose: () => void;
}

interface InstrumentData {
  timestamp: string;
  values: number | number[] | number[][];
  units?: string;
  metadata?: Record<string, any>;
}

export function InstrumentUIModal({ instrument, isOpen, onClose }: InstrumentUIModalProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [data, setData] = useState<InstrumentData | null>(null);
  const [settings, setSettings] = useState({
    sampleRate: 1000,
    integrationTime: 100,
    autoRange: true,
    gain: 1,
  });

  // Simulate data based on instrument type
  useEffect(() => {
    if (!isOpen || !instrument) return;

    const generateMockData = () => {
      const timestamp = new Date().toISOString();
      let values: number | number[] | number[][];
      let units = '';

      switch (instrument.dimensionality) {
        case '0D':
          // Single value (power meter, temperature sensor, etc.)
          values = Math.random() * 100 + Math.sin(Date.now() / 1000) * 10;
          units = instrument.kind === 'detector' ? 'mW' : 'V';
          break;

        case '1D':
          // Array of values (spectrum, trace, etc.)
          values = Array.from({ length: 1024 }, (_, i) =>
            Math.sin(i * 0.1) + Math.random() * 0.1
          );
          units = 'counts';
          break;

        case '2D':
          // 2D array (image, heatmap, etc.)
          values = Array.from({ length: 256 }, () =>
            Array.from({ length: 256 }, () => Math.random() * 255)
          );
          units = 'intensity';
          break;

        default:
          values = 0;
          units = '';
      }

      setData({
        timestamp,
        values,
        units,
        metadata: {
          temperature: 22.5,
          connected: instrument.connected,
          adapter: instrument.adapter_type,
        },
      });
    };

    // Generate initial data
    generateMockData();

    // Auto-refresh data if recording
    const interval = setInterval(() => {
      if (isRecording) {
        generateMockData();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isOpen, instrument, isRecording]);

  if (!isOpen || !instrument) return null;

  const getInstrumentIcon = () => {
    if (instrument.kind === 'detector') {
      if (instrument.dimensionality === '0D') return Gauge;
      if (instrument.dimensionality === '1D') return Activity;
      if (instrument.dimensionality === '2D') return Camera;
    }
    if (instrument.kind === 'motor') {
      return Move3D;
    }
    return Zap;
  };

  const Icon = getInstrumentIcon();

  const renderDataVisualization = () => {
    if (!data) return <div className="text-gray-500">No data available</div>;

    switch (instrument.dimensionality) {
      case '0D':
        return (
          <div className="text-center">
            <div className="text-4xl font-mono font-bold text-blue-600 dark:text-blue-400">
              {typeof data.values === 'number' ? data.values.toFixed(3) : '---'}
            </div>
            <div className="text-sm text-gray-500 mt-1">{data.units}</div>
            <div className="mt-4 text-xs text-gray-400">
              Last updated: {new Date(data.timestamp).toLocaleTimeString()}
            </div>
          </div>
        );

      case '1D':
        const values = data.values as number[];
        return (
          <div className="space-y-4">
            <div className="h-48 bg-gray-50 dark:bg-gray-700 rounded border relative">
              <svg className="w-full h-full">
                {values && values.map((value, i) => (
                  <rect
                    key={i}
                    x={i * (100 / values.length) + '%'}
                    y={50 - (value * 40) + '%'}
                    width="2"
                    height={Math.abs(value * 40) + '%'}
                    fill="rgb(59, 130, 246)"
                    opacity="0.7"
                  />
                ))}
              </svg>
              <div className="absolute top-2 right-2 text-xs text-gray-500">
                {values?.length || 0} points
              </div>
            </div>
            <div className="text-xs text-gray-400 text-center">
              {data.units} vs. channel
            </div>
          </div>
        );

      case '2D':
        return (
          <div className="space-y-4">
            <div className="h-48 bg-gradient-to-br from-blue-100 via-purple-100 to-pink-100 dark:from-blue-900 dark:via-purple-900 dark:to-pink-900 rounded border relative">
              <div className="absolute inset-0 bg-black bg-opacity-10 rounded"></div>
              <div className="absolute top-2 right-2 text-xs text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 px-2 py-1 rounded">
                256x256
              </div>
              <div className="absolute bottom-2 left-2 text-xs text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 px-2 py-1 rounded">
                {data.units}
              </div>
            </div>
            <div className="text-xs text-gray-400 text-center">
              2D intensity map
            </div>
          </div>
        );

      default:
        return <div className="text-gray-500">Visualization not available</div>;
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
              <Icon className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                {instrument.name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {instrument.dimensionality} {instrument.kind} • {instrument.adapter_type}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <div className="p-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column - Controls */}
            <div className="space-y-6">
              {/* Connection Status */}
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                  Status
                </h3>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Connection</span>
                    <span className={`text-sm font-medium ${
                      instrument.connected
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}>
                      {instrument.connected ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Recording</span>
                    <span className={`text-sm font-medium ${
                      isRecording
                        ? 'text-blue-600 dark:text-blue-400'
                        : 'text-gray-600 dark:text-gray-400'
                    }`}>
                      {isRecording ? 'Active' : 'Stopped'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Control Buttons */}
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                  Controls
                </h3>
                <div className="space-y-2">
                  <button
                    onClick={() => setIsRecording(!isRecording)}
                    disabled={!instrument.connected}
                    className={`w-full flex items-center justify-center space-x-2 px-4 py-2 rounded-md font-medium transition-colors ${
                      isRecording
                        ? 'bg-red-600 hover:bg-red-700 text-white'
                        : 'bg-green-600 hover:bg-green-700 text-white disabled:bg-gray-400'
                    }`}
                  >
                    {isRecording ? (
                      <>
                        <Square className="h-4 w-4" />
                        <span>Stop Recording</span>
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4" />
                        <span>Start Recording</span>
                      </>
                    )}
                  </button>

                  <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors">
                    <RefreshCw className="h-4 w-4" />
                    <span>Refresh</span>
                  </button>

                  <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md font-medium transition-colors">
                    <Download className="h-4 w-4" />
                    <span>Export Data</span>
                  </button>
                </div>
              </div>

              {/* Settings */}
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                  <Settings className="h-4 w-4 mr-2" />
                  Settings
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                      Sample Rate (Hz)
                    </label>
                    <input
                      type="number"
                      value={settings.sampleRate}
                      onChange={(e) => setSettings({...settings, sampleRate: parseInt(e.target.value)})}
                      className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                      Integration Time (ms)
                    </label>
                    <input
                      type="number"
                      value={settings.integrationTime}
                      onChange={(e) => setSettings({...settings, integrationTime: parseInt(e.target.value)})}
                      className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    />
                  </div>

                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="autoRange"
                      checked={settings.autoRange}
                      onChange={(e) => setSettings({...settings, autoRange: e.target.checked})}
                      className="rounded border-gray-300 dark:border-gray-600"
                    />
                    <label htmlFor="autoRange" className="text-xs text-gray-600 dark:text-gray-400">
                      Auto Range
                    </label>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column - Data Visualization */}
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                  <BarChart3 className="h-4 w-4 mr-2" />
                  Data Visualization
                </h3>
                <div className="min-h-[300px] flex items-center justify-center">
                  {renderDataVisualization()}
                </div>
              </div>

              {/* Tags */}
              {instrument.tags && instrument.tags.length > 0 && (
                <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                    Tags
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {instrument.tags.map((tag, index) => (
                      <span
                        key={index}
                        className="inline-flex items-center px-2 py-1 rounded-md text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              {data?.metadata && (
                <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                    Metadata
                  </h3>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(data.metadata).map(([key, value]) => (
                      <div key={key} className="flex justify-between">
                        <span className="text-gray-600 dark:text-gray-400 capitalize">
                          {key.replace('_', ' ')}:
                        </span>
                        <span className="text-gray-900 dark:text-white font-mono">
                          {String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}