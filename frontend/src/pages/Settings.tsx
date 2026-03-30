import React, { useState, useEffect } from 'react';
import { useLabPilotStore } from '@/store';
import { Save, RotateCcw, Sun, Moon, Monitor } from 'lucide-react';
import clsx from 'clsx';

export default function Settings() {
  const { preferences, setTheme, ui } = useLabPilotStore();

  // Local settings state
  const [localSettings, setLocalSettings] = useState({
    theme: preferences.theme || 'dark',
    autoTheme: localStorage.getItem('labpilot-auto-theme') === 'true',
    sidebarCollapse: localStorage.getItem('labpilot-sidebar-collapse') === 'true',
    defaultGraphType: localStorage.getItem('labpilot-default-graph-type') || '1d',
    dataFormat: localStorage.getItem('labpilot-data-format') || 'decimal',
    backendUrl: localStorage.getItem('labpilot-backend-url') || 'http://localhost:8000',
    backendTimeout: parseInt(localStorage.getItem('labpilot-backend-timeout') || '5000', 10),
    autoSaveInterval: parseInt(localStorage.getItem('labpilot-auto-save-interval') || '300000', 10),
    sessionRetention: parseInt(localStorage.getItem('labpilot-session-retention') || '30', 10),
  });

  const [saved, setSaved] = useState(false);
  const [changed, setChanged] = useState(false);

  const handleChange = (key: string, value: any) => {
    setLocalSettings(prev => ({ ...prev, [key]: value }));
    setChanged(true);
    setSaved(false);
  };

  const handleSave = async () => {
    // Save to localStorage
    localStorage.setItem('labpilot-theme', localSettings.theme);
    localStorage.setItem('labpilot-auto-theme', String(localSettings.autoTheme));
    localStorage.setItem('labpilot-sidebar-collapse', String(localSettings.sidebarCollapse));
    localStorage.setItem('labpilot-default-graph-type', localSettings.defaultGraphType);
    localStorage.setItem('labpilot-data-format', localSettings.dataFormat);
    localStorage.setItem('labpilot-backend-url', localSettings.backendUrl);
    localStorage.setItem('labpilot-backend-timeout', String(localSettings.backendTimeout));
    localStorage.setItem('labpilot-auto-save-interval', String(localSettings.autoSaveInterval));
    localStorage.setItem('labpilot-session-retention', String(localSettings.sessionRetention));

    // Apply theme immediately
    setTheme(localSettings.theme as 'dark' | 'light');

    setChanged(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const handleReset = () => {
    setLocalSettings({
      theme: 'dark',
      autoTheme: false,
      sidebarCollapse: false,
      defaultGraphType: '1d',
      dataFormat: 'decimal',
      backendUrl: 'http://localhost:8000',
      backendTimeout: 5000,
      autoSaveInterval: 300000,
      sessionRetention: 30,
    });
    setChanged(true);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">Customize your LabPilot experience</p>
      </div>

      {/* Saved notification */}
      {saved && (
        <div className="p-4 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-lg flex items-center gap-3">
          <div className="w-5 h-5">✓</div>
          <span>Settings saved successfully!</span>
        </div>
      )}

      {/* Theme Settings */}
      <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Sun className="w-5 h-5 text-yellow-500" />
            Theme Settings
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Customize appearance</p>
        </div>

        {/* Theme Selection */}
        <div className="space-y-3">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Theme</label>
          <div className="grid grid-cols-3 gap-3">
            {[
              { value: 'light', label: 'Light', icon: Sun },
              { value: 'dark', label: 'Dark', icon: Moon },
              { value: 'auto', label: 'Auto', icon: Monitor },
            ].map(theme => (
              <button
                key={theme.value}
                onClick={() => handleChange('theme', theme.value)}
                className={clsx(
                  'px-4 py-3 rounded-lg border-2 transition-all flex items-center gap-2 justify-center',
                  localSettings.theme === theme.value
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300'
                )}
              >
                <theme.icon className="w-4 h-4" />
                {theme.label}
              </button>
            ))}
          </div>
        </div>

        {/* Auto Theme */}
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={localSettings.autoTheme}
              onChange={(e) => handleChange('autoTheme', e.target.checked)}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Auto-switch theme based on system preference
            </span>
          </label>
        </div>
      </section>

      {/* UI Preferences */}
      <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">UI Preferences</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Customize interface behavior</p>
        </div>

        {/* Sidebar Collapse */}
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={localSettings.sidebarCollapse}
              onChange={(e) => handleChange('sidebarCollapse', e.target.checked)}
              className="w-4 h-4 rounded"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Collapse sidebar by default
            </span>
          </label>
        </div>

        {/* Default Graph Type */}
        <div className="pt-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Default Graph Type
          </label>
          <select
            value={localSettings.defaultGraphType}
            onChange={(e) => handleChange('defaultGraphType', e.target.value)}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          >
            <option value="0d">0D (Single Value)</option>
            <option value="1d">1D (Line Plot)</option>
            <option value="2d">2D (Image/Heatmap)</option>
          </select>
        </div>

        {/* Data Format */}
        <div className="pt-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Data Format
          </label>
          <select
            value={localSettings.dataFormat}
            onChange={(e) => handleChange('dataFormat', e.target.value)}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          >
            <option value="decimal">Decimal (2.5)</option>
            <option value="scientific">Scientific (2.5e+0)</option>
            <option value="percentage">Percentage (250%)</option>
          </select>
        </div>
      </section>

      {/* Backend Settings */}
      <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Backend Configuration</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Configure server connection settings</p>
        </div>

        {/* Backend URL */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Backend Server URL
          </label>
          <input
            type="text"
            value={localSettings.backendUrl}
            onChange={(e) => handleChange('backendUrl', e.target.value)}
            placeholder="http://localhost:8000"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Leave empty to use default</p>
        </div>

        {/* Backend Timeout */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Backend Timeout (ms)
          </label>
          <input
            type="number"
            value={localSettings.backendTimeout}
            onChange={(e) => handleChange('backendTimeout', parseInt(e.target.value, 10))}
            min="1000"
            max="60000"
            step="1000"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">How long to wait before timing out requests</p>
        </div>
      </section>

      {/* Session Settings */}
      <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Session Manager</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage session persistence</p>
        </div>

        {/* Auto-save Interval */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Auto-save Interval (seconds)
          </label>
          <input
            type="number"
            value={localSettings.autoSaveInterval / 1000}
            onChange={(e) => handleChange('autoSaveInterval', parseInt(e.target.value, 10) * 1000)}
            min="10"
            max="3600"
            step="10"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">How often to automatically save session state</p>
        </div>

        {/* Session Retention */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Session History Retention (days)
          </label>
          <input
            type="number"
            value={localSettings.sessionRetention}
            onChange={(e) => handleChange('sessionRetention', parseInt(e.target.value, 10))}
            min="1"
            max="365"
            step="1"
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">How long to keep saved sessions</p>
        </div>
      </section>

      {/* Action Buttons */}
      <div className="flex gap-3 pb-6">
        <button
          onClick={handleSave}
          disabled={!changed}
          className={clsx(
            'px-6 py-3 rounded-lg font-medium transition-colors flex items-center gap-2',
            changed
              ? 'bg-blue-600 hover:bg-blue-700 text-white'
              : 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed'
          )}
        >
          <Save className="w-4 h-4" />
          Save Settings
        </button>
        <button
          onClick={handleReset}
          className="px-6 py-3 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 font-medium transition-colors flex items-center gap-2"
        >
          <RotateCcw className="w-4 h-4" />
          Reset to Defaults
        </button>
      </div>
    </div>
  );
}