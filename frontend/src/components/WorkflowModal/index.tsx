import React, { useState } from 'react';
import { useLabPilotStore } from '@/store';

interface WorkflowModalProps {
  isOpen: boolean;
}

const WORKFLOW_TEMPLATES = [
  { name: 'Power Sweep', description: 'Automated power measurement across range', icon: '📊' },
  { name: 'Device Characterization', description: 'Complete device parameter measurement', icon: '🔬' },
  { name: 'Spectral Analysis', description: 'Automated spectroscopy measurements', icon: '🌈' },
  { name: 'Position Calibration', description: 'Precision alignment workflow', icon: '📐' },
];

export function WorkflowModal({ isOpen }: WorkflowModalProps) {
  const { createWorkflow, workflowsLoading, workflowsError, hideWorkflowModal } = useLabPilotStore();
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workflowName) return;

    await createWorkflow(workflowName, workflowDescription);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Create New Workflow</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {workflowsError && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded text-sm">
              {workflowsError}
            </div>
          )}

          {/* Using Template */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Use a template (optional)
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
              {WORKFLOW_TEMPLATES.map((template) => (
                <button
                  key={template.name}
                  type="button"
                  onClick={() => {
                    setSelectedTemplate(template.name);
                    setWorkflowName(template.name);
                    setWorkflowDescription(template.description);
                  }}
                  className={`p-4 rounded-lg border-2 transition-all text-left ${
                    selectedTemplate === template.name
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                  disabled={workflowsLoading}
                >
                  <div className="flex items-start space-x-3">
                    <span className="text-2xl">{template.icon}</span>
                    <div>
                      <h3 className="font-medium text-gray-900 dark:text-white">{template.name}</h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{template.description}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Workflow Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Workflow Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="Enter workflow name"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-green-500 focus:border-transparent"
              disabled={workflowsLoading}
            />
          </div>

          {/* Workflow Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description (optional)
            </label>
            <textarea
              value={workflowDescription}
              onChange={(e) => setWorkflowDescription(e.target.value)}
              placeholder="Describe what this workflow does"
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-green-500 focus:border-transparent resize-none"
              disabled={workflowsLoading}
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={hideWorkflowModal}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={workflowsLoading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              disabled={workflowsLoading || !workflowName}
            >
              {workflowsLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Creating...
                </>
              ) : (
                'Create Workflow'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
