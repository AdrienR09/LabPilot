import React, { useState, useEffect } from 'react';
import { FloatingWindow } from '@/components/FloatingWindow';
import { DashboardWorkflow, DashboardInstrument, executeDashboardWorkflow, stopDashboardWorkflow } from '@/api';
import { Activity, Play, Square, Download, RefreshCw, BarChart3 } from 'lucide-react';

interface WorkflowControlWindowProps {
  workflow: DashboardWorkflow;
  instruments: DashboardInstrument[];
  isOpen: boolean;
  onClose: () => void;
}

export function WorkflowControlWindow({ workflow, instruments, isOpen, onClose }: WorkflowControlWindowProps) {
  const [workflowProgress, setWorkflowProgress] = useState(0);
  const [isExecuting, setIsExecuting] = useState(false);
  const [workflowData, setWorkflowData] = useState<any[]>([]);
  const [currentStep, setCurrentStep] = useState('Ready');

  // Get connected instruments for this workflow
  const connectedInsts = workflow.connected_instruments
    .map(instId => instruments.find(i => i.id === instId))
    .filter(Boolean) as DashboardInstrument[];

  // Simulate workflow progress
  useEffect(() => {
    if (!workflow.running || !isExecuting) return;

    const interval = setInterval(() => {
      setWorkflowProgress(prev => {
        const newProgress = Math.min(prev + Math.random() * 10, 100);

        // Update current step based on progress
        if (workflow.workflow_type === 'confocal_scan') {
          if (newProgress < 25) setCurrentStep('Initializing scanner...');
          else if (newProgress < 50) setCurrentStep('Scanning area (25x25 grid)...');
          else if (newProgress < 75) setCurrentStep('Collecting photon counts...');
          else if (newProgress < 100) setCurrentStep('Processing data...');
          else setCurrentStep('Complete!');
        } else if (workflow.workflow_type === 'transient_absorption') {
          if (newProgress < 20) setCurrentStep('Calibrating delay stage...');
          else if (newProgress < 60) setCurrentStep('Scanning pump-probe delays...');
          else if (newProgress < 80) setCurrentStep('Recording spectra...');
          else if (newProgress < 100) setCurrentStep('Analyzing transients...');
          else setCurrentStep('Complete!');
        }

        return newProgress;
      });
    }, 500);

    return () => clearInterval(interval);
  }, [workflow.running, isExecuting, workflow.workflow_type]);

  // Generate mock workflow-specific visualizations
  useEffect(() => {
    if (!workflow.running) return;

    const interval = setInterval(() => {
      if (workflow.workflow_type === 'confocal_scan') {
        // Generate confocal scan data
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
        // Generate transient absorption data
        const wavelengths = Array.from({ length: 50 }, (_, i) => 400 + i * 8); // 400-800nm
        const delays = Array.from({ length: 20 }, (_, i) => i * 0.5); // 0-10ps

        const newData = wavelengths.flatMap(wavelength =>
          delays.map(delay => {
            const signal = Math.sin((wavelength - 500) / 50) * Math.exp(-delay / 2) + Math.random() * 0.1;
            return { wavelength, delay, absorption: signal };
          })
        );
        setWorkflowData(newData);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [workflow.running, workflow.workflow_type]);

  const handleExecute = async () => {
    try {
      setIsExecuting(true);
      setWorkflowProgress(0);
      setCurrentStep('Starting workflow...');
      await executeDashboardWorkflow(workflow.id);
    } catch (error) {
      console.error('Failed to execute workflow:', error);
      setIsExecuting(false);
    }
  };

  const handleStop = async () => {
    try {
      await stopDashboardWorkflow(workflow.id);
      setIsExecuting(false);
      setWorkflowProgress(0);
      setCurrentStep('Stopped');
    } catch (error) {
      console.error('Failed to stop workflow:', error);
    }
  };

  const renderWorkflowVisualization = () => {
    if (workflowData.length === 0) {
      return (
        <div className="h-64 bg-white dark:bg-gray-800 rounded border flex items-center justify-center">
          <div className="text-center text-gray-500">
            <Activity className="h-8 w-8 mx-auto mb-2" />
            <div>Start workflow to see visualization</div>
          </div>
        </div>
      );
    }

    if (workflow.workflow_type === 'confocal_scan') {
      const size = 25;
      const maxIntensity = Math.max(...workflowData.map(d => d.intensity));

      return (
        <div className="h-64 bg-white dark:bg-gray-800 rounded border p-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
            Confocal Scan Map
          </h4>
          <div className="grid grid-cols-25 gap-0.5" style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }}>
            {workflowData.map((point, i) => (
              <div
                key={i}
                className="aspect-square"
                style={{
                  backgroundColor: `rgba(59, 130, 246, ${point.intensity / maxIntensity})`,
                }}
                title={`Position: (${point.x}, ${point.y}), Intensity: ${point.intensity.toFixed(0)}`}
              />
            ))}
          </div>
        </div>
      );

    } else if (workflow.workflow_type === 'transient_absorption') {
      return (
        <div className="h-64 bg-white dark:bg-gray-800 rounded border p-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
            Transient Absorption Surface
          </h4>
          <div className="h-48 bg-gradient-to-br from-red-200 via-yellow-200 to-blue-200 dark:from-red-800 dark:via-yellow-800 dark:to-blue-800 rounded relative">
            <div className="absolute inset-0 bg-black bg-opacity-20 rounded"></div>
            <div className="absolute top-2 left-2 text-xs text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 px-2 py-1 rounded">
              ΔA (wavelength × delay)
            </div>
            <div className="absolute bottom-2 right-2 text-xs text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 px-2 py-1 rounded">
              {workflowData.length} data points
            </div>
          </div>
        </div>
      );
    }

    return <div>Unknown workflow type</div>;
  };

  const renderConnectedInstruments = () => {
    return (
      <div className="space-y-3">
        {connectedInsts.map(inst => (
          <div key={inst.id} className="bg-white dark:bg-gray-800 p-3 rounded border">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-medium text-gray-900 dark:text-white">
                {inst.name}
              </h4>
              <div className={`w-2 h-2 rounded-full ${
                inst.connected ? 'bg-green-500' : 'bg-red-500'
              }`} />
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
              {inst.dimensionality} {inst.kind} • {inst.adapter_type}
            </div>

            {/* Mock real-time data for each instrument */}
            {inst.dimensionality === '0D' && (
              <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                <div className="text-lg font-mono text-blue-600 dark:text-blue-400">
                  {(Math.random() * 1000 + 500).toFixed(0)} counts/s
                </div>
              </div>
            )}

            {inst.dimensionality === '1D' && (
              <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                <div className="h-8 bg-blue-200 dark:bg-blue-800 rounded relative overflow-hidden">
                  <div className="absolute inset-1 bg-blue-600 rounded animate-pulse" style={{width: '60%'}} />
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Spectrum active</div>
              </div>
            )}

            {inst.dimensionality === '2D' && (
              <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                <div className="h-8 bg-gradient-to-r from-gray-300 to-blue-300 dark:from-gray-600 dark:to-blue-600 rounded" />
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Image capturing</div>
              </div>
            )}

            {inst.kind === 'motor' && (
              <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-600 dark:text-gray-400">Position:</span>
                  <span className="text-sm font-mono text-gray-900 dark:text-white">
                    {(Math.random() * 100).toFixed(2)} mm
                  </span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <FloatingWindow
      title={`${workflow.name} - Live Control`}
      isOpen={isOpen}
      onClose={onClose}
      initialWidth={1200}
      initialHeight={800}
      showSettings={false}
    >
      <div className="h-full grid grid-cols-3 gap-4">
        {/* Left Column - Controls & Status */}
        <div className="space-y-4">
          {/* Workflow Status */}
          <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
              Status
            </h3>
            <div className="space-y-3">
              <div className={`text-lg font-medium ${
                workflow.running || isExecuting ? 'text-blue-600 dark:text-blue-400' : 'text-gray-600 dark:text-gray-400'
              }`}>
                {workflow.running || isExecuting ? 'Running' : 'Ready'}
              </div>

              {(workflow.running || isExecuting) && (
                <div>
                  <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                    <span>Progress</span>
                    <span>{workflowProgress.toFixed(0)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${workflowProgress}%` }}
                    />
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                    {currentStep}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Control Buttons */}
          <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
              Controls
            </h3>
            <div className="space-y-2">
              {!workflow.running && !isExecuting ? (
                <button
                  onClick={handleExecute}
                  className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors"
                >
                  <Play className="h-4 w-4" />
                  <span>Execute Workflow</span>
                </button>
              ) : (
                <button
                  onClick={handleStop}
                  className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md font-medium transition-colors"
                >
                  <Square className="h-4 w-4" />
                  <span>Stop Workflow</span>
                </button>
              )}

              <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors">
                <RefreshCw className="h-4 w-4" />
                <span>Refresh</span>
              </button>

              {workflowData.length > 0 && (
                <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md font-medium transition-colors">
                  <Download className="h-4 w-4" />
                  <span>Export Data</span>
                </button>
              )}
            </div>
          </div>

          {/* Connected Instruments */}
          <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
              <BarChart3 className="h-4 w-4 mr-2" />
              Connected Instruments
            </h3>
            <div className="max-h-64 overflow-y-auto">
              {renderConnectedInstruments()}
            </div>
          </div>
        </div>

        {/* Right Columns - Workflow Visualization */}
        <div className="col-span-2 space-y-4">
          <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg h-full">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
              Live Results
            </h3>
            {renderWorkflowVisualization()}
          </div>
        </div>
      </div>
    </FloatingWindow>
  );
}