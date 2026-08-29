import React, { useState } from 'react';
import { X, Upload, FilePlus, AlertTriangle } from 'lucide-react';
import { useLabPilotStore } from '@/store';

interface UploadSetupModalProps {
  isOpen: boolean;
}

export function UploadSetupModal({ isOpen }: UploadSetupModalProps) {
  const { hideUploadSetupModal, createBlankInstrumentConfig, uploadInstrumentConfig, devicesLoading, devicesError } = useLabPilotStore();

  const [newName, setNewName] = useState('');
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [parsedName, setParsedName] = useState<string | null>(null);
  const [parsedDevices, setParsedDevices] = useState<Record<string, any>[] | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    setFileError(null);
    setParsedDevices(null);
    setParsedName(null);
    if (!file) {
      setFileName(null);
      return;
    }
    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result as string);
        if (!Array.isArray(data.devices)) {
          throw new Error('File is missing a "devices" array');
        }
        setParsedName(data.name || file.name.replace(/\.(json|cfg)$/i, ''));
        setParsedDevices(data.devices);
      } catch (err) {
        setFileError(err instanceof Error ? err.message : 'Could not parse this file as a LabPilot instrument config');
      }
    };
    reader.onerror = () => setFileError('Could not read the selected file');
    reader.readAsText(file);
  };

  const handleLoadUpload = () => {
    if (parsedName && parsedDevices) {
      uploadInstrumentConfig(parsedName, parsedDevices);
    }
  };

  const handleCreateNew = () => {
    if (newName.trim()) {
      createBlankInstrumentConfig(newName.trim());
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg max-w-md w-full mx-4">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Setup</h2>
          <button onClick={hideUploadSetupModal} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {devicesError && (
            <div className="p-2 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded text-sm">
              {devicesError}
            </div>
          )}

          {/* Upload a file */}
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2 flex items-center">
              <Upload className="h-4 w-4 mr-2" />
              Upload a setup file
            </h3>
            <input
              type="file"
              accept="application/json,.json,.cfg"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-600 dark:text-gray-300 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:bg-blue-50 dark:file:bg-blue-900/30 file:text-blue-700 dark:file:text-blue-300 file:text-sm"
            />
            {fileError && (
              <p className="mt-2 text-xs text-red-600 dark:text-red-400 flex items-center">
                <AlertTriangle className="h-3 w-3 mr-1" /> {fileError}
              </p>
            )}
            {parsedDevices && (
              <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                {parsedName} — {parsedDevices.length} instrument{parsedDevices.length === 1 ? '' : 's'}
              </p>
            )}
            <button
              onClick={handleLoadUpload}
              disabled={!parsedDevices || devicesLoading}
              className="mt-3 w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium transition-colors"
            >
              {devicesLoading ? 'Loading…' : 'Load this setup'}
            </button>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2 flex items-center">
              <FilePlus className="h-4 w-4 mr-2" />
              Or create a new blank setup
            </h3>
            <div className="flex gap-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. optics_bench_2"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleCreateNew}
                disabled={!newName.trim() || devicesLoading}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-800 dark:bg-gray-600 dark:hover:bg-gray-500 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md text-sm font-medium transition-colors"
              >
                Create
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Starts empty — instruments you add afterward are saved into it automatically.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
