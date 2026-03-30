import React, { useState, useEffect, useRef } from 'react';
import { FloatingWindow } from '@/components/FloatingWindow';
import { DashboardInstrument } from '@/api';
import { Activity, Gauge, Camera, Zap, Move3D, Target } from 'lucide-react';

interface InstrumentControlWindowProps {
  instrument: DashboardInstrument;
  isOpen: boolean;
  onClose: () => void;
}

// 0D Detector Component - Real-time counter with time traces
function Detector0D({ instrument }: { instrument: DashboardInstrument }) {
  const [currentValue, setCurrentValue] = useState(0);
  const [timeTrace, setTimeTrace] = useState<{ time: number; value: number }[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [settings, setSettings] = useState({
    sampleRate: 10, // Hz
    integrationTime: 100, // ms
    units: 'counts/s',
    scale: 'linear',
  });

  useEffect(() => {
    if (!isRecording) return;

    const interval = setInterval(() => {
      const now = Date.now();
      const newValue = Math.random() * 1000 +
                      Math.sin(now / 1000) * 200 +
                      (Math.random() - 0.5) * 50;

      setCurrentValue(newValue);

      setTimeTrace(prev => {
        const updated = [...prev, { time: now, value: newValue }];
        // Keep last 100 points
        return updated.slice(-100);
      });
    }, 1000 / settings.sampleRate);

    return () => clearInterval(interval);
  }, [isRecording, settings.sampleRate]);

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Real-time Counter */}
      <div className="bg-gray-50 dark:bg-gray-700 p-6 rounded-lg text-center">
        <div className="text-4xl font-mono font-bold text-blue-600 dark:text-blue-400">
          {currentValue.toFixed(2)}
        </div>
        <div className="text-sm text-gray-500 mt-2">{settings.units}</div>
        <div className="mt-4">
          <button
            onClick={() => setIsRecording(!isRecording)}
            className={`px-4 py-2 rounded-md font-medium transition-colors ${
              isRecording
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isRecording ? 'Stop' : 'Start'} Recording
          </button>
        </div>
      </div>

      {/* Time Trace Plot */}
      <div className="flex-1 bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Time Trace</h3>
        <div className="h-48 bg-white dark:bg-gray-800 rounded border relative">
          <svg className="w-full h-full">
            {timeTrace.length > 1 && (
              <polyline
                fill="none"
                stroke="rgb(59, 130, 246)"
                strokeWidth="2"
                points={timeTrace.map((point, i) => {
                  const x = (i / Math.max(timeTrace.length - 1, 1)) * 100;
                  const minVal = Math.min(...timeTrace.map(p => p.value));
                  const maxVal = Math.max(...timeTrace.map(p => p.value));
                  const y = 90 - ((point.value - minVal) / Math.max(maxVal - minVal, 1)) * 80;
                  return `${x}%,${y}%`;
                }).join(' ')}
              />
            )}
          </svg>
          <div className="absolute top-2 right-2 text-xs text-gray-500">
            {timeTrace.length} points
          </div>
        </div>
      </div>
    </div>
  );
}

// 1D Detector Component - Real-time plot for each pixel
function Detector1D({ instrument }: { instrument: DashboardInstrument }) {
  const [spectrumData, setSpectrumData] = useState<number[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [settings, setSettings] = useState({
    pixels: 1024,
    integrationTime: 100,
    binning: 1,
    units: 'counts',
  });

  useEffect(() => {
    if (!isRecording) return;

    const interval = setInterval(() => {
      const newSpectrum = Array.from({ length: settings.pixels }, (_, i) => {
        // Simulate spectrum with some peaks
        let value = Math.random() * 50 + 10; // baseline

        // Add some Gaussian peaks
        const peak1 = 200 * Math.exp(-0.5 * Math.pow((i - 300) / 50, 2));
        const peak2 = 150 * Math.exp(-0.5 * Math.pow((i - 700) / 30, 2));

        return value + peak1 + peak2;
      });

      setSpectrumData(newSpectrum);
    }, settings.integrationTime);

    return () => clearInterval(interval);
  }, [isRecording, settings]);

  const maxValue = Math.max(...spectrumData);

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Controls */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setIsRecording(!isRecording)}
              className={`px-4 py-2 rounded-md font-medium transition-colors ${
                isRecording
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-green-600 hover:bg-green-700 text-white'
              }`}
            >
              {isRecording ? 'Stop' : 'Start'} Acquisition
            </button>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {settings.pixels} pixels • {settings.integrationTime}ms
            </div>
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">
            Max: {maxValue.toFixed(0)} {settings.units}
          </div>
        </div>
      </div>

      {/* Spectrum Plot */}
      <div className="flex-1 bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Spectrum</h3>
        <div className="h-full bg-white dark:bg-gray-800 rounded border relative">
          <svg className="w-full h-full">
            {spectrumData.length > 0 && (
              <>
                {/* Spectrum line */}
                <polyline
                  fill="none"
                  stroke="rgb(59, 130, 246)"
                  strokeWidth="1"
                  points={spectrumData.map((value, i) => {
                    const x = (i / Math.max(spectrumData.length - 1, 1)) * 100;
                    const y = 95 - (value / Math.max(maxValue, 1)) * 90;
                    return `${x}%,${y}%`;
                  }).join(' ')}
                />
                {/* Fill area */}
                <polygon
                  fill="rgba(59, 130, 246, 0.1)"
                  points={`0%,95% ${spectrumData.map((value, i) => {
                    const x = (i / Math.max(spectrumData.length - 1, 1)) * 100;
                    const y = 95 - (value / Math.max(maxValue, 1)) * 90;
                    return `${x}%,${y}%`;
                  }).join(' ')} 100%,95%`}
                />
              </>
            )}
          </svg>
          {/* Cursor */}
          <div className="absolute top-2 left-2 text-xs text-gray-500 bg-white dark:bg-gray-800 px-2 py-1 rounded">
            Pixel: 0-{settings.pixels-1}
          </div>
        </div>
      </div>
    </div>
  );
}

// 2D Detector Component - Real-time image
function Detector2D({ instrument }: { instrument: DashboardInstrument }) {
  const [imageData, setImageData] = useState<number[][]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [settings, setSettings] = useState({
    width: 256,
    height: 256,
    exposureTime: 100,
    binning: 1,
    colormap: 'viridis',
  });
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!isRecording) return;

    const interval = setInterval(() => {
      // Generate mock 2D image data
      const newImage = Array.from({ length: settings.height }, (_, y) =>
        Array.from({ length: settings.width }, (_, x) => {
          // Create some interesting patterns
          const centerX = settings.width / 2;
          const centerY = settings.height / 2;
          const distance = Math.sqrt((x - centerX) ** 2 + (y - centerY) ** 2);

          let intensity = 100 + Math.random() * 50; // baseline noise
          intensity += 500 * Math.exp(-distance / 50); // central gaussian
          intensity += 200 * Math.sin(x / 20) * Math.sin(y / 20); // interference pattern

          return Math.max(0, intensity);
        })
      );

      setImageData(newImage);
    }, settings.exposureTime);

    return () => clearInterval(interval);
  }, [isRecording, settings]);

  // Render image to canvas
  useEffect(() => {
    if (!imageData.length || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const imageDataObj = ctx.createImageData(settings.width, settings.height);
    const data = imageDataObj.data;

    const maxVal = Math.max(...imageData.flat());

    for (let y = 0; y < settings.height; y++) {
      for (let x = 0; x < settings.width; x++) {
        const i = (y * settings.width + x) * 4;
        const normalized = imageData[y][x] / maxVal;

        // Simple grayscale colormap
        const intensity = Math.floor(normalized * 255);
        data[i] = intensity;     // R
        data[i + 1] = intensity; // G
        data[i + 2] = intensity; // B
        data[i + 3] = 255;       // A
      }
    }

    ctx.putImageData(imageDataObj, 0, 0);
  }, [imageData, settings]);

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Controls */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setIsRecording(!isRecording)}
              className={`px-4 py-2 rounded-md font-medium transition-colors ${
                isRecording
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-green-600 hover:bg-green-700 text-white'
              }`}
            >
              {isRecording ? 'Stop' : 'Start'} Capture
            </button>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {settings.width}×{settings.height} • {settings.exposureTime}ms
            </div>
          </div>
        </div>
      </div>

      {/* Image Display */}
      <div className="flex-1 bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Live Image</h3>
        <div className="h-full flex items-center justify-center bg-white dark:bg-gray-800 rounded border">
          <canvas
            ref={canvasRef}
            width={settings.width}
            height={settings.height}
            className="max-w-full max-h-full border"
            style={{ imageRendering: 'pixelated' }}
          />
        </div>
      </div>
    </div>
  );
}

// 0D Motor Component - Status + switches
function Motor0D({ instrument }: { instrument: DashboardInstrument }) {
  const [isMoving, setIsMoving] = useState(false);
  const [status, setStatus] = useState('Idle');
  const [switches, setSwitches] = useState({
    forwardLimit: false,
    reverseLimit: false,
    home: false,
    enabled: true,
  });

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Status Display */}
      <div className="bg-gray-50 dark:bg-gray-700 p-6 rounded-lg text-center">
        <div className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          Motor Status
        </div>
        <div className={`text-lg font-medium ${
          isMoving ? 'text-blue-600' : switches.enabled ? 'text-green-600' : 'text-red-600'
        }`}>
          {status}
        </div>
      </div>

      {/* Control Switches */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-4">Control</h3>
        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => {
              setIsMoving(true);
              setTimeout(() => setIsMoving(false), 2000);
            }}
            disabled={!switches.enabled || isMoving}
            className="px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-md font-medium transition-colors"
          >
            Home
          </button>
          <button
            onClick={() => setSwitches(prev => ({ ...prev, enabled: !prev.enabled }))}
            className={`px-4 py-3 rounded-md font-medium transition-colors ${
              switches.enabled
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {switches.enabled ? 'Disable' : 'Enable'}
          </button>
        </div>
      </div>

      {/* Limit Switches */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-4">Limit Switches</h3>
        <div className="space-y-3">
          {Object.entries({
            'Forward Limit': switches.forwardLimit,
            'Reverse Limit': switches.reverseLimit,
            'Home Switch': switches.home,
          }).map(([label, active]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
              <div className={`w-3 h-3 rounded-full ${
                active ? 'bg-red-500' : 'bg-green-500'
              }`} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// 1D Motor Component - Position + target + slide bar
function Motor1D({ instrument }: { instrument: DashboardInstrument }) {
  const [position, setPosition] = useState(50);
  const [targetPosition, setTargetPosition] = useState(50);
  const [isMoving, setIsMoving] = useState(false);
  const [settings, setSettings] = useState({
    minPos: 0,
    maxPos: 100,
    units: 'mm',
    resolution: 0.1,
    speed: 10, // units/s
    continuousMode: false,
  });

  const handleMove = () => {
    setIsMoving(true);
    // Simulate movement
    const startPos = position;
    const endPos = targetPosition;
    const startTime = Date.now();
    const distance = Math.abs(endPos - startPos);
    const duration = (distance / settings.speed) * 1000;

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const currentPos = startPos + (endPos - startPos) * progress;

      setPosition(currentPos);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        setIsMoving(false);
      }
    };

    animate();
  };

  const handleSliderChange = (value: number) => {
    setTargetPosition(value);
    if (settings.continuousMode) {
      setPosition(value);
    }
  };

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Position Display */}
      <div className="bg-gray-50 dark:bg-gray-700 p-6 rounded-lg text-center">
        <div className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Current Position
        </div>
        <div className="text-3xl font-mono font-bold text-blue-600 dark:text-blue-400">
          {position.toFixed(2)} {settings.units}
        </div>
        <div className={`text-sm mt-2 ${isMoving ? 'text-blue-600' : 'text-green-600'}`}>
          {isMoving ? 'Moving...' : 'Ready'}
        </div>
      </div>

      {/* Target Position Input */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Target Position</h3>
        <div className="flex items-center space-x-3">
          <input
            type="number"
            value={targetPosition}
            onChange={(e) => setTargetPosition(parseFloat(e.target.value) || 0)}
            min={settings.minPos}
            max={settings.maxPos}
            step={settings.resolution}
            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
          />
          <span className="text-sm text-gray-600 dark:text-gray-400">{settings.units}</span>
          <button
            onClick={handleMove}
            disabled={isMoving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-md font-medium transition-colors"
          >
            Move
          </button>
        </div>
      </div>

      {/* Position Slider */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Position Control</h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
            <span>{settings.minPos}</span>
            <span>{settings.maxPos}</span>
          </div>
          <input
            type="range"
            min={settings.minPos}
            max={settings.maxPos}
            step={settings.resolution}
            value={targetPosition}
            onChange={(e) => handleSliderChange(parseFloat(e.target.value))}
            className="w-full h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer"
          />
          <div className="flex items-center justify-center">
            <label className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={settings.continuousMode}
                onChange={(e) => setSettings(prev => ({ ...prev, continuousMode: e.target.checked }))}
                className="rounded border-gray-300 dark:border-gray-600"
              />
              <span className="text-sm text-gray-600 dark:text-gray-400">Continuous Mode</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

// Multi-axis Motor Component - Multiple slide bars
function MotorMultiAxis({ instrument }: { instrument: DashboardInstrument }) {
  const numAxes = parseInt(instrument.dimensionality[0]) || 2;
  const [positions, setPositions] = useState<number[]>(Array(numAxes).fill(50));
  const [targetPositions, setTargetPositions] = useState<number[]>(Array(numAxes).fill(50));
  const [isMoving, setIsMoving] = useState<boolean[]>(Array(numAxes).fill(false));

  const axisLabels = ['X', 'Y', 'Z', 'U', 'V', 'W'];
  const settings = {
    minPos: 0,
    maxPos: 100,
    units: 'mm',
    resolution: 0.1,
    speed: 10,
  };

  const handleMoveAxis = (axisIndex: number) => {
    const newIsMoving = [...isMoving];
    newIsMoving[axisIndex] = true;
    setIsMoving(newIsMoving);

    // Simulate movement for this axis
    const startPos = positions[axisIndex];
    const endPos = targetPositions[axisIndex];
    const startTime = Date.now();
    const distance = Math.abs(endPos - startPos);
    const duration = (distance / settings.speed) * 1000;

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const currentPos = startPos + (endPos - startPos) * progress;

      setPositions(prev => {
        const updated = [...prev];
        updated[axisIndex] = currentPos;
        return updated;
      });

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        setIsMoving(prev => {
          const updated = [...prev];
          updated[axisIndex] = false;
          return updated;
        });
      }
    };

    animate();
  };

  return (
    <div className="h-full flex flex-col space-y-4">
      {/* Multi-Axis Position Display */}
      <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Current Positions</h3>
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: numAxes }).map((_, i) => (
            <div key={i} className="text-center">
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                {axisLabels[i]} Axis
              </div>
              <div className="text-lg font-mono font-bold text-blue-600 dark:text-blue-400">
                {positions[i]?.toFixed(2)} {settings.units}
              </div>
              <div className={`text-xs ${isMoving[i] ? 'text-blue-600' : 'text-green-600'}`}>
                {isMoving[i] ? 'Moving' : 'Ready'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Individual Axis Controls */}
      <div className="flex-1 space-y-3">
        {Array.from({ length: numAxes }).map((_, i) => (
          <div key={i} className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-gray-900 dark:text-white">
                {axisLabels[i]} Axis
              </h4>
              <button
                onClick={() => handleMoveAxis(i)}
                disabled={isMoving[i]}
                className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white text-sm rounded-md font-medium transition-colors"
              >
                Move
              </button>
            </div>

            <div className="flex items-center space-x-3 mb-3">
              <input
                type="number"
                value={targetPositions[i]}
                onChange={(e) => {
                  const newTargets = [...targetPositions];
                  newTargets[i] = parseFloat(e.target.value) || 0;
                  setTargetPositions(newTargets);
                }}
                min={settings.minPos}
                max={settings.maxPos}
                step={settings.resolution}
                className="w-20 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              />
              <span className="text-xs text-gray-600 dark:text-gray-400">{settings.units}</span>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
                <span>{settings.minPos}</span>
                <span>{settings.maxPos}</span>
              </div>
              <input
                type="range"
                min={settings.minPos}
                max={settings.maxPos}
                step={settings.resolution}
                value={targetPositions[i]}
                onChange={(e) => {
                  const newTargets = [...targetPositions];
                  newTargets[i] = parseFloat(e.target.value);
                  setTargetPositions(newTargets);
                }}
                className="w-full h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function InstrumentControlWindow({ instrument, isOpen, onClose }: InstrumentControlWindowProps) {
  const [showSettings, setShowSettings] = useState(false);

  const getIcon = () => {
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

  const Icon = getIcon();

  const renderInstrumentUI = () => {
    if (instrument.kind === 'detector') {
      switch (instrument.dimensionality) {
        case '0D':
          return <Detector0D instrument={instrument} />;
        case '1D':
          return <Detector1D instrument={instrument} />;
        case '2D':
          return <Detector2D instrument={instrument} />;
        default:
          return <div>Unsupported detector dimensionality: {instrument.dimensionality}</div>;
      }
    } else if (instrument.kind === 'motor') {
      if (instrument.dimensionality === '0D') {
        return <Motor0D instrument={instrument} />;
      } else if (instrument.dimensionality === '1D') {
        return <Motor1D instrument={instrument} />;
      } else {
        return <MotorMultiAxis instrument={instrument} />;
      }
    }

    return <div>Unsupported instrument type: {instrument.kind}</div>;
  };

  return (
    <FloatingWindow
      title={`${instrument.name} - ${instrument.dimensionality} ${instrument.kind}`}
      isOpen={isOpen}
      onClose={onClose}
      initialWidth={800}
      initialHeight={600}
      showSettings={true}
      onSettingsClick={() => setShowSettings(!showSettings)}
    >
      {renderInstrumentUI()}
    </FloatingWindow>
  );
}