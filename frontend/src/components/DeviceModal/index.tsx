import React, { useEffect, useMemo, useState } from 'react';
import { Search, X, ChevronDown, ChevronRight, AlertTriangle, FolderSearch, Check } from 'lucide-react';
import { useLabPilotStore } from '@/store';
import { locateVendorLibrary } from '@/api';
import type { CatalogEntry, VendorLibraryLocation } from '@/api';
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
  // An NI card is not reached by an address: DAQmx knows it by the name
  // NI-MAX gave it. What has to be said instead is which card it is and what
  // is plugged into which terminal — see instruments/NI/channels.py for the
  // one-line channel syntax, which exists so the wiring fits in one field.
  ni_daqmx: {
    label: 'NI-DAQmx device',
    fields: [
      { name: 'device', dtype: 'str', label: 'NI-MAX device name', default: 'Dev1' },
      { name: 'model', dtype: 'str', label: 'Card model', default: 'PCIe-6363' },
      { name: 'channels', dtype: 'str', label: 'Channels (name=terminal, comma separated)', default: 'x=ao0, y=ao1, apd=ctr0/pfi8' },
    ],
  },
  // An R-Series card is an FPGA: what it does is whatever gateware was
  // compiled onto it, so the bitfile is the real setting. Blank is a
  // first-class choice — the pulsed measurement then picks the image its
  // sequence needs from ~/.labpilot/config/ni_rseries.toml.
  ni_fpga: {
    label: 'NI R-Series (FPGA)',
    fields: [
      { name: 'resource', dtype: 'str', label: 'RIO resource name', default: 'RIO0' },
      { name: 'model', dtype: 'str', label: 'Card model', default: 'generic' },
      { name: 'bitfile', dtype: 'str', label: 'Bitfile (.lvbitx; blank = chosen from the library)' },
    ],
  },
  ocean_optics: {
    label: 'Ocean Optics (USB)',
    fields: [
      { name: 'serial_number', dtype: 'str', label: 'Serial number (blank = first found)' },
      { name: 'model', dtype: 'str', label: 'Model (blank = ask the device)' },
    ],
  },
  // Reached over the network, but by an address its constructor calls
  // `resource` rather than a host/port pair — so not the `tcp` method,
  // whose fields the adapter would discard.
  hostname: {
    label: 'Hostname / IP address',
    fields: [{ name: 'resource', dtype: 'str', label: 'Hostname or IP address', default: '192.168.1.100' }],
  },
  // A PCI card with no address: spinapi selects it by index. The clock rate
  // and channel count decide what a sequence compiles to, so they belong in
  // the same form.
  spincore: {
    label: 'SpinCore board',
    fields: [
      { name: 'board', dtype: 'int', label: 'Board index', default: 0 },
      { name: 'clock_mhz', dtype: 'float', label: 'Clock (MHz)', default: 500.0 },
      { name: 'channels', dtype: 'int', label: 'Digital channels', default: 24 },
    ],
  },
  // A library that comes with the manufacturer's driver installation and has
  // no PyPI package. Blank means "search the usual places", which is what
  // works on a standard installation — hence no default and the Find button
  // below, which asks the backend where it actually is.
  vendor_library: {
    label: 'Vendor library (DLL)',
    fields: [{ name: 'library', dtype: 'str', label: 'Library path — blank to search the default locations' }],
  },
  none: { label: 'No connection (mock/simulated)', fields: [] },
};

// The field that the Find button fills in. Named rather than inferred so the
// button appears only beside the control it can actually complete.
const LIBRARY_FIELD = 'library';

export function DeviceModal({ isOpen }: DeviceModalProps) {
  const { catalog, catalogLoading, loadCatalog, createDeviceFromCatalog, devicesLoading, devicesError, hideDeviceModal } = useLabPilotStore();

  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<CatalogEntry | null>(null);
  const [customName, setCustomName] = useState('');
  const [connectionMethod, setConnectionMethod] = useState('');
  const [connectionFields, setConnectionFields] = useState<Record<string, string>>({});
  const [collapsedTypes, setCollapsedTypes] = useState<Set<string>>(new Set());
  const [library, setLibrary] = useState<VendorLibraryLocation | null>(null);
  const [librarySearching, setLibrarySearching] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  // Asking the backend where the DLL is. Its own candidate list is the one
  // searched, so a hit here is where a connect will load from. On success the
  // path is written into the field: the point is to save the typing, and a
  // found path that still has to be copied by hand saves none of it.
  const findLibrary = async () => {
    if (!selected) return;
    setLibrarySearching(true);
    setLibraryError(null);
    setLibrary(null);
    try {
      const found = await locateVendorLibrary(selected.adapter_key);
      setLibrary(found);
      if (found.found) {
        setConnectionFields((prev) => ({ ...prev, [LIBRARY_FIELD]: found.path }));
      }
    } catch (error) {
      setLibraryError(error instanceof Error ? error.message : String(error));
    } finally {
      setLibrarySearching(false);
    }
  };

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

  const clearLibrarySearch = () => {
    setLibrary(null);
    setLibraryError(null);
  };

  const handleSelect = (item: CatalogEntry) => {
    setSelected(item);
    setCustomName(item.display_name);
    clearLibrarySearch();
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
    clearLibrarySearch();
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
                    Instrument catalog comes from the backend — start it with <code>labpilot app</code> to browse and add devices.
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
                <div className="flex gap-2">
                  <input
                    type={field.dtype === 'str' ? 'text' : 'number'}
                    step={field.dtype === 'float' ? 'any' : undefined}
                    value={connectionFields[field.name] ?? ''}
                    onChange={(e) => setConnectionFields((prev) => ({ ...prev, [field.name]: e.target.value }))}
                    placeholder={field.default !== undefined ? String(field.default) : ''}
                    className="flex-1 min-w-0 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  {field.name === LIBRARY_FIELD && (
                    <button
                      type="button"
                      onClick={findLibrary}
                      disabled={librarySearching}
                      title="Look for the library in the places this instrument's driver installs it"
                      className="shrink-0 inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                    >
                      <FolderSearch className="w-4 h-4" />
                      {librarySearching ? 'Searching…' : 'Find'}
                    </button>
                  )}
                </div>

                {field.name === LIBRARY_FIELD && libraryError && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                    Could not search: {libraryError}
                  </p>
                )}

                {field.name === LIBRARY_FIELD && library && (
                  <div
                    className={clsx(
                      'mt-2 rounded-md border px-3 py-2 text-xs',
                      // A library found but of the wrong word size is a
                      // failure, not a success: it cannot be loaded. Colouring
                      // it green because a file turned up would be a lie.
                      library.found && !library.mismatched
                        ? 'border-green-300 bg-green-50 text-green-800 dark:border-green-700 dark:bg-green-900/30 dark:text-green-200'
                        : 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
                    )}
                  >
                    <div className="flex items-start gap-1.5">
                      {library.found && !library.mismatched ? (
                        <Check className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                      )}
                      <span>{library.message}</span>
                    </div>
                    {library.found && library.architecture && (
                      <p className="mt-1 pl-5 opacity-80">
                        {library.architecture} library, {library.interpreter} Python.
                      </p>
                    )}
                    {!library.found && library.searched.length > 0 && (
                      <details className="mt-1.5 pl-5">
                        <summary className="cursor-pointer opacity-80">
                          Where it looked ({library.searched.length})
                        </summary>
                        <ul className="mt-1 space-y-0.5 font-mono break-all opacity-80">
                          {library.searched.map((place) => (
                            <li key={place}>{place}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                )}
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
