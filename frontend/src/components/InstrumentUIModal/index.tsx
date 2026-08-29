import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  Activity,
  Gauge,
  Camera,
  Move3D,
  Play,
  Square,
  Download,
  RefreshCw,
  Zap,
  Target,
  BarChart3,
} from 'lucide-react';
import { DashboardInstrument, getInstrumentSchema, readInstrumentData, type InstrumentSchema } from '@/api';

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

// Reduce a real read() dict (one value per schema.readable key) down to the
// single series this modal's 0D/1D/2D visualizations expect. Real adapters
// can expose several readable axes (e.g. x/y/phase on a lock-in) — pick the
// first one rather than guessing which is "the" value.
function pickPrimarySeries(raw: Record<string, any>, schema: InstrumentSchema | null): { values: any; key: string | null; units?: string } {
  const keys = Object.keys(raw);
  if (keys.length === 0) return { values: null, key: null };
  const key = keys[0];
  return { values: raw[key], key, units: schema?.units[key] };
}

export function InstrumentUIModal({ instrument, isOpen, onClose }: InstrumentUIModalProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [data, setData] = useState<InstrumentData | null>(null);
  const [schema, setSchema] = useState<InstrumentSchema | null>(null);
  const [readError, setReadError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !instrument) return;
    getInstrumentSchema(instrument.id).then(setSchema).catch(() => setSchema(null));
  }, [isOpen, instrument?.id]);

  useEffect(() => {
    if (!isOpen || !instrument) return;

    const fetchData = () => {
      if (!instrument.connected) {
        setReadError('Not connected — connect it to see live data.');
        return;
      }
      readInstrumentData(instrument.id)
        .then((raw) => {
          setReadError(null);
          const { values, units } = pickPrimarySeries(raw, schema);
          setData({ timestamp: new Date().toISOString(), values, units, metadata: raw });
        })
        .catch((e) => setReadError(e instanceof Error ? e.message : 'Read failed'));
    };

    fetchData();
    const interval = setInterval(() => {
      if (isRecording) fetchData();
    }, 1000);

    return () => clearInterval(interval);
  }, [isOpen, instrument, isRecording, schema]);

  if (!isOpen || !instrument) return null;

  const handleRefresh = () => {
    if (!instrument.connected) {
      setReadError('Not connected — connect it to see live data.');
      return;
    }
    readInstrumentData(instrument.id)
      .then((raw) => {
        setReadError(null);
        const { values, units } = pickPrimarySeries(raw, schema);
        setData({ timestamp: new Date().toISOString(), values, units, metadata: raw });
      })
      .catch((e) => setReadError(e instanceof Error ? e.message : 'Read failed'));
  };

  const handleExport = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${instrument.id}_${data.timestamp.replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

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
    if (readError) return <div className="text-amber-600 dark:text-amber-400 text-sm">{readError}</div>;
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
        const rows = Array.isArray(data.values) ? (data.values as any[]) : [];
        const isNested = rows.length > 0 && Array.isArray(rows[0]);
        const height = rows.length;
        const width = isNested ? (rows[0] as any[]).length : rows.length;
        return (
          <div className="space-y-4">
            <div className="h-48 bg-black rounded border relative overflow-hidden flex items-center justify-center">
              {isNested ? (
                <Canvas2D data={rows as number[][]} />
              ) : (
                <span className="text-gray-500 text-sm">No image data</span>
              )}
              <div className="absolute top-2 right-2 text-xs text-gray-200 bg-black bg-opacity-50 px-2 py-1 rounded">
                {width}x{height}
              </div>
              <div className="absolute bottom-2 left-2 text-xs text-gray-200 bg-black bg-opacity-50 px-2 py-1 rounded">
                {data.units}
              </div>
            </div>
            <div className="text-xs text-gray-400 text-center">
              Live frame (grayscale, auto-scaled)
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

                  <button
                    onClick={handleRefresh}
                    disabled={!instrument.connected}
                    className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-md font-medium transition-colors"
                  >
                    <RefreshCw className="h-4 w-4" />
                    <span>Refresh</span>
                  </button>

                  <button
                    onClick={handleExport}
                    disabled={!data}
                    className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white rounded-md font-medium transition-colors"
                  >
                    <Download className="h-4 w-4" />
                    <span>Export Data</span>
                  </button>
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

/** Grayscale render of a 2D numeric array (e.g. camera frame), auto-scaled to its own min/max. */
function Canvas2D({ data }: { data: number[][] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const height = data.length;
    const width = data[0]?.length || 0;
    canvas.width = width;
    canvas.height = height;

    let min = Infinity, max = -Infinity;
    for (const row of data) for (const v of row) { if (v < min) min = v; if (v > max) max = v; }
    const range = max - min || 1;

    const img = ctx.createImageData(width, height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const v = Math.round(((data[y][x] - min) / range) * 255);
        const i = (y * width + x) * 4;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [data]);

  return <canvas ref={canvasRef} className="max-h-full max-w-full" style={{ imageRendering: 'pixelated' }} />;
}