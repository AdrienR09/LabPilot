import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  Link,
  Unlink,
  Settings,
  Trash2,
  Monitor,
  Wifi,
  WifiOff,
  Move3D,
  Gauge,
  Camera,
  Zap,
  Plus,
  Download,
  ExternalLink,
  Play,
} from 'lucide-react';
import { useLabPilotStore } from '@/store';
import { qtBridge, initQtBridge } from '@/utils/qtBridge';
import { InstrumentUIModal } from '@/components/InstrumentUIModal';

export default function Devices() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<Record<string, 'connecting' | 'disconnecting' | null>>({});
  const [selectedInstrument, setSelectedInstrument] = useState<string | null>(null);

  // Use store directly - no local state duplication!
  const {
    showDeviceModal,
    devices,
    connectDeviceById,
    disconnectDevice,
    showInstrumentSettings,
    hideInstrumentSettings,
    ui
  } = useLabPilotStore();

  useEffect(() => {
    // Initialize Qt Bridge
    initQtBridge(() => {
      console.log('✅ Qt Bridge ready');
    });
    setLoading(false);
  }, []);

  const handleConnect = async (instrumentId: string) => {
    setConnectionStatus(prev => ({ ...prev, [instrumentId]: 'connecting' }));
    try {
      await connectDeviceById(instrumentId);
      setConnectionStatus(prev => ({ ...prev, [instrumentId]: null }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect device');
      setConnectionStatus(prev => ({ ...prev, [instrumentId]: null }));
    }
  };

  const handleDisconnect = async (instrumentId: string) => {
    setConnectionStatus(prev => ({ ...prev, [instrumentId]: 'disconnecting' }));
    try {
      await disconnectDevice(instrumentId);
      setConnectionStatus(prev => ({ ...prev, [instrumentId]: null }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect device');
      setConnectionStatus(prev => ({ ...prev, [instrumentId]: null }));
    }
  };

  const getInstrumentIcon = (inst: { kind?: string; dimensionality?: string }) => {
    if (inst.kind === 'detector') {
      if (inst.dimensionality === '0D') return Gauge;
      if (inst.dimensionality === '1D') return Activity;
      if (inst.dimensionality === '2D') return Camera;
    }
    if (inst.kind === 'motor') {
      return Move3D;
    }
    return Zap;
  };

  const getDimensionalityColor = (dim: string | undefined) => {
    switch (dim) {
      case '0D': return 'blue';
      case '1D': return 'green';
      case '2D': return 'purple';
      case '3D': return 'orange';
      default: return 'gray';
    }
  };

  const handleConnectDevice = () => {
    showDeviceModal();
  };

  const launchInstrumentQtWindow = (instrument: { id: string; name: string }) => {
    console.log(`🚀 Launching UI for: ${instrument.name} (${instrument.id})`);
    console.log(`Is in Qt: ${qtBridge.isInQt()}`);
    console.log(`Bridge object:`, qtBridge);
    console.log(`launchInstrumentUI method exists:`, typeof qtBridge.launchInstrumentUI);

    if (!qtBridge || typeof qtBridge.launchInstrumentUI !== 'function') {
      console.error('❌ QtBridge.launchInstrumentUI not available');
      alert('Qt Bridge not ready. Make sure you\'re running in Qt Manager.');
      return;
    }

    try {
      console.log('Calling qtBridge.launchInstrumentUI...');
      qtBridge.launchInstrumentUI(instrument.id);
      console.log(`✅ Launch command sent for: ${instrument.name}`);
    } catch (err) {
      console.error('❌ Error launching UI:', err);
      alert(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  if (loading && devices.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-center h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
      </div>
    );
  }

  if (error && devices.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Instruments</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Manage laboratory instruments and connections
          </p>
        </div>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-red-800 dark:text-red-200">{error}</p>
        </div>
      </div>
    );
  }

  // Group instruments by type
  const detectors = devices.filter(i => i.kind === 'detector');
  const motors = devices.filter(i => i.kind === 'motor');

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Instruments</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Loaded laboratory instruments ({devices.length})
          </p>
        </div>
        <div className="flex flex-col space-y-3">
          {/* Web Interface Controls */}
          <button
            onClick={handleConnectDevice}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
          >
            <Plus className="h-4 w-4 mr-2" />
            Connect Device
          </button>
        </div>
      </div>

      {/* Detectors */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <Gauge className="h-5 w-5 mr-2 text-green-500" />
          Detectors ({detectors.length})
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {detectors.map((instrument) => {
            const Icon = getInstrumentIcon(instrument);
            const color = getDimensionalityColor(instrument.dimensionality);
            const isSelected = selectedInstrument === instrument.id;

            return (
              <div
                key={instrument.id}
                className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-all hover:shadow-lg"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className={`p-2 rounded-lg bg-${color}-100 dark:bg-${color}-900/30`}>
                        <Icon className={`h-5 w-5 text-${color}-600 dark:text-${color}-400`} />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {instrument.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {instrument.dimensionality} {instrument.kind}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Status */}
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                      instrument.connected
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                    }`}>
                      {instrument.connected ? (
                        <><Wifi className="h-3 w-3 mr-1" /> Connected</>
                      ) : (
                        <><WifiOff className="h-3 w-3 mr-1" /> Disconnected</>
                      )}
                    </span>
                  </div>

                  {/* Control Buttons */}
                  <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          launchInstrumentQtWindow(instrument);
                        }}
                        className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                        title="Open Qt UI"
                      >
                        <Monitor className="h-4 w-4" />
                      </button>
                      {instrument.connected ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDisconnect(instrument.id);
                          }}
                          disabled={connectionStatus[instrument.id] === 'disconnecting'}
                          className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors disabled:opacity-50"
                          title="Disconnect"
                        >
                          <Unlink className="h-4 w-4" />
                        </button>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleConnect(instrument.id);
                          }}
                          disabled={connectionStatus[instrument.id] === 'connecting'}
                          className="p-2 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 rounded-lg transition-colors disabled:opacity-50"
                          title={connectionStatus[instrument.id] === 'connecting' ? 'Connecting...' : 'Connect'}
                        >
                          <Link className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          showInstrumentSettings(instrument.id);
                        }}
                        className="p-2 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        title="Settings"
                      >
                        <Settings className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete "${instrument.name}"?`)) {
                            disconnectDevice(instrument.id);
                          }
                        }}
                        className="p-2 text-gray-600 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400 rounded-lg transition-colors"
                        title="Delete"
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
      </div>

      {/* Motors/Actuators */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <Move3D className="h-5 w-5 mr-2 text-blue-500" />
          Motors & Actuators ({motors.length})
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {motors.map((instrument) => {
            const Icon = getInstrumentIcon(instrument);
            const color = getDimensionalityColor(instrument.dimensionality);
            const isSelected = selectedInstrument === instrument.id;

            return (
              <div
                key={instrument.id}
                className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 transition-all hover:shadow-lg"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className={`p-2 rounded-lg bg-${color}-100 dark:bg-${color}-900/30`}>
                        <Icon className={`h-5 w-5 text-${color}-600 dark:text-${color}-400`} />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {instrument.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {instrument.dimensionality} {instrument.kind}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Status */}
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                      instrument.connected
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                    }`}>
                      {instrument.connected ? (
                        <><Wifi className="h-3 w-3 mr-1" /> Connected</>
                      ) : (
                        <><WifiOff className="h-3 w-3 mr-1" /> Disconnected</>
                      )}
                    </span>
                  </div>

                  {/* Control Buttons */}
                  <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          launchInstrumentQtWindow(instrument);
                        }}
                        className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                        title="Open Qt UI"
                      >
                        <Monitor className="h-4 w-4" />
                      </button>
                      {instrument.connected ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDisconnect(instrument.id);
                          }}
                          disabled={connectionStatus[instrument.id] === 'disconnecting'}
                          className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors disabled:opacity-50"
                          title="Disconnect"
                        >
                          <Unlink className="h-4 w-4" />
                        </button>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleConnect(instrument.id);
                          }}
                          disabled={connectionStatus[instrument.id] === 'connecting'}
                          className="p-2 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 rounded-lg transition-colors disabled:opacity-50"
                          title={connectionStatus[instrument.id] === 'connecting' ? 'Connecting...' : 'Connect'}
                        >
                          <Link className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center space-x-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          showInstrumentSettings(instrument.id);
                        }}
                        className="p-2 text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        title="Settings"
                      >
                        <Settings className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete "${instrument.name}"?`)) {
                            disconnectDevice(instrument.id);
                          }
                        }}
                        className="p-2 text-gray-600 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400 rounded-lg transition-colors"
                        title="Delete"
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
      </div>

      {/* Instrument Settings Modal */}
      {ui.selectedInstrumentId && devices.find(d => d.id === ui.selectedInstrumentId) && (
        <InstrumentUIModal
          instrument={{
            id: devices.find(d => d.id === ui.selectedInstrumentId)?.id || '',
            name: devices.find(d => d.id === ui.selectedInstrumentId)?.name || '',
            adapter_type: devices.find(d => d.id === ui.selectedInstrumentId)?.adapter_type || '',
            kind: devices.find(d => d.id === ui.selectedInstrumentId)?.kind || 'detector',
            dimensionality: (devices.find(d => d.id === ui.selectedInstrumentId)?.dimensionality || '0D') as any,
            connected: devices.find(d => d.id === ui.selectedInstrumentId)?.connected || false,
            tags: devices.find(d => d.id === ui.selectedInstrumentId)?.tags || [],
          }}
          isOpen={ui.showInstrumentSettings}
          onClose={hideInstrumentSettings}
        />
      )}
    </div>
  );
}