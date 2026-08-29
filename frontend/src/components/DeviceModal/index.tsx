import React, { useEffect, useMemo, useState } from 'react';
import { Search, X, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import { useLabPilotStore } from '@/store';
import type { CatalogEntry } from '@/api';
import clsx from 'clsx';

interface DeviceModalProps {
  isOpen: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  detector_0d: '0D Detectors',
  detector_1d: '1D Detectors',
  detector_2d: '2D Detectors (Cameras)',
  actuator_0d: '0D Actuators (Switches)',
  actuator_1d: '1D Actuators (Motors/Stages)',
  actuator_nd: 'Multi-axis Actuators',
  source: 'Sources',
  generic: 'Other',
};

// Mirrors src/instruments/connections.py's CONNECTION_METHODS — the field
// shape for each way an instrument can be reached, selected here instead
// of assumed from backend. Kept as a small frontend constant (like
// TYPE_LABELS above) rather than a new backend route, since this is
// stable UI metadata, not live state.
interface ConnectionField {
  name: string;
  dtype: 'str' | 'int' | 'float';
  label: string;
  default?: string | number;
}
const CONNECTION_METHODS: Record<string, { label: string; fields: ConnectionField[] }> = {
  visa: { label: 'VISA', fields: [{ name: 'resource', dtype: 'str', label: 'VISA resource string', default: 'GPIB::1' }] },
  serial: {
    label: 'Serial / COM port',
    fields: [
      { name: 'port', dtype: 'str', label: 'Serial port', default: 'COM3' },
      { name: 'baudrate', dtype: 'int', label: 'Baud rate', default: 9600 },
      { name: 'timeout', dtype: 'float', label: 'Timeout (s)', default: 1.0 },
    ],
  },
  tcp: {
    label: 'TCP/IP',
    fields: [
      { name: 'host', dtype: 'str', label: 'Host', default: '192.168.1.100' },
      { name: 'port', dtype: 'int', label: 'Port', default: 5025 },
    ],
  },
  usb_serial_number: { label: 'USB (serial number)', fields: [{ name: 'serial_number', dtype: 'str', label: 'Device serial number' }] },
  none: { label: 'No connection (mock/simulated)', fields: [] },
};

export function DeviceModal({ isOpen }: DeviceModalProps) {
  const { catalog, catalogLoading, loadCatalog, createDeviceFromCatalog, devicesLoading, devicesError, hideDeviceModal } = useLabPilotStore();

  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<CatalogEntry | null>(null);
  const [customName, setCustomName] = useState('');
  const [connectionMethod, setConnectionMethod] = useState('');
  const [connectionFields, setConnectionFields] = useState<Record<string, string>>({});
  const [collapsedTypes, setCollapsedTypes] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (isOpen && catalog.length === 0 && !catalogLoading) {
      loadCatalog();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Always the real backend catalog (285 verified instruments from
  // instruments/) — no local/fake fallback.
  const source: CatalogEntry[] = catalog;

  const filtered = useMemo(() => {
    const tokens = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (tokens.length === 0) return source;
    return source.filter(i => {
      const haystack = [i.manufacturer, i.model, i.display_name, i.adapter_key, ...i.tags]
        .join(' ')
        .toLowerCase();
      return tokens.every(t => haystack.includes(t));
    });
  }, [source, search]);

  const grouped = useMemo(() => {
    const groups: Record<string, CatalogEntry[]> = {};
    for (const item of filtered) {
      (groups[item.instrument_type] ??= []).push(item);
    }
    return groups;
  }, [filtered]);

  const toggleType = (type: string) => {
    setCollapsedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  };

  const handleSelect = (item: CatalogEntry) => {
    setSelected(item);
    setCustomName(item.display_name);
    const firstMethod = item.connection_types[0] || 'none';
    setConnectionMethod(firstMethod);
    const defaults: Record<string, string> = {};
    for (const field of CONNECTION_METHODS[firstMethod]?.fields || []) {
      if (field.default !== undefined) defaults[field.name] = String(field.default);
    }
    setConnectionFields(defaults);
  };

  const handleMethodChange = (method: string) => {
    setConnectionMethod(method);
    const defaults: Record<string, string> = {};
    for (const field of CONNECTION_METHODS[method]?.fields || []) {
      if (field.default !== undefined) defaults[field.name] = String(field.default);
    }
    setConnectionFields(defaults);
  };

  const handleCreate = async () => {
    if (!selected) return;
    const fieldSpecs = CONNECTION_METHODS[connectionMethod]?.fields || [];
    const connectionParams: Record<string, string | number> = {};
    for (const field of fieldSpecs) {
      const raw = connectionFields[field.name];
      if (raw === undefined || raw === '') continue;
      connectionParams[field.name] = field.dtype === 'str' ? raw : Number(raw);
    }
    try {
      await createDeviceFromCatalog(selected.adapter_key, {
        name: customName || selected.display_name,
        connectionParams,
      });
    } catch {
      // Failed — stay on this step with the form and error intact so the
      // user can fix (e.g. a missing connection address) and retry.
      return;
    }
    setSearch('');
    setSelected(null);
    setCustomName('');
    setConnectionMethod('');
    setConnectionFields({});
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Connect Device</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {catalogLoading ? 'Loading catalog…' : `${source.length} instruments available`}
            </p>
          </div>
          <button onClick={hideDeviceModal} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
            <X className="h-5 w-5" />
          </button>
        </div>

        {!selected ? (
          <>
            {/* Search */}
            <div className="px-6 pt-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  autoFocus
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by manufacturer, model, or tag (e.g. Keithley, camera, lock-in)"
                  className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>

            {devicesError && (
              <div className="mx-6 mt-3 p-2 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded text-sm">
                {devicesError}
              </div>
            )}

            {/* Results, organized by instrument type */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
              {!catalogLoading && source.length === 0 && (
                <div className="text-center py-8">
                  <AlertTriangle className="h-8 w-8 mx-auto text-amber-500 mb-2" />
                  <p className="text-sm text-gray-700 dark:text-gray-300 font-medium">Backend unreachable</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Instrument catalog comes from the backend — start it with <code>labpilot start</code> (or <code>./launch.sh</code>) to browse and add devices.
                  </p>
                </div>
              )}
              {source.length > 0 && Object.keys(grouped).length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                  No instruments match "{search}"
                </p>
              )}
              {Object.entries(grouped).map(([type, items]) => {
                const isCollapsed = collapsedTypes.has(type);
                return (
                  <div key={type}>
                    <button
                      onClick={() => toggleType(type)}
                      className="w-full flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2 hover:text-gray-700 dark:hover:text-gray-200"
                    >
                      {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      {TYPE_LABELS[type] || type} ({items.length})
                    </button>
                    {!isCollapsed && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {items.map((item) => (
                          <button
                            key={item.adapter_key}
                            onClick={() => handleSelect(item)}
                            className="text-left px-3 py-2 rounded-lg border-2 border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500 transition-colors"
                          >
                            <div className="text-sm font-medium text-gray-900 dark:text-white">
                              {item.manufacturer} {item.model}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                              {item.display_name}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          /* Confirm + connection details */
          <div className="p-6 space-y-4">
            <button
              onClick={() => setSelected(null)}
              className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              ← Back to search
            </button>

            {devicesError && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded text-sm">
                {devicesError}
              </div>
            )}

            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <div className="text-sm text-blue-700 dark:text-blue-300">
                {selected.manufacturer} • {TYPE_LABELS[selected.instrument_type] || selected.instrument_type}
              </div>
              <div className="text-lg font-semibold text-gray-900 dark:text-white">{selected.display_name}</div>
              <div className="text-xs text-gray-600 dark:text-gray-400">{selected.model} ({selected.adapter_key})</div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Device Name
              </label>
              <input
                type="text"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {selected.connection_types.length > 0 && connectionMethod !== 'none' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Connection Method
                </label>
                <select
                  value={connectionMethod}
                  onChange={(e) => handleMethodChange(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  {selected.connection_types.map((method) => (
                    <option key={method} value={method}>
                      {CONNECTION_METHODS[method]?.label || method}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {(CONNECTION_METHODS[connectionMethod]?.fields || []).map((field) => (
              <div key={field.name}>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {field.label}
                </label>
                <input
                  type={field.dtype === 'str' ? 'text' : 'number'}
                  step={field.dtype === 'float' ? 'any' : undefined}
                  value={connectionFields[field.name] ?? ''}
                  onChange={(e) => setConnectionFields((prev) => ({ ...prev, [field.name]: e.target.value }))}
                  placeholder={field.default !== undefined ? String(field.default) : ''}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            ))}

            {connectionMethod === 'none' && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                No connection parameters needed — this is a mock/simulated instrument.
              </p>
            )}

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setSelected(null)}
                disabled={devicesLoading}
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 font-medium disabled:opacity-50"
              >
                Back
              </button>
              <button
                onClick={handleCreate}
                disabled={devicesLoading || !customName}
                className={clsx(
                  'flex-1 px-4 py-2 rounded-md font-medium transition-colors flex items-center justify-center gap-2',
                  !devicesLoading && customName
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-400 cursor-not-allowed'
                )}
              >
                {devicesLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Adding...
                  </>
                ) : (
                  'Add Device'
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
