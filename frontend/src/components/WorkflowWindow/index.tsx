import React from 'react';
import { DashboardWorkflow, DashboardInstrument } from '@/api';
import { Activity, Play, Square, Download, RefreshCw } from 'lucide-react';

// This component will be rendered in separate browser windows
export function WorkflowWindowContent() {
  // Get workflow data from URL params or localStorage
  const getWorkflowData = (): { workflow: DashboardWorkflow; instruments: DashboardInstrument[] } | null => {
    try {
      const params = new URLSearchParams(window.location.search);
      const workflowData = params.get('data');
      if (workflowData) {
        return JSON.parse(decodeURIComponent(workflowData));
      }

      // Fallback to localStorage
      const stored = localStorage.getItem('workflowWindowData');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  };

  const data = getWorkflowData();

  if (!data) {
    return (
      <div className="p-8 text-center">
        <div className="text-red-600 mb-4">Failed to load workflow data</div>
        <button onClick={() => window.close()} className="px-4 py-2 bg-gray-600 text-white rounded">
          Close Window
        </button>
      </div>
    );
  }

  const { workflow, instruments } = data;

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
        <div className="flex items-center justify-between mb-6 border-b pb-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              {workflow.name}
            </h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {workflow.workflow_type.replace('_', ' ')} workflow
            </p>
          </div>
          <button
            onClick={() => window.close()}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md"
          >
            Close Window
          </button>
        </div>

        <WorkflowUI workflow={workflow} instruments={instruments} />
      </div>
    </div>
  );
}

// Main workflow UI component
function WorkflowUI({ workflow, instruments }: { workflow: DashboardWorkflow; instruments: DashboardInstrument[] }) {
  const [isExecuting, setIsExecuting] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [currentStep, setCurrentStep] = React.useState('Ready');
  const [workflowData, setWorkflowData] = React.useState<any[]>([]);

  // Get connected instruments
  const connectedInsts = workflow.connected_instruments
    .map(instId => instruments.find(i => i.id === instId))
    .filter(Boolean) as DashboardInstrument[];

  // Simulate workflow execution
  const handleExecute = async () => {
    setIsExecuting(true);
    setProgress(0);
    setCurrentStep('Initializing...');

    // Simulate progress
    const steps = [
      'Initializing instruments...',
      'Starting acquisition...',
      'Collecting data...',
      'Processing results...',
      'Complete!'
    ];

    for (let i = 0; i < steps.length; i++) {
      setCurrentStep(steps[i]);

      // Simulate gradual progress within each step
      for (let j = 0; j <= 20; j++) {
        await new Promise(resolve => setTimeout(resolve, 100));
        setProgress((i * 20) + j);

        // Generate mock data during execution
        if (i >= 2) { // Start generating data at step 3
          generateMockData();
        }
      }
    }

    setIsExecuting(false);
  };

  const generateMockData = () => {
    if (workflow.workflow_type === 'confocal_scan') {
      const size = 25;
      const newData = Array.from({ length: size * size }, (_, i) => {
        const x = i % size;
        const y = Math.floor(i / size);
        const centerX = size / 2;
        const centerY = size / 2;
        const distance = Math.sqrt((x - centerX) ** 2 + (y - centerY) ** 2);
        const intensity = 1000 * Math.exp(-distance / 8) + Math.random() * 100;
        return { x, y, intensity };
      });
      setWorkflowData(newData);
    } else if (workflow.workflow_type === 'transient_absorption') {
      const wavelengths = Array.from({ length: 50 }, (_, i) => 400 + i * 8);
      const delays = Array.from({ length: 20 }, (_, i) => i * 0.5);
      const newData = wavelengths.flatMap(wavelength =>
        delays.map(delay => {
          const signal = Math.sin((wavelength - 500) / 50) * Math.exp(-delay / 2) + Math.random() * 0.1;
          return { wavelength, delay, absorption: signal };
        })
      );
      setWorkflowData(newData);
    }
  };

  const renderVisualization = () => {
    if (workflowData.length === 0) {
      return (
        <div className="h-96 bg-white dark:bg-gray-800 rounded border flex items-center justify-center">
          <div className="text-center text-gray-500">
            <Activity className="h-8 w-8 mx-auto mb-2" />
            <div>Execute workflow to see results</div>
          </div>
        </div>
      );
    }

    if (workflow.workflow_type === 'confocal_scan') {
      const size = 25;
      const maxIntensity = Math.max(...workflowData.map(d => d.intensity));

      return (
        <div className="space-y-4">
          <h4 className="font-medium text-gray-900 dark:text-white">Confocal Scan Results</h4>
          <div className="bg-white dark:bg-gray-800 rounded border p-4">
            <div className="grid gap-0.5" style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }}>
              {workflowData.map((point, i) => (
                <div
                  key={i}
                  className="aspect-square"
                  style={{
                    backgroundColor: `rgba(59, 130, 246, ${point.intensity / maxIntensity})`,
                  }}
                  title={`(${point.x}, ${point.y}): ${point.intensity.toFixed(0)}`}
                />
              ))}
            </div>
            <div className="mt-4 text-xs text-gray-600 dark:text-gray-400 text-center">
              {size}×{size} scan, max intensity: {maxIntensity.toFixed(0)} counts
            </div>
          </div>
        </div>
      );
    } else if (workflow.workflow_type === 'transient_absorption') {
      return (
        <div className="space-y-4">
          <h4 className="font-medium text-gray-900 dark:text-white">Transient Absorption Results</h4>
          <div className="bg-white dark:bg-gray-800 rounded border p-4">
            <div className="h-64 bg-gradient-to-br from-red-200 via-yellow-200 to-blue-200 dark:from-red-800 dark:via-yellow-800 dark:to-blue-800 rounded relative">
              <div className="absolute inset-0 bg-black bg-opacity-20 rounded"></div>
              <div className="absolute top-2 left-2 text-xs bg-white dark:bg-gray-800 px-2 py-1 rounded">
                ΔA Surface (λ × delay)
              </div>
              <div className="absolute bottom-2 right-2 text-xs bg-white dark:bg-gray-800 px-2 py-1 rounded">
                {workflowData.length} data points
              </div>
            </div>
          </div>
        </div>
      );
    }

    return <div>Unknown workflow type</div>;
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left Column - Controls & Status */}
      <div className="space-y-6">
        {/* Status */}
        <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
          <h3 className="font-medium text-gray-900 dark:text-white mb-4">Status</h3>
          <div className="space-y-3">
            <div className={`text-lg font-medium ${
              isExecuting ? 'text-blue-600' : 'text-green-600'
            }`}>
              {isExecuting ? 'Running' : 'Ready'}
            </div>

            {isExecuting && (
              <div>
                <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                  <span>Progress</span>
                  <span>{progress}%</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                  {currentStep}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
          <h3 className="font-medium text-gray-900 dark:text-white mb-4">Controls</h3>
          <div className="space-y-3">
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className={`w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-lg font-medium transition-colors ${
                isExecuting
                  ? 'bg-gray-400 text-white cursor-not-allowed'
                  : 'bg-green-600 hover:bg-green-700 text-white'
              }`}
            >
              <Play className="h-4 w-4" />
              <span>{isExecuting ? 'Running...' : 'Execute Workflow'}</span>
            </button>

            {isExecuting && (
              <button
                onClick={() => {
                  setIsExecuting(false);
                  setProgress(0);
                  setCurrentStep('Stopped');
                }}
                className="w-full flex items-center justify-center space-x-2 px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
              >
                <Square className="h-4 w-4" />
                <span>Stop</span>
              </button>
            )}

            <button className="w-full flex items-center justify-center space-x-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
              <RefreshCw className="h-4 w-4" />
              <span>Refresh</span>
            </button>

            {workflowData.length > 0 && (
              <button className="w-full flex items-center justify-center space-x-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors">
                <Download className="h-4 w-4" />
                <span>Export Data</span>
              </button>
            )}
          </div>
        </div>

        {/* Connected Instruments */}
        <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
          <h3 className="font-medium text-gray-900 dark:text-white mb-4">Connected Instruments</h3>
          <div className="space-y-3">
            {connectedInsts.map(inst => (
              <div key={inst.id} className="bg-white dark:bg-gray-800 p-3 rounded border">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                    {inst.name}
                  </div>
                  <div className={`w-2 h-2 rounded-full ${
                    inst.connected ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                  {inst.dimensionality} {inst.kind}
                </div>

                {/* Mock real-time indicators */}
                {inst.dimensionality === '0D' && (
                  <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                    <div className="text-sm font-mono text-blue-600 dark:text-blue-400">
                      {(Math.random() * 1000 + 500).toFixed(0)} cts/s
                    </div>
                  </div>
                )}

                {inst.dimensionality === '1D' && (
                  <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                    <div className="h-4 bg-blue-200 dark:bg-blue-800 rounded relative overflow-hidden">
                      <div className="absolute inset-0.5 bg-blue-600 rounded animate-pulse" style={{width: '70%'}} />
                    </div>
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Acquiring</div>
                  </div>
                )}

                {inst.dimensionality === '2D' && (
                  <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                    <div className="h-4 bg-gradient-to-r from-gray-300 to-blue-300 dark:from-gray-600 dark:to-blue-600 rounded" />
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Exposing</div>
                  </div>
                )}

                {inst.kind === 'motor' && (
                  <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-600 dark:text-gray-400">Pos:</span>
                      <span className="font-mono text-gray-900 dark:text-white">
                        {(Math.random() * 100).toFixed(2)} mm
                      </span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Columns - Visualization */}
      <div className="lg:col-span-2">
        <div className="bg-gray-50 dark:bg-gray-700 p-6 rounded-lg h-full">
          <h3 className="font-medium text-gray-900 dark:text-white mb-6">Live Results</h3>
          {renderVisualization()}
        </div>
      </div>
    </div>
  );
}