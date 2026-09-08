import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  Play,
  Square,
  FileCode2,
  Trash2,
  Monitor,
  RotateCcw,
  FolderOpen,
  LayoutTemplate,
  X,
} from 'lucide-react';
import { useLabPilotStore } from '@/store';
import type { Workflow } from '@/store/index';
import { qtBridge, initQtBridge } from '@/utils/qtBridge';
import { WorkflowScriptModal } from '@/components/WorkflowScriptModal';
import { getWorkflowTemplates, loadWorkflowTemplate, WorkflowTemplate, wsManager } from '@/api';
import type { LabPilotEvent } from '@/types';

// Ready-made, general-purpose workflow templates (core/workflow_templates/)
// — each declares the instrument "roles" it needs (kind + dimensionality)
// rather than hardcoding a specific instrument. Loading one creates a real
// workflow with every role unbound; the user then binds each role to a
// real connected instrument on the Flow page.
function TemplateLibraryModal({ onClose, onLoaded }: { onClose: () => void; onLoaded: (workflowId: string) => void }) {
  const [templates, setTemplates] = useState<WorkflowTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingName, setLoadingName] = useState<string | null>(null);

  useEffect(() => {
    getWorkflowTemplates()
      .then(setTemplates)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load template library'));
  }, []);

  const handleLoad = async (name: string) => {
    setLoadingName(name);
    setError(null);
    try {
      const { workflow_id } = await loadWorkflowTemplate(name);
      onLoaded(workflow_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to load template ${name}`);
    } finally {
      setLoadingName(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Workflow Template Library</h2>
          <button onClick={onClose} className="p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-5 overflow-y-auto space-y-3">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-400">
              {error}
            </div>
          )}
          {templates === null && !error && (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading templates…</p>
          )}
          {templates?.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400">No templates available.</p>
          )}
          {templates?.map((tpl) => (
            <div
              key={tpl.name}
              className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 flex items-start justify-between gap-4"
            >
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  {tpl.name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                </p>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{tpl.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(tpl.required_instruments).map(([role, req]) => (
                    <span
                      key={role}
                      className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300"
                    >
                      {role}: {req.dimensionality} {req.kind}
                    </span>
                  ))}
                </div>
              </div>
              <button
                onClick={() => handleLoad(tpl.name)}
                disabled={loadingName !== null}
                className="shrink-0 px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-md"
              >
                {loadingName === tpl.name ? 'Loading…' : 'Load'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Workflows() {
  const { workflows, devices, executeWorkflow, stopWorkflow, unloadWorkflow, loadWorkflowScript, loadWorkflows, workflowsError } = useLabPilotStore();
  const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(null);
  const [scriptModalWorkflow, setScriptModalWorkflow] = useState<Workflow | null>(null);
  const [loadPathInput, setLoadPathInput] = useState('');
  const [showLoadInput, setShowLoadInput] = useState(false);
  const [showTemplateLibrary, setShowTemplateLibrary] = useState(false);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const handleTemplateLoaded = async (workflowId: string) => {
    setShowTemplateLibrary(false);
    await loadWorkflows();
    // Templates always need their roles bound to real instruments before
    // they can run — send the user straight to the flowchart to do that.
    navigate(`/flow?workflow=${workflowId}`);
  };

  useEffect(() => {
    // Initialize Qt Bridge
    initQtBridge(() => {
      console.log('✅ Qt Bridge ready in Workflows');
    });
  }, []);

  // Follow runs as they start and finish, wherever they were started from.
  //
  // This page only refreshed when you clicked something, so a run started
  // from a Qt window or the console never appeared here, and a run that
  // finished on its own kept its Stop button until you navigated away and
  // back. The backend has broadcast these events on /ws all along and
  // `wsManager` was written to receive them; nothing had ever connected it.
  useEffect(() => {
    const lifecycle = new Set([
      'WORKFLOW_STARTED',
      'WORKFLOW_COMPLETED',
      'WORKFLOW_ERROR',
      'WORKFLOW_STOPPED',
    ]);
    const onEvent = (event: LabPilotEvent) => {
      if (lifecycle.has(event.kind)) loadWorkflows();
    };
    wsManager.addEventListener('event', onEvent);
    wsManager.connect().catch(() => {
      // The page is still usable without it — it just goes back to
      // refreshing when you act on it, which is what it did before.
    });
    return () => {
      wsManager.removeEventListener('event', onEvent);
      wsManager.disconnect();
    };
  }, [loadWorkflows]);

  // Arriving via `?workflow=id` (e.g. a double-click on a workflow's box in
  // the flowchart) highlights that card the same way clicking it would.
  useEffect(() => {
    const id = searchParams.get('workflow');
    if (id) setSelectedWorkflow(id);
  }, [searchParams]);

  const handleExecuteWorkflow = async (workflowId: string) => {
    try {
      await executeWorkflow(workflowId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to execute workflow');
    }
  };

  const handleStopWorkflow = async (workflowId: string) => {
    try {
      await stopWorkflow(workflowId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to stop workflow');
    }
  };

  // Inside the Qt desktop shell this opens a real native combined window
  // (every instrument the workflow references — see qt_bridge.py ->
  // launch_workflow.py -> workflow_window.py) as a separate OS window,
  // mirroring how Devices.tsx opens a single instrument's native window.
  // In a plain browser tab there's no Qt process to open a window in, so
  // fall back to the existing read-only graph view.
  const handleOpenUI = (workflowId: string) => {
    if (qtBridge?.isInQt() && typeof qtBridge.launchWorkflowUI === 'function') {
      try {
        qtBridge.launchWorkflowUI(workflowId);
        return;
      } catch (err) {
        console.error('Error launching native workflow UI, falling back to graph view:', err);
      }
    }
    navigate(`/flow?workflow=${workflowId}`);
  };

  const handleUnloadWorkflow = async (workflowId: string, name: string) => {
    if (!confirm(`Unload "${name}" from the Workflows tab? The script file stays on disk and can be reloaded later.`)) {
      return;
    }
    try {
      await unloadWorkflow(workflowId);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to unload workflow');
    }
  };

  const handleLoadScript = async () => {
    const path = loadPathInput.trim();
    if (!path) return;
    try {
      await loadWorkflowScript(path);
      setLoadPathInput('');
      setShowLoadInput(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to load workflow script');
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
        <div className="flex items-center space-x-2">
          {showLoadInput ? (
            <div className="flex items-center space-x-2">
              <input
                type="text"
                autoFocus
                value={loadPathInput}
                onChange={(e) => setLoadPathInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleLoadScript();
                  if (e.key === 'Escape') setShowLoadInput(false);
                }}
                placeholder="/path/to/workflow_script.py"
                className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white w-72"
              />
              <button
                onClick={handleLoadScript}
                className="px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md"
              >
                Load
              </button>
              <button
                onClick={() => { setShowLoadInput(false); setLoadPathInput(''); }}
                className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowLoadInput(true)}
              className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <FolderOpen className="h-4 w-4 mr-2" />
              Load script…
            </button>
          )}
          <button
            onClick={() => setShowTemplateLibrary(true)}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <LayoutTemplate className="h-4 w-4 mr-2" />
            Templates…
          </button>
        </div>
      </div>

      {workflowsError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-400">
          {workflowsError}
        </div>
      )}

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

                  {/* Status — from the most recent execution_logs row (see
                      GET /api/workflows); a workflow that's never run shows
                      "Ready". */}
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                      workflow.running
                        ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                        : workflow.last_status === 'completed'
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : workflow.last_status === 'failed'
                        ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400'
                    }`}>
                      {workflow.running
                        ? 'Running'
                        : workflow.last_status === 'completed'
                        ? 'Completed'
                        : workflow.last_status === 'failed'
                        ? 'Failed'
                        : workflow.last_status === 'cancelled'
                        ? 'Cancelled'
                        : 'Ready'}
                    </span>
                  </div>

                  {/* Running indicator — no numeric progress is tracked at
                      the workflow-list level (see the native "Open UI"
                      window for a live per-pixel view). */}
                  {workflow.running && (
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                      <div className="bg-blue-600 h-1.5 w-1/3 rounded-full animate-pulse" />
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
                        onClick={(e) => {
                          e.stopPropagation();
                          setScriptModalWorkflow(workflow);
                        }}
                        className="p-2 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        title="View/edit script"
                      >
                        <FileCode2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleUnloadWorkflow(workflow.id, workflow.name);
                        }}
                        className="p-2 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        title="Unload"
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

      {scriptModalWorkflow && (
        <WorkflowScriptModal
          workflowId={scriptModalWorkflow.id}
          workflowName={scriptModalWorkflow.name}
          onClose={() => setScriptModalWorkflow(null)}
        />
      )}

      {showTemplateLibrary && (
        <TemplateLibraryModal
          onClose={() => setShowTemplateLibrary(false)}
          onLoaded={handleTemplateLoaded}
        />
      )}
    </div>
  );
}
