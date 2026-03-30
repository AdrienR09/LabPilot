import React from 'react';
import { DashboardInstrument } from '@/api';
import {
  Activity, Gauge, Camera, Move3D, Play, Square, RotateCcw,
  ZoomIn, ZoomOut, Grid, Settings, Home, SkipBack, SkipForward,
  MousePointerClick, MoreHorizontal
} from 'lucide-react';

// This component will be rendered in separate browser windows
export function InstrumentWindowContent() {
  // Get instrument data from URL params or localStorage
  const getInstrumentData = (): DashboardInstrument | null => {
    try {
      const params = new URLSearchParams(window.location.search);
      const instrumentData = params.get('data');
      if (instrumentData) {
        return JSON.parse(decodeURIComponent(instrumentData));
      }

      // Fallback to localStorage
      const stored = localStorage.getItem('instrumentWindowData');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  };

  const instrument = getInstrumentData();

  if (!instrument) {
    return (
      <div className="p-8 text-center bg-gray-900 text-white min-h-screen flex items-center justify-center">
        <div className="text-red-400">Failed to load instrument data</div>
      </div>
    );
  }

  // Render directly without any navigation/header - full window use
  return <InstrumentUI instrument={instrument} />;
}

// Professional pyqtgraph-style plot component
interface PyQtGraphProps {
  data: { x: number; y: number }[] | number[][];
  title?: string;
  xLabel?: string;
  yLabel?: string;
  xUnit?: string;
  yUnit?: string;
  className?: string;
  type?: '1d' | '2d';
  colormap?: 'viridis' | 'plasma' | 'grayscale';
  showToolbar?: boolean;
  onSettingsClick?: () => void;
}

function PyQtGraphPlot({
  data,
  title,
  xLabel = "X",
  yLabel = "Y",
  xUnit = "",
  yUnit = "",
  className = "",
  type = '1d',
  colormap = 'viridis',
  showToolbar = true,
  onSettingsClick
}: PyQtGraphProps) {
  const [viewState, setViewState] = React.useState({
    zoom: 1,
    panX: 0,
    panY: 0,
    autoScale: true,
    showGrid: true,
    logX: false,
    logY: false
  });

  const [isDragging, setIsDragging] = React.useState(false);
  const [dragStart, setDragStart] = React.useState({ x: 0, y: 0 });
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number; show: boolean }>({ x: 0, y: 0, show: false });
  const [isZooming, setIsZooming] = React.useState(false);

  const svgRef = React.useRef<SVGSVGElement>(null);
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);

  // Calculate data bounds
  const getDataBounds = React.useCallback(() => {
    if (type === '1d' && Array.isArray(data) && data.length > 0) {
      const xValues = (data as { x: number; y: number }[]).map(d => d.x);
      const yValues = (data as { x: number; y: number }[]).map(d => d.y);
      return {
        xMin: Math.min(...xValues),
        xMax: Math.max(...xValues),
        yMin: Math.min(...yValues),
        yMax: Math.max(...yValues)
      };
    }
    return { xMin: 0, xMax: 100, yMin: 0, yMax: 100 };
  }, [data, type]);

  const bounds = getDataBounds();

  // Transform coordinates from data space to screen space
  const transformPoint = React.useCallback((x: number, y: number, svgWidth: number, svgHeight: number) => {
    const margin = { left: 60, bottom: 50, top: 30, right: 30 };
    const plotWidth = svgWidth - margin.left - margin.right;
    const plotHeight = svgHeight - margin.top - margin.bottom;

    let xRange = bounds.xMax - bounds.xMin;
    let yRange = bounds.yMax - bounds.yMin;

    // Handle log scaling
    if (viewState.logX && bounds.xMin > 0) {
      const logXMin = Math.log10(bounds.xMin);
      const logXMax = Math.log10(bounds.xMax);
      const logX = Math.log10(x);
      var screenX = margin.left + ((logX - logXMin) / (logXMax - logXMin)) * plotWidth * viewState.zoom + viewState.panX;
    } else {
      var screenX = margin.left + ((x - bounds.xMin) / xRange) * plotWidth * viewState.zoom + viewState.panX;
    }

    if (viewState.logY && bounds.yMin > 0) {
      const logYMin = Math.log10(bounds.yMin);
      const logYMax = Math.log10(bounds.yMax);
      const logY = Math.log10(y);
      var screenY = margin.top + plotHeight - ((logY - logYMin) / (logYMax - logYMin)) * plotHeight * viewState.zoom + viewState.panY;
    } else {
      var screenY = margin.top + plotHeight - ((y - bounds.yMin) / yRange) * plotHeight * viewState.zoom + viewState.panY;
    }

    return { x: screenX, y: screenY };
  }, [bounds, viewState]);

  // Mouse event handlers for professional pan/zoom
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) { // Left click for pan
      setIsDragging(true);
      setDragStart({ x: e.clientX, y: e.clientY });
      e.preventDefault();
    } else if (e.button === 1) { // Middle click for zoom
      setIsZooming(true);
      e.preventDefault();
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging && !isZooming) {
      const deltaX = e.clientX - dragStart.x;
      const deltaY = e.clientY - dragStart.y;

      setViewState(prev => ({
        ...prev,
        panX: prev.panX + deltaX,
        panY: prev.panY + deltaY,
        autoScale: false
      }));

      setDragStart({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setIsZooming(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    setViewState(prev => ({
      ...prev,
      zoom: Math.max(0.1, Math.min(50, prev.zoom * zoomFactor)),
      autoScale: false
    }));
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, show: true });
  };

  const resetView = () => {
    setViewState(prev => ({
      ...prev,
      zoom: 1,
      panX: 0,
      panY: 0,
      autoScale: true
    }));
    setContextMenu(prev => ({ ...prev, show: false }));
  };

  const toggleLogX = () => {
    setViewState(prev => ({ ...prev, logX: !prev.logX }));
    setContextMenu(prev => ({ ...prev, show: false }));
  };

  const toggleLogY = () => {
    setViewState(prev => ({ ...prev, logY: !prev.logY }));
    setContextMenu(prev => ({ ...prev, show: false }));
  };

  // Close context menu on click outside
  React.useEffect(() => {
    const handleClick = () => setContextMenu(prev => ({ ...prev, show: false }));
    if (contextMenu.show) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [contextMenu.show]);

  // Render 2D data to canvas
  React.useEffect(() => {
    if (type === '2d' && Array.isArray(data) && data.length > 0 && canvasRef.current) {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const imageData = data as number[][];
      const width = imageData[0]?.length || 256;
      const height = imageData.length;

      canvas.width = width;
      canvas.height = height;

      const imgData = ctx.createImageData(width, height);
      const pixels = imgData.data;
      const maxVal = Math.max(...imageData.flat());

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const i = (y * width + x) * 4;
          const normalized = imageData[y][x] / maxVal;

          // Enhanced colormap
          let r, g, b;
          if (colormap === 'viridis') {
            r = Math.floor(255 * (0.267004 + 0.329415 * normalized + 0.518077 * normalized * normalized));
            g = Math.floor(255 * (0.004874 + 0.731456 * normalized - 0.123456 * normalized * normalized));
            b = Math.floor(255 * (0.329415 + 0.267004 * normalized + 0.789654 * normalized * normalized));
          } else if (colormap === 'plasma') {
            r = Math.floor(255 * normalized);
            g = Math.floor(255 * Math.pow(normalized, 1.5));
            b = Math.floor(255 * Math.pow(normalized, 0.5));
          } else { // grayscale
            r = g = b = Math.floor(255 * normalized);
          }

          pixels[i] = r;
          pixels[i + 1] = g;
          pixels[i + 2] = b;
          pixels[i + 3] = 255;
        }
      }

      ctx.putImageData(imgData, 0, 0);
    }
  }, [data, colormap, type]);

  if (type === '2d') {
    return (
      <div ref={containerRef} className={`relative bg-gray-900 text-white h-full flex flex-col ${className}`}>
        {/* Toolbar for 2D plots */}
        {showToolbar && (
          <div className="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-700">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium">{title || 'Image'}</span>
            </div>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setViewState(prev => ({ ...prev, zoom: Math.min(10, prev.zoom * 1.2) }))}
                className="p-1 hover:bg-gray-700 rounded"
                title="Zoom In"
              >
                <ZoomIn className="h-3 w-3" />
              </button>
              <button
                onClick={() => setViewState(prev => ({ ...prev, zoom: Math.max(0.1, prev.zoom * 0.8) }))}
                className="p-1 hover:bg-gray-700 rounded"
                title="Zoom Out"
              >
                <ZoomOut className="h-3 w-3" />
              </button>
              <button
                onClick={resetView}
                className="p-1 hover:bg-gray-700 rounded"
                title="Reset View"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
              {onSettingsClick && (
                <button
                  onClick={onSettingsClick}
                  className="p-1 hover:bg-gray-700 rounded"
                  title="Settings"
                >
                  <Settings className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        )}

        {/* 2D Canvas Display */}
        <div className="flex-1 flex items-center justify-center bg-black p-4 overflow-hidden">
          <canvas
            ref={canvasRef}
            className="border border-gray-600"
            style={{
              imageRendering: 'pixelated',
              transform: `scale(${viewState.zoom})`,
              cursor: isDragging ? 'grabbing' : 'grab',
              maxWidth: '100%',
              maxHeight: '100%'
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
            onContextMenu={handleContextMenu}
          />
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`relative bg-gray-900 text-white h-full flex flex-col ${className}`}>
      {/* Professional Plot Area */}
      <div className="flex-1 relative">
        <svg
          ref={svgRef}
          className="w-full h-full"
          style={{ cursor: isDragging ? 'grabbing' : isZooming ? 'crosshair' : 'grab' }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          onContextMenu={handleContextMenu}
        >
          <defs>
            {/* Grid pattern */}
            <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path
                d="M 20 0 L 0 0 0 20"
                fill="none"
                stroke="#374151"
                strokeWidth="0.5"
                opacity={viewState.showGrid ? "0.3" : "0"}
              />
            </pattern>
            {/* Minor grid */}
            <pattern id="minorGrid" width="10" height="10" patternUnits="userSpaceOnUse">
              <path
                d="M 10 0 L 0 0 0 10"
                fill="none"
                stroke="#374151"
                strokeWidth="0.25"
                opacity={viewState.showGrid ? "0.2" : "0"}
              />
            </pattern>
          </defs>

          {/* Background */}
          <rect width="100%" height="100%" fill="#111827" />

          {/* Grid layers */}
          <rect width="100%" height="100%" fill="url(#minorGrid)" />
          <rect width="100%" height="100%" fill="url(#grid)" />

          {/* Axes */}
          <line x1="60" y1="30" x2="60" y2="calc(100% - 50)" stroke="#6B7280" strokeWidth="1" />
          <line x1="60" y1="calc(100% - 50)" x2="calc(100% - 30)" y2="calc(100% - 50)" stroke="#6B7280" strokeWidth="1" />

          {/* Data Plot */}
          {Array.isArray(data) && data.length > 1 && (
            <>
              {/* Filled area under curve */}
              <path
                d={`M 60,calc(100% - 50) ${(data as { x: number; y: number }[]).map((point, i) => {
                  const svgRect = svgRef.current?.getBoundingClientRect();
                  const w = svgRect?.width || 800;
                  const h = svgRect?.height || 400;
                  const { x, y } = transformPoint(point.x, point.y, w, h);
                  return `L ${x},${y}`;
                }).join(' ')} L calc(100% - 30),calc(100% - 50) Z`}
                fill="rgba(59, 130, 246, 0.15)"
                stroke="none"
              />

              {/* Main data line */}
              <polyline
                fill="none"
                stroke="#3B82F6"
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                points={(data as { x: number; y: number }[]).map((point, i) => {
                  const svgRect = svgRef.current?.getBoundingClientRect();
                  const w = svgRect?.width || 800;
                  const h = svgRect?.height || 400;
                  const { x, y } = transformPoint(point.x, point.y, w, h);
                  return `${x},${y}`;
                }).join(' ')}
              />
            </>
          )}

          {/* Axis labels */}
          <text x="30" y="50%" textAnchor="middle" fill="#9CA3AF" fontSize="11"
                transform="rotate(-90, 30, 50%)" className="font-medium">
            {yLabel} {yUnit && `(${yUnit})`}
          </text>
          <text x="50%" y="calc(100% - 15)" textAnchor="middle" fill="#9CA3AF" fontSize="11" className="font-medium">
            {xLabel} {xUnit && `(${xUnit})`}
          </text>

          {/* Title */}
          {title && (
            <text x="50%" y="20" textAnchor="middle" fill="#F9FAFB" fontSize="13" className="font-semibold">
              {title}
            </text>
          )}
        </svg>

        {/* Right-click context menu */}
        {contextMenu.show && (
          <div
            className="absolute bg-gray-800 border border-gray-600 rounded shadow-lg py-1 z-50"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              onClick={resetView}
              className="block w-full px-3 py-1 text-left text-sm text-gray-200 hover:bg-gray-700"
            >
              Reset View
            </button>
            <button
              onClick={() => setViewState(prev => ({ ...prev, showGrid: !prev.showGrid }))}
              className="block w-full px-3 py-1 text-left text-sm text-gray-200 hover:bg-gray-700"
            >
              {viewState.showGrid ? 'Hide' : 'Show'} Grid
            </button>
            <hr className="my-1 border-gray-600" />
            <button
              onClick={toggleLogX}
              className={`block w-full px-3 py-1 text-left text-sm hover:bg-gray-700 ${
                viewState.logX ? 'text-blue-400' : 'text-gray-200'
              }`}
            >
              Log X Axis
            </button>
            <button
              onClick={toggleLogY}
              className={`block w-full px-3 py-1 text-left text-sm hover:bg-gray-700 ${
                viewState.logY ? 'text-blue-400' : 'text-gray-200'
              }`}
            >
              Log Y Axis
            </button>
            {onSettingsClick && (
              <>
                <hr className="my-1 border-gray-600" />
                <button
                  onClick={() => {
                    onSettingsClick();
                    setContextMenu(prev => ({ ...prev, show: false }));
                  }}
                  className="block w-full px-3 py-1 text-left text-sm text-gray-200 hover:bg-gray-700"
                >
                  Plot Settings...
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Number input spinbox component
interface SpinBoxProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  className?: string;
}

function SpinBox({ value, onChange, min, max, step = 1, suffix = "", className = "" }: SpinBoxProps) {
  const handleIncrement = () => {
    const newValue = value + step;
    if (max === undefined || newValue <= max) {
      onChange(newValue);
    }
  };

  const handleDecrement = () => {
    const newValue = value - step;
    if (min === undefined || newValue >= min) {
      onChange(newValue);
    }
  };

  return (
    <div className={`flex items-center bg-gray-700 rounded ${className}`}>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        min={min}
        max={max}
        step={step}
        className="bg-transparent px-2 py-1 text-white text-center border-none outline-none w-20"
      />
      {suffix && (
        <span className="text-gray-400 text-sm px-1">{suffix}</span>
      )}
      <div className="flex flex-col">
        <button
          onClick={handleIncrement}
          className="px-1 py-0.5 hover:bg-gray-600 text-gray-400 text-xs"
        >
          ▲
        </button>
        <button
          onClick={handleDecrement}
          className="px-1 py-0.5 hover:bg-gray-600 text-gray-400 text-xs"
        >
          ▼
        </button>
      </div>
    </div>
  );
}

// Main instrument UI component
function InstrumentUI({ instrument }: { instrument: DashboardInstrument }) {
  if (instrument.kind === 'detector') {
    switch (instrument.dimensionality) {
      case '0D':
        return <Detector0DWindow instrument={instrument} />;
      case '1D':
        return <Detector1DWindow instrument={instrument} />;
      case '2D':
        return <Detector2DWindow instrument={instrument} />;
      default:
        return <div>Unsupported detector type</div>;
    }
  } else if (instrument.kind === 'motor') {
    switch (instrument.dimensionality) {
      case '0D':
        return <Motor0DWindow instrument={instrument} />;
      case '1D':
        return <Motor1DWindow instrument={instrument} />;
      default:
        return <MotorMultiAxisWindow instrument={instrument} />;
    }
  }

  return <div>Unknown instrument type</div>;
}

// 0D Detector - Counter above, full-window graph below (qudi style)
function Detector0DWindow({ instrument }: { instrument: DashboardInstrument }) {
  const [currentValue, setCurrentValue] = React.useState(0);
  const [timeTrace, setTimeTrace] = React.useState<{ x: number; y: number }[]>([]);
  const [isLive, setIsLive] = React.useState(false);
  const [isRecording, setIsRecording] = React.useState(false);
  const [integrationTime, setIntegrationTime] = React.useState(100);
  const [showSettings, setShowSettings] = React.useState(false);

  React.useEffect(() => {
    if (!isLive) return;

    const interval = setInterval(() => {
      const now = Date.now() / 1000; // Convert to seconds
      const newValue = Math.random() * 1000 + Math.sin(now) * 200 + 500;

      setCurrentValue(newValue);

      if (isRecording) {
        setTimeTrace(prev => [...prev.slice(-499), { x: now, y: newValue }]);
      }
    }, integrationTime);

    return () => clearInterval(interval);
  }, [isLive, integrationTime, isRecording]);

  const takeSnapshot = () => {
    const snapshot = Math.random() * 1000 + Math.sin(Date.now() / 1000) * 200 + 500;
    setCurrentValue(snapshot);

    if (isRecording) {
      const now = Date.now() / 1000;
      setTimeTrace(prev => [...prev.slice(-499), { x: now, y: snapshot }]);
    }
  };

  return (
    <div className="h-screen bg-gray-900 flex flex-col">
      {/* Top counter bar */}
      <div className="bg-gray-800 px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center space-x-6">
          {/* Counter Display */}
          <div className="text-center">
            <div className="text-4xl font-mono font-bold text-blue-400">
              {currentValue.toFixed(0)}
            </div>
            <div className="text-sm text-gray-400">counts/s</div>
          </div>

          {/* Controls */}
          <div className="flex items-center space-x-3">
            <button
              onClick={takeSnapshot}
              className="p-2 bg-blue-600 hover:bg-blue-700 rounded transition-colors"
              title="Single Shot"
            >
              <Play className="h-4 w-4" />
            </button>
            <button
              onClick={() => setIsLive(!isLive)}
              className={`p-2 rounded transition-colors ${
                isLive
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-green-600 hover:bg-green-700'
              }`}
              title={isLive ? 'Stop Live' : 'Start Live'}
            >
              {isLive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button
              onClick={() => setIsRecording(!isRecording)}
              className={`p-2 rounded transition-colors ${
                isRecording
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-orange-600 hover:bg-orange-700'
              }`}
              title={isRecording ? 'Stop Recording' : 'Start Recording'}
            >
              <div className={`w-3 h-3 rounded-full ${isRecording ? 'bg-white' : 'bg-white'}`} />
            </button>
          </div>
        </div>

        {/* Settings */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <label className="text-gray-300 text-sm">Integration:</label>
            <SpinBox
              value={integrationTime}
              onChange={setIntegrationTime}
              min={10}
              max={5000}
              step={10}
              suffix="ms"
            />
          </div>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 hover:bg-gray-700 rounded"
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Full-window time trace graph */}
      <div className="flex-1">
        <PyQtGraphPlot
          data={timeTrace}
          title="Time Trace"
          xLabel="Time"
          yLabel="Intensity"
          xUnit="s"
          yUnit="counts/s"
          className="h-full"
          showToolbar={false}
          onSettingsClick={() => setShowSettings(true)}
        />
      </div>
    </div>
  );
}

// 1D Detector - pyMoDAQ spectrometer style
function Detector1DWindow({ instrument }: { instrument: DashboardInstrument }) {
  const [spectrumData, setSpectrumData] = React.useState<{ x: number; y: number }[]>([]);
  const [isLive, setIsLive] = React.useState(false);
  const [integrationTime, setIntegrationTime] = React.useState(100);
  const [showSettings, setShowSettings] = React.useState(false);
  const [pixels, setPixels] = React.useState(1024);

  // Generate realistic spectrum data with proper wavelength axis
  const generateSpectrum = React.useCallback(() => {
    const newSpectrum = Array.from({ length: pixels }, (_, i) => {
      const wavelength = 400 + (i / pixels) * 400; // 400-800nm range

      // Base noise
      let intensity = Math.random() * 50 + 10;

      // Add multiple realistic peaks
      const peak1 = 500 * Math.exp(-0.5 * Math.pow((wavelength - 500) / 30, 2)); // Sharp peak at 500nm
      const peak2 = 300 * Math.exp(-0.5 * Math.pow((wavelength - 600) / 50, 2)); // Broader peak at 600nm
      const peak3 = 200 * Math.exp(-0.5 * Math.pow((wavelength - 700) / 20, 2)); // Small peak at 700nm

      // Add background slope
      const background = (wavelength - 400) * 0.1;

      intensity += peak1 + peak2 + peak3 + background;

      return {
        x: wavelength,
        y: Math.max(0, intensity)
      };
    });

    setSpectrumData(newSpectrum);
  }, [pixels]);

  React.useEffect(() => {
    generateSpectrum();
  }, [generateSpectrum]);

  React.useEffect(() => {
    if (!isLive) return;

    const interval = setInterval(() => {
      generateSpectrum();
    }, integrationTime);

    return () => clearInterval(interval);
  }, [isLive, integrationTime, generateSpectrum]);

  const takeSnapshot = () => {
    generateSpectrum();
  };

  return (
    <div className="h-screen bg-gray-900 flex flex-col">
      {/* Top toolbar */}
      <div className="bg-gray-800 px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          {/* Acquisition Controls */}
          <div className="flex items-center space-x-2">
            <button
              onClick={takeSnapshot}
              className="p-2 bg-blue-600 hover:bg-blue-700 rounded transition-colors"
              title="Single Shot"
            >
              <Play className="h-4 w-4" />
            </button>
            <button
              onClick={() => setIsLive(!isLive)}
              className={`p-2 rounded transition-colors ${
                isLive
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-green-600 hover:bg-green-700'
              }`}
              title={isLive ? 'Stop Live' : 'Start Live'}
            >
              {isLive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
          </div>

          {/* Integration Time */}
          <div className="flex items-center space-x-2">
            <label className="text-gray-300 text-sm">Integration:</label>
            <SpinBox
              value={integrationTime}
              onChange={setIntegrationTime}
              min={1}
              max={10000}
              step={1}
              suffix="ms"
            />
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-gray-400 text-sm">
            Max: {spectrumData.length > 0 ? Math.max(...spectrumData.map(d => d.y)).toFixed(0) : 0} counts
          </div>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 hover:bg-gray-700 rounded"
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="bg-gray-800 px-4 py-3 border-b border-gray-700">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <label className="text-gray-300 text-sm">Pixels:</label>
              <select
                value={pixels}
                onChange={(e) => setPixels(parseInt(e.target.value))}
                className="bg-gray-700 text-white px-2 py-1 rounded text-sm"
              >
                <option value={256}>256</option>
                <option value={512}>512</option>
                <option value={1024}>1024</option>
                <option value={2048}>2048</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Full-screen spectrum graph */}
      <div className="flex-1">
        <PyQtGraphPlot
          data={spectrumData}
          title="Live Spectrum"
          xLabel="Wavelength"
          yLabel="Intensity"
          xUnit="nm"
          yUnit="counts"
          className="h-full"
          showToolbar={false}
          onSettingsClick={() => setShowSettings(true)}
        />
      </div>
    </div>
  );
}

// 2D Detector - Full window image with toolbar
function Detector2DWindow({ instrument }: { instrument: DashboardInstrument }) {
  const [imageData, setImageData] = React.useState<number[][]>([]);
  const [isLive, setIsLive] = React.useState(false);
  const [exposureTime, setExposureTime] = React.useState(100);
  const [showSettings, setShowSettings] = React.useState(false);
  const [resolution, setResolution] = React.useState({ width: 256, height: 256 });

  const generateImage = React.useCallback(() => {
    const newImage = Array.from({ length: resolution.height }, (_, y) =>
      Array.from({ length: resolution.width }, (_, x) => {
        const centerX = resolution.width / 2;
        const centerY = resolution.height / 2;
        const distance = Math.sqrt((x - centerX) ** 2 + (y - centerY) ** 2);

        let intensity = 100 + Math.random() * 50;

        // Add multiple features
        intensity += 500 * Math.exp(-distance / 40); // Central gaussian
        intensity += 200 * Math.sin(x / 15) * Math.sin(y / 15); // Interference pattern
        intensity += 100 * Math.exp(-Math.pow(x - 0.7*resolution.width, 2) / 400) * Math.exp(-Math.pow(y - 0.3*resolution.height, 2) / 400); // Secondary spot

        return Math.max(0, intensity);
      })
    );
    setImageData(newImage);
  }, [resolution]);

  React.useEffect(() => {
    generateImage();
  }, [generateImage]);

  React.useEffect(() => {
    if (!isLive) return;

    const interval = setInterval(() => {
      generateImage();
    }, exposureTime);

    return () => clearInterval(interval);
  }, [isLive, exposureTime, generateImage]);

  const takeSnapshot = () => {
    generateImage();
  };

  return (
    <div className="h-screen bg-gray-900 flex flex-col">
      {/* Top toolbar */}
      <div className="bg-gray-800 px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          {/* Acquisition Controls */}
          <div className="flex items-center space-x-2">
            <button
              onClick={takeSnapshot}
              className="p-2 bg-blue-600 hover:bg-blue-700 rounded transition-colors"
              title="Single Shot"
            >
              <Play className="h-4 w-4" />
            </button>
            <button
              onClick={() => setIsLive(!isLive)}
              className={`p-2 rounded transition-colors ${
                isLive
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-green-600 hover:bg-green-700'
              }`}
              title={isLive ? 'Stop Live' : 'Start Live'}
            >
              {isLive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
          </div>

          {/* Exposure Time */}
          <div className="flex items-center space-x-2">
            <label className="text-gray-300 text-sm">Exposure:</label>
            <SpinBox
              value={exposureTime}
              onChange={setExposureTime}
              min={1}
              max={10000}
              step={1}
              suffix="ms"
            />
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-gray-400 text-sm">
            {resolution.width}×{resolution.height} • Max: {imageData.length > 0 ? Math.max(...imageData.flat()).toFixed(0) : 0}
          </div>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 hover:bg-gray-700 rounded"
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="bg-gray-800 px-4 py-3 border-b border-gray-700">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <label className="text-gray-300 text-sm">Resolution:</label>
              <select
                value={`${resolution.width}x${resolution.height}`}
                onChange={(e) => {
                  const [w, h] = e.target.value.split('x').map(Number);
                  setResolution({ width: w, height: h });
                }}
                className="bg-gray-700 text-white px-2 py-1 rounded text-sm"
              >
                <option value="128x128">128×128</option>
                <option value="256x256">256×256</option>
                <option value="512x512">512×512</option>
                <option value="1024x1024">1024×1024</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Full-window image display */}
      <div className="flex-1">
        <PyQtGraphPlot
          data={imageData}
          type="2d"
          title="Live Image"
          className="h-full"
          showToolbar={false}
          onSettingsClick={() => setShowSettings(true)}
        />
      </div>
    </div>
  );
}

// 0D Motor - State switches/buttons (dropdown for multiple states)
function Motor0DWindow({ instrument }: { instrument: DashboardInstrument }) {
  const [currentState, setCurrentState] = React.useState<string>('OFF');

  // Simulate different state options based on motor type
  const availableStates = ['OFF', 'ON', 'STANDBY', 'LOCKED'];

  return (
    <div className="h-screen bg-gray-900 flex items-center justify-center">
      <div className="bg-gray-800 rounded-lg p-12 text-center max-w-md">
        <div className="text-4xl font-bold text-white mb-8">{instrument.name}</div>

        {/* Current State Display */}
        <div className="mb-8">
          <div className="text-lg text-gray-400 mb-2">Current State</div>
          <div className={`text-3xl font-bold mb-6 ${
            currentState === 'ON' ? 'text-green-400' :
            currentState === 'STANDBY' ? 'text-yellow-400' :
            currentState === 'LOCKED' ? 'text-red-400' : 'text-gray-400'
          }`}>
            {currentState}
          </div>
        </div>

        {/* State Controls */}
        <div className="space-y-4">
          {availableStates.map((state) => (
            <button
              key={state}
              onClick={() => setCurrentState(state)}
              className={`w-full px-6 py-3 rounded-lg font-medium transition-colors ${
                currentState === state
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              {state}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// 1D Motor - Merged frames, position on top, real-time slider
function Motor1DWindow({ instrument }: { instrument: DashboardInstrument }) {
  const [position, setPosition] = React.useState(50.0);
  const [targetPosition, setTargetPosition] = React.useState(50.0);
  const [isMoving, setIsMoving] = React.useState(false);
  const [isHoming, setIsHoming] = React.useState(false);
  const [realtimeSlider, setRealtimeSlider] = React.useState(true);
  const [showSettings, setShowSettings] = React.useState(false);

  // Real-time slider movement
  React.useEffect(() => {
    if (realtimeSlider && !isMoving) {
      setPosition(targetPosition);
    }
  }, [targetPosition, realtimeSlider, isMoving]);

  const handleMove = () => {
    if (isMoving) return;

    setIsMoving(true);
    const startPos = position;
    const endPos = targetPosition;
    const startTime = Date.now();
    const duration = Math.abs(endPos - startPos) * 100;

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

  const handleHome = () => {
    setIsHoming(true);
    setTargetPosition(0);

    setTimeout(() => {
      setPosition(0);
      setIsHoming(false);
    }, 2000);
  };

  const stopMotion = () => {
    setIsMoving(false);
    setIsHoming(false);
  };

  return (
    <div className="h-screen bg-gray-900 p-6">
      <div className="h-full bg-gray-800 rounded-lg p-6">
        {/* Current Position Display (Top) */}
        <div className="text-center mb-8">
          <div className="text-lg text-gray-400 mb-2">Current Position</div>
          <div className="flex items-center justify-center space-x-2">
            <div className="text-6xl font-mono font-bold text-blue-400">
              {position.toFixed(3)}
            </div>
            <div className="text-2xl text-gray-400">mm</div>
          </div>
          <div className={`text-lg mt-2 ${
            isMoving ? 'text-blue-400' : isHoming ? 'text-yellow-400' : 'text-green-400'
          }`}>
            {isMoving ? '⚡ Moving...' : isHoming ? '🏠 Homing...' : '✅ Ready'}
          </div>
        </div>

        {/* Control Section */}
        <div className="space-y-6">
          {/* Target Position Input */}
          <div className="flex items-center space-x-4">
            <label className="text-gray-300 text-lg w-32">Target Position:</label>
            <input
              type="number"
              value={targetPosition}
              onChange={(e) => setTargetPosition(parseFloat(e.target.value) || 0)}
              className="flex-1 px-4 py-2 text-xl bg-gray-700 text-white rounded border-gray-600"
              step="0.001"
            />
            <span className="text-lg text-gray-400">mm</span>
          </div>

          {/* Control Buttons */}
          <div className="flex items-center justify-center space-x-4">
            <button
              onClick={handleHome}
              disabled={isMoving || isHoming}
              className="p-3 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white rounded-lg"
              title="Home Motor"
            >
              <Home className="h-5 w-5" />
            </button>
            <button
              onClick={handleMove}
              disabled={isMoving || isHoming}
              className="p-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white rounded-lg"
              title="Move to Position"
            >
              <SkipForward className="h-5 w-5" />
            </button>
            <button
              onClick={stopMotion}
              disabled={!isMoving && !isHoming}
              className="p-3 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white rounded-lg"
              title="Stop Motion"
            >
              <Square className="h-5 w-5" />
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-3 bg-gray-600 hover:bg-gray-500 text-white rounded-lg"
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </button>
          </div>

          {/* Position Slider */}
          <div className="space-y-3">
            <div className="flex justify-between text-gray-400">
              <span>0 mm</span>
              <span>100 mm</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="0.001"
              value={targetPosition}
              onChange={(e) => setTargetPosition(parseFloat(e.target.value))}
              className="w-full h-3 bg-gray-700 rounded-lg appearance-none cursor-pointer"
              disabled={isMoving || isHoming}
            />
            <div className="text-center text-sm text-gray-400">
              Real-time slider: {realtimeSlider ? 'ON' : 'OFF'}
              {!realtimeSlider && !isMoving && (
                <span className="ml-2 text-orange-400">(Click Move to apply)</span>
              )}
            </div>
          </div>

          {/* Settings Panel */}
          {showSettings && (
            <div className="bg-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <label className="text-gray-300">Real-time Slider Movement:</label>
                <button
                  onClick={() => setRealtimeSlider(!realtimeSlider)}
                  className={`px-3 py-1 rounded text-sm ${
                    realtimeSlider ? 'bg-green-600' : 'bg-gray-600'
                  }`}
                >
                  {realtimeSlider ? 'ON' : 'OFF'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Multi-axis Motor - Individual cards for each axis in grid
function MotorMultiAxisWindow({ instrument }: { instrument: DashboardInstrument }) {
  const numAxes = parseInt(instrument.dimensionality[0]) || 2;
  const [positions, setPositions] = React.useState<number[]>(Array(numAxes).fill(50));
  const [targetPositions, setTargetPositions] = React.useState<number[]>(Array(numAxes).fill(50));
  const [isMoving, setIsMoving] = React.useState<boolean[]>(Array(numAxes).fill(false));

  const axisLabels = ['X', 'Y', 'Z', 'U', 'V', 'W'];

  const moveAxis = (axisIndex: number) => {
    const newIsMoving = [...isMoving];
    newIsMoving[axisIndex] = true;
    setIsMoving(newIsMoving);

    // Simulate movement
    setTimeout(() => {
      const newPositions = [...positions];
      newPositions[axisIndex] = targetPositions[axisIndex];
      setPositions(newPositions);

      const finalIsMoving = [...newIsMoving];
      finalIsMoving[axisIndex] = false;
      setIsMoving(finalIsMoving);
    }, 1500);
  };

  const homeAxis = (axisIndex: number) => {
    const newTargetPositions = [...targetPositions];
    newTargetPositions[axisIndex] = 0;
    setTargetPositions(newTargetPositions);
    moveAxis(axisIndex);
  };

  return (
    <div className="h-screen bg-gray-900 p-4">
      {/* Grid of axis cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 h-full">
        {Array.from({ length: numAxes }).map((_, i) => (
          <div key={i} className="bg-gray-800 rounded-lg p-6 flex flex-col">
            {/* Axis Header */}
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-white mb-2">
                {axisLabels[i]} Axis
              </h3>
              <div className={`text-sm ${isMoving[i] ? 'text-blue-400' : 'text-green-400'}`}>
                {isMoving[i] ? '⚡ Moving' : '✅ Ready'}
              </div>
            </div>

            {/* Current & Target Position in single card */}
            <div className="bg-gray-700 rounded-lg p-4 mb-6">
              <div className="grid grid-cols-2 gap-4 text-center">
                <div>
                  <div className="text-sm text-gray-400 mb-1">Current</div>
                  <div className="text-2xl font-mono font-bold text-blue-400">
                    {positions[i].toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-400">mm</div>
                </div>
                <div>
                  <div className="text-sm text-gray-400 mb-1">Target</div>
                  <div className="text-2xl font-mono font-bold text-orange-400">
                    {targetPositions[i].toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-400">mm</div>
                </div>
              </div>
            </div>

            {/* Controls */}
            <div className="flex-1 space-y-4">
              <div className="flex items-center space-x-2">
                <input
                  type="number"
                  value={targetPositions[i]}
                  onChange={(e) => {
                    const newTargets = [...targetPositions];
                    newTargets[i] = parseFloat(e.target.value) || 0;
                    setTargetPositions(newTargets);
                  }}
                  className="flex-1 px-2 py-1 bg-gray-600 text-white rounded"
                  step="0.01"
                />
                <span className="text-gray-400 text-sm">mm</span>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => homeAxis(i)}
                  disabled={isMoving[i]}
                  className="p-2 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white rounded flex-1"
                  title="Home"
                >
                  <Home className="h-4 w-4 mx-auto" />
                </button>
                <button
                  onClick={() => moveAxis(i)}
                  disabled={isMoving[i]}
                  className="p-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white rounded flex-1"
                  title="Move"
                >
                  <SkipForward className="h-4 w-4 mx-auto" />
                </button>
                <button
                  disabled={!isMoving[i]}
                  className="p-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white rounded flex-1"
                  title="Stop"
                >
                  <Square className="h-4 w-4 mx-auto" />
                </button>
              </div>

              <input
                type="range"
                min="0"
                max="100"
                step="0.1"
                value={targetPositions[i]}
                onChange={(e) => {
                  const newTargets = [...targetPositions];
                  newTargets[i] = parseFloat(e.target.value);
                  setTargetPositions(newTargets);
                }}
                className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer"
                disabled={isMoving[i]}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}