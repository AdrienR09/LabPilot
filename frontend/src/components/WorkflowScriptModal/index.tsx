import React, { useEffect, useState } from 'react';
import { X, Save, FileCode2 } from 'lucide-react';
import { getWorkflowScript, updateWorkflowScript } from '@/api';

interface WorkflowScriptModalProps {
  workflowId: string;
  workflowName: string;
  onClose: () => void;
}

/**
 * Read/edit view of a workflow's generated (or externally-authored) .py
 * script — see GET/PUT /api/workflows/{id}/script in server.py. This is a
 * plain in-app text editor, not a system-editor handoff: it stays portable
 * across the plain-browser and Qt-shell contexts this app already runs in,
 * and edits here are file-only (not re-parsed back into the workflow graph
 * — see core/workflow/script.py's module docstring for why).
 */
export function WorkflowScriptModal({ workflowId, workflowName, onClose }: WorkflowScriptModalProps) {
  const [path, setPath] = useState<string | null>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getWorkflowScript(workflowId)
      .then((script) => {
        if (cancelled) return;
        setPath(script.path);
        setContent(script.content);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load script');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateWorkflowScript(workflowId, content);
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save script');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-2 min-w-0">
            <FileCode2 className="h-5 w-5 text-gray-500 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{workflowName}</p>
              {path && <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{path}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Loading script…</p>
          ) : error ? (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          ) : (
            <textarea
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                setDirty(true);
              }}
              spellCheck={false}
              className="w-full h-[55vh] font-mono text-sm p-3 rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 resize-none"
            />
          )}
        </div>

        <div className="flex items-center justify-end space-x-2 px-4 py-3 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
          >
            Close
          </button>
          <button
            onClick={handleSave}
            disabled={loading || saving || !dirty}
            className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-md"
          >
            <Save className="h-4 w-4 mr-1.5" />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
