import React, { useEffect, useState } from 'react';
import {
  Activity,
  Play,
  Square,
  Settings,
  Trash2,
  Monitor,
  Plus,
  RotateCcw,
} from 'lucide-react';
import { useLabPilotStore } from '@/store';
import type { Workflow } from '@/store/index';
import { qtBridge, initQtBridge } from '@/utils/qtBridge';

export default function Workflows() {
  const { workflows, devices } = useLabPilotStore();
  const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(null);

  useEffect(() => {
    // Initialize Qt Bridge
    initQtBridge(() => {
      console.log('✅ Qt Bridge ready in Workflows');
    });
  }, []);

  const handleExecuteWorkflow = (workflowId: string) => {
    console.log('🚀 Executing workflow:', workflowId);
    alert(`Executing workflow: ${workflowId}`);
  };

  const handleStopWorkflow = (workflowId: string) => {
    console.log('⏹️  Stopping workflow:', workflowId);
    alert(`Stopping workflow: ${workflowId}`);
  };

  const handleOpenUI = (workflowId: string) => {
    const workflow = workflows.find(w => w.id === workflowId);
    if (workflow) {
      console.log('📊 Opening UI for workflow:', workflow.name);
      alert(`Opening UI for workflow: ${workflow.name}`);
    }
  };

  // Get connected instrument names
  const getConnectedInstrumentNames = (instIds: string[] = []) => {
    return instIds
      .map(id => devices.find(d => d.id === id))
      .filter(Boolean)
      .map(d => d?.name || 'Unknown');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Workflows</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Manage laboratory workflows ({workflows.length})
          </p>
        </div>
        <button className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">
          <Plus className="h-4 w-4 mr-2" />
          New Workflow
        </button>
      </div>

      {/* Workflows Grid */}
      {workflows.length === 0 ? (
        <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-8 text-center">
          <Activity className="h-12 w-12 mx-auto text-gray-400 mb-3" />
          <p className="text-gray-600 dark:text-gray-400">No workflows loaded</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflows.map((workflow) => {
            const isSelected = selectedWorkflow === workflow.id;
            const connectedInstNames = getConnectedInstrumentNames(workflow.connected_instruments);

            return (
              <div
                key={workflow.id}
                onClick={() => setSelectedWorkflow(isSelected ? null : workflow.id)}
                className={`bg-white dark:bg-gray-800 rounded-lg shadow p-4 cursor-pointer transition-all ${
                  isSelected ? 'ring-2 ring-blue-500' : 'hover:shadow-md'
                }`}
              >
                <div className="space-y-3">
                  {/* Header */}
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {workflow.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {workflow.workflow_type || 'Workflow'}
                    </p>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-gray-600 dark:text-gray-400">
                    {workflow.description || 'No description'}
                  </p>

                  {/* Status */}
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                      workflow.running
                        ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                        : workflow.has_data
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400'
                    }`}>
                      {workflow.running ? 'Running' : workflow.has_data ? 'Completed' : 'Ready'}
                    </span>
                  </div>

                  {/* Progress Bar (if running) */}
                  {workflow.running && (
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${workflow.progress || 0}%` }}
                      />
                    </div>
                  )}

                  {/* Connected Instruments */}
                  {connectedInstNames.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {connectedInstNames.map((name, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                        >
                          {name}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Control Buttons */}
                  <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenUI(workflow.id);
                        }}
                        className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                        title="Open UI"
                      >
                        <Monitor className="h-4 w-4" />
                      </button>
                      {!workflow.running ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleExecuteWorkflow(workflow.id);
                          }}
                          className="p-2 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 rounded-lg transition-colors"
                          title="Execute"
                        >
                          <Play className="h-4 w-4" />
                        </button>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStopWorkflow(workflow.id);
                          }}
                          className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                          title="Stop"
                        >
                          <Square className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        className="p-2 text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded-lg transition-colors"
                        title="Reload"
                      >
                        <RotateCcw className="h-4 w-4" />
                      </button>
                    </div>
                    <div className="flex items-center space-x-1">
                      <button
                        className="p-2 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        title="Settings"
                      >
                        <Settings className="h-4 w-4" />
                      </button>
                      <button
                        className="p-2 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
