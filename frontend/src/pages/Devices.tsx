import React, { useEffect, useState } from 'react';
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
  Upload,
  Loader2,
  AlertTriangle,
  Radio,
} from 'lucide-react';
import { useLabPilotStore } from '@/store';
import { readInstrumentData } from '@/api';
import { qtBridge, initQtBridge } from '@/utils/qtBridge';
import { InstrumentUIModal } from '@/components/InstrumentUIModal';
import { InstrumentSettingsModal } from '@/components/InstrumentSettingsModal';

// Reduce a read() dict down to one short display string for a device card.
// Actuators show every axis (there are at most 3); detectors/sources show
// their primary reading, averaged down to a scalar for 1D/2D arrays since a
// card has no room for a trace or image.
function formatLiveValue(kind: string | undefined, data: Record<string, any> | undefined): string | null {
  if (!data) return null;
  const keys = Object.keys(data);
  if (keys.length === 0) return null;

  if (kind === 'motor') {
    return keys
      .map((k) => {
        const v = data[k];
        return typeof v === 'boolean' ? `${k}: ${v ? 'ON' : 'OFF'}` : `${k}: ${Number(v).toFixed(2)}`;
      })
      .join('  ');
  }

  const value = data[keys[0]];
  if (typeof value === 'boolean') return value ? 'ON' : 'OFF';
  if (typeof value === 'number') return value.toFixed(3);
  if (Array.isArray(value)) {
    const flat: number[] = value.flat(Infinity).filter((v: unknown) => typeof v === 'number');
    if (flat.length === 0) return null;
    const avg = flat.reduce((a, b) => a + b, 0) / flat.length;
    return `avg: ${avg.toFixed(2)}`;
  }
  return null;
}

// DeviceSchema.kind is "detector" | "motor" | "source" | "counter" | "generic"
// (src/core/device/schema.py). Only 3 user-facing groups: "counter" (a 0D
// detector) and "generic" (couldn't be classified more precisely — mostly
// niche power supplies/timing gear the auto-classifier wasn't sure about)
// both fold into Detectors so nothing has its own confusing bucket, and
// nothing silently vanishes either.
const KIND_GROUPS: Record<string, { label: string; icon: any }> = {
  detector: { label: 'Detectors', icon: Gauge },
  motor: { label: 'Motors & Actuators', icon: Move3D },
  source: { label: 'Sources', icon: Radio },
};
const KIND_ORDER = ['detector', 'motor', 'source'];
const KIND_ALIAS: Record<string, string> = { counter: 'detector', generic: 'detector' };

export default function Devices() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<Record<string, 'connecting' | 'disconnecting' | null>>({});
  const [liveValues, setLiveValues] = useState<Record<string, Record<string, any>>>({});

  const {
    showDeviceModal,
    showUploadSetupModal,
    devices,
    connectDeviceById,
    disconnectDevice,
    removeDevice,
    showInstrumentSettings,
    hideInstrumentSettings,
    showInstrumentUI,
    hideInstrumentUI,
    activeInstrumentConfig,
    loadInstrumentConfigs,
    ui,
  } = useLabPilotStore();

  useEffect(() => {
    loadInstrumentConfigs();
    setLoading(false);
  }, []);

  // Poll connected instruments so cards show a live reading instead of just
  // connect/disconnect status. Kept on a ref so the interval isn't torn down
  // and rebuilt every time `devices` changes identity.
  const devicesRef = React.useRef(devices);
  devicesRef.current = devices;

  useEffect(() => {
    const poll = () => {
      const connected = devicesRef.current.filter((d) => d.connected);
      for (const d of connected) {
        readInstrumentData(d.id)
          .then((data) => setLiveValues((prev) => ({ ...prev, [d.id]: data })))
          .catch(() => {
            // Transient read errors shouldn't spam the card — just skip this tick.
          });
      }
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    initQtBridge();
  }, []);

  const handleConnect = async (instrumentId: string) => {
    setConnectionStatus(prev => ({ ...prev, [instrumentId]: 'connecting' }));
    try {
      await connectDeviceById(instrumentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect device');
    } finally {
      setConnectionStatus(prev => ({ ...prev, [instrumentId]: null }));
    }
  };

  const [connectingAll, setConnectingAll] = useState(false);

  const handleConnectAll = async () => {
    const disconnected = devices.filter((d) => !d.connected);
    if (disconnected.length === 0) return;
    setConnectingAll(true);
    setConnectionStatus((prev) => {
      const next = { ...prev };
      disconnected.forEach((d) => { next[d.id] = 'connecting'; });
      return next;
    });
    const results = await Promise.allSettled(disconnected.map((d) => connectDeviceById(d.id)));
    const failures = results.filter((r) => r.status === 'rejected').length;
    if (failures > 0) {
      setError(`Failed to connect ${failures} of ${disconnected.length} instrument(s)`);
    }
    setConnectionStatus((prev) => {
      const next = { ...prev };
      disconnected.forEach((d) => { next[d.id] = null; });
      return next;
    });
    setConnectingAll(false);
  };

  const handleDisconnect = async (instrumentId: string) => {
    setConnectionStatus(prev => ({ ...prev, [instrumentId]: 'disconnecting' }));
    try {
      await disconnectDevice(instrumentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect device');
    } finally {
      setConnectionStatus(prev => ({ ...prev, [instrumentId]: null }));
    }
  };

  const getInstrumentIcon = (inst: { kind?: string; dimensionality?: string }) => {
    if (inst.kind === 'detector') {
      if (inst.dimensionality === '0D') return Gauge;
      if (inst.dimensionality === '1D') return Activity;
      if (inst.dimensionality === '2D') return Camera;
    }
    if (inst.kind === 'motor') return Move3D;
    if (inst.kind === 'source') return Radio;
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

  // Screen icon: launch the live instrument UI. Inside the Qt desktop shell
  // this opens a real native PyQtGraph window as a separate OS window (see
  // qt_bridge.py -> launch_instrument.py -> instrument_window.py, which
  // fetches the instrument's real schema/data from the backend by id — no
  // fake/simulated data). In a plain browser tab there's no Qt process to
  // open a window in, so fall back to the in-app live view modal.
  const launchInstrumentQtWindow = (instrument: { id: string; name: string }) => {
    if (qtBridge?.isInQt() && typeof qtBridge.launchInstrumentUI === 'function') {
      try {
        qtBridge.launchInstrumentUI(instrument.id);
        return;
      } catch (err) {
        console.error('Error launching native Qt UI, falling back to in-app view:', err);
      }
    }
    showInstrumentUI(instrument.id);
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

  // Group by kind — anything not detector/motor/source (including unknown
  // future kinds) folds into Detectors rather than disappearing.
  const groups: Record<string, typeof devices> = {};
  for (const inst of devices) {
    const rawKind = inst.kind || 'detector';
    const kind = KIND_GROUPS[rawKind] ? rawKind : (KIND_ALIAS[rawKind] || 'detector');
    (groups[kind] ??= []).push(inst);
  }

  const renderCard = (instrument: (typeof devices)[number]) => {
    const Icon = getInstrumentIcon(instrument);
    const color = getDimensionalityColor(instrument.dimensionality);
    const liveValue = instrument.connected ? formatLiveValue(instrument.kind, liveValues[instrument.id]) : null;

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
          <div className="flex items-center justify-between flex-wrap gap-1">
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
            {instrument.status && instrument.status !== 'idle' && (
              <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                instrument.status === 'busy'
                  ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
                  : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
              }`}
                title={instrument.status === 'error' ? instrument.error : undefined}
              >
                {instrument.status === 'busy' ? (
                  <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Busy</>
                ) : (
                  <><AlertTriangle className="h-3 w-3 mr-1" /> Error</>
                )}
              </span>
            )}
          </div>

          {liveValue && (
            <div className="font-mono text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-900/40 rounded px-2 py-1">
              {liveValue}
            </div>
          )}

          {/* Control Buttons */}
          <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center space-x-1">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  launchInstrumentQtWindow(instrument);
                }}
                className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                title="Open live UI"
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
                    removeDevice(instrument.id);
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
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Instruments</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Loaded laboratory instruments ({devices.length})
            {activeInstrumentConfig && (
              <span className="ml-2 text-gray-400 dark:text-gray-500">· setup: {activeInstrumentConfig}</span>
            )}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {devices.some((d) => !d.connected) && (
            <button
              onClick={handleConnectAll}
              disabled={connectingAll}
              className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              {connectingAll ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Link className="h-4 w-4 mr-2" />
              )}
              Connect All
            </button>
          )}
          <button
            onClick={showUploadSetupModal}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <Upload className="h-4 w-4 mr-2" />
            Upload Setup
          </button>
          <button
            onClick={showDeviceModal}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
          >
            <Plus className="h-4 w-4 mr-2" />
            Connect Device
          </button>
        </div>
      </div>

      {devices.length === 0 && (
        <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-8 text-center">
          <p className="text-gray-600 dark:text-gray-400">No instruments in this setup yet.</p>
        </div>
      )}

      {KIND_ORDER.filter((kind) => groups[kind]?.length).map((kind) => {
        const { label, icon: GroupIcon } = KIND_GROUPS[kind];
        const list = groups[kind];
        return (
          <div key={kind}>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
              <GroupIcon className="h-5 w-5 mr-2 text-green-500" />
              {label} ({list.length})
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {list.map(renderCard)}
            </div>
          </div>
        );
      })}

      {/* Settings modal (gear icon) and live-view modal (screen icon) share the
          same selectedInstrumentId but are two independent windows. */}
      {ui.selectedInstrumentId && (() => {
        const selected = devices.find(d => d.id === ui.selectedInstrumentId);
        if (!selected) return null;
        const instrumentProps = {
          id: selected.id,
          name: selected.name,
          adapter_type: selected.adapter_type,
          kind: selected.kind || 'detector',
          dimensionality: (selected.dimensionality || '0D') as any,
          capabilities: selected.capabilities || [],
          connected: selected.connected,
          status: selected.status,
          error: selected.error,
          tags: selected.tags || [],
          connection_params: selected.connection_params || {},
          custom_settings: selected.custom_settings || {},
        };
        return (
          <>
            <InstrumentSettingsModal
              instrument={instrumentProps}
              isOpen={ui.showInstrumentSettings}
              onClose={hideInstrumentSettings}
            />
            <InstrumentUIModal
              instrument={instrumentProps}
              isOpen={ui.showInstrumentLiveView}
              onClose={hideInstrumentUI}
            />
          </>
        );
      })()}
    </div>
  );
}
