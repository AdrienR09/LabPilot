import React, { useState, useEffect } from 'react';
import {
  X,
  Activity,
  Play,
  Square,
  Settings,
  Download,
  RefreshCw,
  BarChart3,
  Clock,
  Target,
  Zap,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';
import { DashboardWorkflow, DashboardInstrument } from '@/api';

interface WorkflowUIModalProps {
  workflow: DashboardWorkflow | null;
  instruments: DashboardInstrument[];
  isOpen: boolean;
  onClose: () => void;
}

interface WorkflowData {
  timestamp: string;
  results: any[];
  progress: number;
  currentStep: string;
  estimatedTime: number;
  metadata?: Record<string, any>;
}

export function WorkflowUIModal({ workflow, instruments, isOpen, onClose }: WorkflowUIModalProps) {
  const [data, setData] = useState<WorkflowData | null>(null);
  const [settings, setSettings] = useState({
    autoSave: true,
    dataFormat: 'JSON',
    logLevel: 'INFO',
    notifications: true,
  });

  // Simulate workflow data based on type
  useEffect(() => {
    if (!isOpen || !workflow) return;

    const generateMockData = () => {
      const timestamp = new Date().toISOString();
      let results: any[] = [];
      let currentStep = '';
      let estimatedTime = 0;

      switch (workflow.workflow_type) {
        case 'confocal_microscopy':
          currentStep = workflow.running ? 'Scanning position (45, 67)' : 'Ready to start';
          estimatedTime = 1200; // 20 minutes
          results = Array.from({ length: 100 }, (_, i) => ({
            x: i % 10,
            y: Math.floor(i / 10),
            intensity: Math.random() * 1000 + 500,
          }));
          break;

        case 'transient_absorption':
          currentStep = workflow.running ? 'Pump-probe delay: 2.5 ps' : 'Ready to start';
          estimatedTime = 900; // 15 minutes
          results = Array.from({ length: 50 }, (_, i) => ({
            wavelength: 400 + i * 10,
            delay: i * 0.1,
            absorption: Math.sin(i * 0.2) * 0.1 + Math.random() * 0.05,
          }));
          break;

        default:
          currentStep = workflow.running ? 'Processing...' : 'Ready';
          estimatedTime = 600;
          results = [];
      }

      setData({
        timestamp,
        results,
        progress: workflow.progress,
        currentStep,
        estimatedTime,
        metadata: {
          startTime: new Date(Date.now() - 300000).toISOString(),
          dataPoints: results.length,
          connectedInstruments: workflow.connected_instruments.length,
        },
      });
    };

    // Generate initial data
    generateMockData();

    // Auto-refresh data if running
    const interval = setInterval(() => {
      if (workflow.running) {
        generateMockData();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [isOpen, workflow]);

  if (!isOpen || !workflow) return null;

  const connectedInsts = workflow.connected_instruments
    .map(instId => instruments.find(i => i.id === instId))
    .filter(Boolean) as DashboardInstrument[];

  const renderWorkflowVisualization = () => {
    if (!data) return <div className="text-gray-500">No data available</div>;

    switch (workflow.workflow_type) {
      case 'confocal_microscopy':
        return (
          <div className="space-y-4">
            <div className="h-64 bg-gray-50 dark:bg-gray-700 rounded border relative">
              {/* Mock confocal scan visualization */}
              <div className="absolute inset-4 grid grid-cols-10 gap-1">
                {data.results.map((point, i) => (
                  <div
                    key={i}
                    className="aspect-square rounded"
                    style={{
                      backgroundColor: `rgba(59, 130, 246, ${point.intensity / 1500})`,
                    }}
                  />
                ))}
              </div>
              <div className="absolute top-2 right-2 text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 px-2 py-1 rounded">
                10×10 scan
              </div>
            </div>
            <div className="text-xs text-gray-400 text-center">
              Confocal intensity map (counts)
            </div>
          </div>
        );

      case 'transient_absorption':
        return (
          <div className="space-y-4">
            <div className="h-64 bg-gray-50 dark:bg-gray-700 rounded border relative overflow-hidden">
              {/* Mock transient absorption heatmap */}
              <div className="absolute inset-0">
                <svg className="w-full h-full">
                  {data.results.map((point, i) => (
                    <rect
                      key={i}
                      x={i * (100 / data.results.length) + '%'}
                      y="50%"
                      width={100 / data.results.length + '%'}
                      height={Math.abs(point.absorption * 200) + 'px'}
                      fill={point.absorption > 0 ? 'rgb(239, 68, 68)' : 'rgb(59, 130, 246)'}
                      opacity="0.7"
                    />
                  ))}
                </svg>
              </div>
              <div className="absolute top-2 right-2 text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 px-2 py-1 rounded">
                ΔA vs λ
              </div>
            </div>
            <div className="text-xs text-gray-400 text-center">
              Transient absorption spectrum (mOD)
            </div>
          </div>
        );

      default:
        return (
          <div className="h-64 bg-gray-50 dark:bg-gray-700 rounded border flex items-center justify-center">
            <div className="text-center text-gray-500">
              <Activity className="h-8 w-8 mx-auto mb-2" />
              <div>Workflow visualization</div>
              <div className="text-sm">Will appear when running</div>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-full max-w-6xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30">
              <Activity className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                {workflow.name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {workflow.workflow_type.replace('_', ' ')} workflow
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
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Left Column - Status & Controls */}
            <div className="space-y-6">
              {/* Workflow Status */}
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                  Status
                </h3>
                <div className="space-y-3">
                  <div className="flex items-center space-x-2">
                    {workflow.running ? (
                      <div className="flex items-center space-x-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                        <span className="text-sm font-medium text-blue-600 dark:text-blue-400">
                          Running
                        </span>
                      </div>
                    ) : workflow.has_data ? (
                      <div className="flex items-center space-x-2">
                        <CheckCircle className="h-4 w-4 text-green-600" />
                        <span className="text-sm font-medium text-green-600 dark:text-green-400">
                          Completed
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center space-x-2">
                        <AlertCircle className="h-4 w-4 text-gray-500" />
                        <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
                          Ready
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Progress Bar */}
                  {workflow.running && (
                    <div>
                      <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                        <span>Progress</span>
                        <span>{workflow.progress}%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${workflow.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Current Step */}
                  {data && (
                    <div>
                      <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                        Current Step
                      </div>
                      <div className="text-sm text-gray-900 dark:text-white">
                        {data.currentStep}
                      </div>
                    </div>
                  )}

                  {/* Estimated Time */}
                  {workflow.running && data && (
                    <div className="flex items-center space-x-2 text-xs text-gray-600 dark:text-gray-400">
                      <Clock className="h-3 w-3" />
                      <span>~{Math.floor(data.estimatedTime / 60)} min remaining</span>
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
                  {!workflow.running ? (
                    <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors">
                      <Play className="h-4 w-4" />
                      <span>Start Workflow</span>
                    </button>
                  ) : (
                    <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md font-medium transition-colors">
                      <Square className="h-4 w-4" />
                      <span>Stop Workflow</span>
                    </button>
                  )}

                  <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors">
                    <RefreshCw className="h-4 w-4" />
                    <span>Reload</span>
                  </button>

                  {workflow.has_data && (
                    <button className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md font-medium transition-colors">
                      <Download className="h-4 w-4" />
                      <span>Export Results</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Connected Instruments */}
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                  Connected Instruments
                </h3>
                <div className="space-y-2">
                  {connectedInsts.map((inst) => (
                    <div key={inst.id} className="flex items-center justify-between">
                      <span className="text-sm text-gray-900 dark:text-white truncate">
                        {inst.name}
                      </span>
                      <div className={`w-2 h-2 rounded-full ${
                        inst.connected ? 'bg-green-500' : 'bg-red-500'
                      }`} />
                    </div>
                  ))}
                  {connectedInsts.length === 0 && (
                    <div className="text-sm text-gray-500 italic">
                      No instruments connected
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right Column - Visualization & Settings */}
            <div className="lg:col-span-3 space-y-6">
              {/* Data Visualization */}
              <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                  <BarChart3 className="h-4 w-4 mr-2" />
                  Real-time Results
                </h3>
                {renderWorkflowVisualization()}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Workflow Settings */}
                <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                    <Settings className="h-4 w-4 mr-2" />
                    Settings
                  </h3>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Auto Save</span>
                      <input
                        type="checkbox"
                        checked={settings.autoSave}
                        onChange={(e) => setSettings({...settings, autoSave: e.target.checked})}
                        className="rounded border-gray-300 dark:border-gray-600"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                        Data Format
                      </label>
                      <select
                        value={settings.dataFormat}
                        onChange={(e) => setSettings({...settings, dataFormat: e.target.value})}
                        className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                      >
                        <option value="JSON">JSON</option>
                        <option value="CSV">CSV</option>
                        <option value="HDF5">HDF5</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                        Log Level
                      </label>
                      <select
                        value={settings.logLevel}
                        onChange={(e) => setSettings({...settings, logLevel: e.target.value})}
                        className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                      >
                        <option value="DEBUG">DEBUG</option>
                        <option value="INFO">INFO</option>
                        <option value="WARNING">WARNING</option>
                        <option value="ERROR">ERROR</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Metadata */}
                {data?.metadata && (
                  <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                      Metadata
                    </h3>
                    <div className="space-y-2 text-xs">
                      {Object.entries(data.metadata).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span className="text-gray-600 dark:text-gray-400 capitalize">
                            {key.replace(/([A-Z])/g, ' $1').replace('_', ' ')}:
                          </span>
                          <span className="text-gray-900 dark:text-white font-mono">
                            {typeof value === 'string' && value.includes('T') && value.includes('Z')
                              ? new Date(value).toLocaleTimeString()
                              : String(value)
                            }
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
    </div>
  );
}