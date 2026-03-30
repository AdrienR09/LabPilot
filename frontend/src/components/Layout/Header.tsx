import React from 'react';
import { useLabPilotStore } from '@/store';
import {
  Menu,
  Moon,
  Sun,
  Zap,
  AlertTriangle,
  CheckCircle,
  Settings,
} from 'lucide-react';
import clsx from 'clsx';

export default function Header() {
  const {
    sessionStatus,
    ui,
    setSidebarOpen,
    setTheme,
    preferences,
  } = useLabPilotStore();

  const toggleSidebar = () => setSidebarOpen(!ui.sidebarOpen);
  const toggleTheme = () => setTheme(preferences.theme === 'dark' ? 'light' : 'dark');

  return (
    <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between px-4 py-3">
        {/* Left side - Logo and navigation */}
        <div className="flex items-center space-x-4">
          <button
            onClick={toggleSidebar}
            className="p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle sidebar"
          >
            <Menu size={20} />
          </button>

          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <Zap className="h-8 w-8 text-blue-600 dark:text-blue-400" />
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                LabPilot
              </h1>
            </div>

            {/* Status indicator */}
            {sessionStatus && (
              <div className="flex items-center space-x-2 text-sm">
                <div className="flex items-center space-x-1">
                  <CheckCircle size={16} className="text-green-500" />
                  <span className="text-gray-600 dark:text-gray-300">Connected</span>
                </div>

                <div className="w-px h-4 bg-gray-300 dark:bg-gray-600" />

                <span className="text-gray-600 dark:text-gray-300">
                  {sessionStatus.devices_connected} devices
                </span>

                {sessionStatus.ai_available && (
                  <>
                    <div className="w-px h-4 bg-gray-300 dark:bg-gray-600" />
                    <div className="flex items-center space-x-1">
                      <div className="w-2 h-2 bg-green-500 rounded-full" />
                      <span className="text-gray-600 dark:text-gray-300">AI</span>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right side - Actions */}
        <div className="flex items-center space-x-2">
          {/* Loading indicator */}
          {ui.loading && (
            <div className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-300">
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-600 border-t-transparent" />
              <span>Loading...</span>
            </div>
          )}

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className={clsx(
              'p-2 rounded-md transition-colors',
              'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200',
              'hover:bg-gray-100 dark:hover:bg-gray-700'
            )}
            aria-label="Toggle theme"
          >
            {preferences.theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
          </button>

          {/* Settings */}
          <button
            className={clsx(
              'p-2 rounded-md transition-colors',
              'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200',
              'hover:bg-gray-100 dark:hover:bg-gray-700'
            )}
            aria-label="Settings"
          >
            <Settings size={20} />
          </button>
        </div>
      </div>

      {/* Notifications bar */}
      {ui.notifications.length > 0 && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800 px-4 py-2">
          <div className="flex items-center space-x-2">
            <AlertTriangle size={16} className="text-yellow-600 dark:text-yellow-400" />
            <span className="text-sm text-yellow-800 dark:text-yellow-200">
              {ui.notifications.length} notification{ui.notifications.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      )}
    </header>
  );
}