import React, { useState } from 'react';
import { useLabPilotStore } from '@/store';
import { X } from 'lucide-react';

interface Adapter {
  name: string;
  type: string;
  category: string;
}

interface DeviceModalProps {
  isOpen: boolean;
  availableAdapters: Adapter[];
}

export function DeviceModal({ isOpen, availableAdapters }: DeviceModalProps) {
  const { connectDevice, hideDeviceModal, devicesLoading } = useLabPilotStore();
  const [deviceName, setDeviceName] = useState('');
  const [selectedAdapter, setSelectedAdapter] = useState<string>('');
  const [instrumentModel, setInstrumentModel] = useState('');
  const [connectionParams, setConnectionParams] = useState<Record<string, string>>({});

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!deviceName.trim() || !selectedAdapter) {
      alert('Please fill in all required fields');
      return;
    }

    try {
      await connectDevice(deviceName, selectedAdapter, {
        ...connectionParams,
        category: availableAdapters.find(a => a.type === selectedAdapter)?.category || 'Unknown',
        model: instrumentModel || 'N/A',
      });
      // Reset form
      setDeviceName('');
      setSelectedAdapter('');
      setInstrumentModel('');
      setConnectionParams({});
    } catch (error) {
      console.error('Failed to connect device:', error);
    }
  };

  const handleParamChange = (key: string, value: string) => {
    setConnectionParams((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Connect Device</h2>
          <button
            onClick={hideDeviceModal}
            disabled={devicesLoading}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 disabled:opacity-50"
          >
            <X size={20} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Device Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Device Name
            </label>
            <input
              type="text"
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              disabled={devicesLoading}
              placeholder="e.g., Power Meter 1"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Adapter Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Device Type
            </label>
            <select
              value={selectedAdapter}
              onChange={(e) => setSelectedAdapter(e.target.value)}
              disabled={devicesLoading}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="">Select a device type...</option>
              {availableAdapters.map((adapter) => (
                <option key={adapter.type} value={adapter.type}>
                  {adapter.name} ({adapter.category})
                </option>
              ))}
            </select>
          </div>

          {/* Instrument Model */}
          {selectedAdapter && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Instrument Model
              </label>
              <input
                type="text"
                value={instrumentModel}
                onChange={(e) => setInstrumentModel(e.target.value)}
                disabled={devicesLoading}
                placeholder="e.g., USB2000+, iXon EMCCD, ESP301..."
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 disabled:opacity-50"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Category: {availableAdapters.find(a => a.type === selectedAdapter)?.category || 'N/A'}
              </p>
            </div>
          )}

          {/* Connection Parameters */}
          {selectedAdapter && (
            <div className="pt-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Connection Parameters (Optional)
              </label>
              <div className="space-y-2">
                {['host', 'port', 'timeout', 'baudrate'].map((param) => (
                  <input
                    key={param}
                    type="text"
                    placeholder={param.charAt(0).toUpperCase() + param.slice(1)}
                    value={connectionParams[param] || ''}
                    onChange={(e) => handleParamChange(param, e.target.value)}
                    disabled={devicesLoading}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                  />
                ))}
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex space-x-3 pt-4">
            <button
              type="button"
              onClick={hideDeviceModal}
              disabled={devicesLoading}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={devicesLoading || !deviceName.trim() || !selectedAdapter}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
            >
              {devicesLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                  Connecting...
                </>
              ) : (
                'Connect'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
