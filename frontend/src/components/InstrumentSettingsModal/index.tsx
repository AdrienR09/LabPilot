import React, { useEffect, useState } from 'react';
import { X, Settings as SettingsIcon, Gauge, Activity, Camera, Move3D, Radio, AlertTriangle, RefreshCw, Plug } from 'lucide-react';
import { DashboardInstrument } from '@/api';
import {
  getInstrumentSchema,
  readInstrumentData,
  writeInstrumentSettings,
  updateInstrumentConnection,
  getInstrumentUIPrefs,
  getInstrumentUIPrefsSchema,
  writeInstrumentUIPrefs,
  type InstrumentSchema,
  type InstrumentUIPrefs,
  type InstrumentUIPrefsSchema,
} from '@/api';
import { useLabPilotStore } from '@/store';

interface InstrumentSettingsModalProps {
  instrument: DashboardInstrument | null;
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Instrument configuration only — no live data. For monitoring/live view,
 * see InstrumentUIModal (opened from the screen/Monitor icon instead).
 *
 * Renders whatever this specific instrument actually declares in its
 * DeviceSchema (settable/readable/units/limits) — not a fixed generic form.
 */
export function InstrumentSettingsModal({ instrument, isOpen, onClose }: InstrumentSettingsModalProps) {
  const loadDevices = useLabPilotStore((s) => s.loadDevices);
  const [schema, setSchema] = useState<InstrumentSchema | null>(null);
  const [values, setValues] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [connectionAddress, setConnectionAddress] = useState('');
  const [connectionSaving, setConnectionSaving] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connectionSaved, setConnectionSaved] = useState(false);
  const [uiPrefs, setUIPrefs] = useState<InstrumentUIPrefs>({});
  const [uiPrefsSaving, setUIPrefsSaving] = useState(false);
  const [uiPrefsSchema, setUIPrefsSchema] = useState<InstrumentUIPrefsSchema>({});

  useEffect(() => {
    if (!isOpen || !instrument) return;
    setSchema(null);
    setError(null);
    setSaveMessage(null);
    setLoading(true);
    // DeviceModal writes the same value into resource/port/address at
    // creation time — pick whichever is set to show one address field.
    const params = instrument.connection_params || {};
    setConnectionAddress(String(params.resource ?? params.address ?? params.port ?? ''));
    setConnectionError(null);
    setConnectionSaved(false);

    getInstrumentSchema(instrument.id)
      .then((s) => {
        setSchema(s);
        if (instrument.connected) {
          return readInstrumentData(instrument.id).then((data) => setValues(data));
        }
        // Disconnected: nothing to read live, so show whatever config was
        // last saved/staged — it'll be sent to the instrument the moment
        // it connects (see write_instrument_settings on the backend).
        setValues({ ...(instrument.custom_settings || {}) });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load instrument schema'))
      .finally(() => setLoading(false));

    getInstrumentUIPrefs(instrument.id)
      .then((p) => setUIPrefs(p || {}))
      .catch(() => setUIPrefs({}));

    getInstrumentUIPrefsSchema(instrument.id)
      .then((s) => setUIPrefsSchema(s || {}))
      .catch(() => setUIPrefsSchema({}));
  }, [isOpen, instrument?.id]);

  if (!isOpen || !instrument) return null;

  const handleUpdateConnection = async () => {
    setConnectionSaving(true);
    setConnectionError(null);
    setConnectionSaved(false);
    const params = connectionAddress
      ? { resource: connectionAddress, port: connectionAddress, address: connectionAddress }
      : {};
    try {
      await updateInstrumentConnection(instrument.id, params);
      await loadDevices();
      setConnectionSaved(true);
    } catch (e) {
      setConnectionError(e instanceof Error ? e.message : 'Failed to update connection');
    } finally {
      setConnectionSaving(false);
    }
  };

  const handleUIPrefChange = async (patch: InstrumentUIPrefs) => {
    const next = { ...uiPrefs, ...patch };
    setUIPrefs(next);
    setUIPrefsSaving(true);
    try {
      await writeInstrumentUIPrefs(instrument.id, next);
    } catch {
      // Best-effort — a failed save here just means the toggle reverts
      // to its old behavior next time the instrument's window opens.
    } finally {
      setUIPrefsSaving(false);
    }
  };

  const getInstrumentIcon = () => {
    if (instrument.kind === 'detector') {
      if (instrument.dimensionality === '0D') return Gauge;
      if (instrument.dimensionality === '1D') return Activity;
      if (instrument.dimensionality === '2D') return Camera;
    }
    if (instrument.kind === 'motor') return Move3D;
    if (instrument.kind === 'source') return Radio;
    return SettingsIcon;
  };
  const Icon = getInstrumentIcon();

  const handleRefresh = () => {
    if (!instrument.connected) return;
    setLoading(true);
    readInstrumentData(instrument.id)
      .then((data) => setValues(data))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to read current values'))
      .finally(() => setLoading(false));
  };

  const handleApply = async () => {
    if (!schema) return;
    setSaving(true);
    setError(null);
    setSaveMessage(null);
    const payload: Record<string, any> = {};
    for (const name of configNames(schema)) {
      if (values[name] !== undefined) payload[name] = values[name];
    }
    try {
      const result = await writeInstrumentSettings(instrument.id, payload);
      setSaveMessage(result.message || 'Applied.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to apply settings');
    } finally {
      setSaving(false);
    }
  };

  // Params that are both readable AND settable (e.g. an actuator's
  // "position", a source's "output") are live controls manipulated during
  // operation — those live in the live view window (screen icon), not here.
  // Only settable-but-not-readable params (connection/config knobs like
  // "integration_time_ms" or "velocity") are configuration, edited here.
  function configNames(s: InstrumentSchema): string[] {
    return Object.keys(s.settable).filter((n) => !s.readable[n]);
  }

  const settableNames = schema ? configNames(schema) : [];
  const liveControlNames = schema
    ? Object.keys(schema.settable).filter((n) => !!schema.readable[n])
    : [];
  const readOnlyNames = schema
    ? Object.keys(schema.readable).filter((n) => !schema.settable[n])
    : [];

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700">
              <Icon className="h-6 w-6 text-gray-600 dark:text-gray-300" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                {instrument.name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Settings • {instrument.adapter_type}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {!instrument.connected && (
            <div className="p-3 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 rounded text-sm flex items-center">
              <AlertTriangle className="h-4 w-4 mr-2 flex-shrink-0" />
              Not connected — configuration below is still editable and will be sent to the instrument as soon as it connects.
            </div>
          )}

          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded text-sm">
              {error}
            </div>
          )}

          <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center mb-3">
              <Plug className="h-4 w-4 mr-2" />
              Connection
            </h3>
            {instrument.connected && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">
                Updating this disconnects the instrument first — the adapter is re-created against the new address.
              </p>
            )}
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
              Connection Address <span className="text-gray-400 font-normal">(VISA resource, serial port, IP, ... — leave blank for mock/simulated instruments)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={connectionAddress}
                onChange={(e) => setConnectionAddress(e.target.value)}
                placeholder="e.g. GPIB::24 or COM3 or 192.168.1.10"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleUpdateConnection}
                disabled={connectionSaving}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 text-white rounded-md text-sm font-medium transition-colors whitespace-nowrap"
              >
                {connectionSaving ? 'Updating…' : 'Update'}
              </button>
            </div>
            {connectionError && (
              <p className="mt-2 text-xs text-red-600 dark:text-red-400">{connectionError}</p>
            )}
            {connectionSaved && !connectionError && (
              <p className="mt-2 text-xs text-green-600 dark:text-green-400">Connection updated.</p>
            )}
          </div>

          {Object.keys(uiPrefsSchema).length > 0 && (
            <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
              <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center mb-3">
                <Move3D className="h-4 w-4 mr-2" />
                Native UI
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Changes apply the next time this instrument's native window is opened.
              </p>
              {/* Rendered generically from the backend's declared prefs
                  (core/config/instrument_ui_prefs.py) — a new component's
                  preference shows up here with no new JSX, as long as it
                  fits an existing `kind` (currently just "bool"). */}
              <div className="space-y-2">
                {Object.entries(uiPrefsSchema).map(([name, spec]) =>
                  spec.kind === 'bool' ? (
                    <label key={name} className="flex items-center text-sm text-gray-700 dark:text-gray-300">
                      <input
                        type="checkbox"
                        checked={uiPrefs[name] ?? spec.default ?? false}
                        disabled={uiPrefsSaving}
                        onChange={(e) => handleUIPrefChange({ [name]: e.target.checked })}
                        className="mr-2"
                      />
                      {spec.label}
                    </label>
                  ) : null
                )}
              </div>
            </div>
          )}

          {loading && !schema && (
            <div className="flex items-center justify-center py-8 text-gray-400">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          )}

          {schema && (
            <>
              {settableNames.length === 0 && readOnlyNames.length === 0 && liveControlNames.length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  This instrument declares no readable or settable parameters.
                </p>
              )}

              {liveControlNames.length > 0 && (
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded text-sm">
                  {liveControlNames.join(', ')} {liveControlNames.length === 1 ? 'is' : 'are'} controlled from the
                  live view (screen icon) — it changes during operation, so it isn't a config setting.
                </div>
              )}

              {settableNames.length > 0 && (
                <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center">
                      <SettingsIcon className="h-4 w-4 mr-2" />
                      Configuration
                    </h3>
                    <button
                      onClick={handleRefresh}
                      disabled={!instrument.connected || loading}
                      className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 disabled:opacity-40"
                      title="Refresh current values"
                    >
                      <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                  </div>
                  <div className="space-y-3">
                    {settableNames.map((name) => {
                      const unit = schema.units[name];
                      const limits = schema.limits[name];
                      return (
                        <div key={name}>
                          <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                            {name}{unit ? ` (${unit})` : ''}
                            {limits && (
                              <span className="text-gray-400 dark:text-gray-500"> · {limits[0]}–{limits[1]}</span>
                            )}
                          </label>
                          <input
                            type="number"
                            value={values[name] ?? ''}
                            min={limits?.[0]}
                            max={limits?.[1]}
                            onChange={(e) => setValues({ ...values, [name]: parseFloat(e.target.value) })}
                            className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          />
                        </div>
                      );
                    })}
                  </div>
                  <button
                    onClick={handleApply}
                    disabled={saving}
                    className="mt-4 w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 text-white rounded-md text-sm font-medium transition-colors"
                  >
                    {saving ? 'Applying…' : instrument.connected ? 'Apply' : 'Save (applies on connect)'}
                  </button>
                  {saveMessage && (
                    <p className="mt-2 text-xs text-green-600 dark:text-green-400">{saveMessage}</p>
                  )}
                </div>
              )}

              {readOnlyNames.length > 0 && (
                <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                    Read-only
                  </h3>
                  <div className="space-y-2">
                    {readOnlyNames.map((name) => (
                      <div key={name} className="flex justify-between text-sm">
                        <span className="text-gray-600 dark:text-gray-400">
                          {name}{schema.units[name] ? ` (${schema.units[name]})` : ''}
                        </span>
                        <span className="text-gray-900 dark:text-white font-mono">
                          {values[name] !== undefined ? String(values[name]) : '—'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {schema.tags.length > 0 && (
                <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Tags</h3>
                  <div className="flex flex-wrap gap-2">
                    {schema.tags.map((tag, index) => (
                      <span
                        key={index}
                        className="inline-flex items-center px-2 py-1 rounded-md text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-md font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
