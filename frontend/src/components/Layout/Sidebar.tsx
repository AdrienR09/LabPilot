import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useLabPilotStore } from '@/store';
import {
  LayoutDashboard,
  Cpu,
  GitBranch,
  MessageSquare,
  Database,
  Settings,
  Activity,
  AlertCircle,
  Network,
} from 'lucide-react';
import clsx from 'clsx';

const navigation = [
  {
    name: 'Dashboard',
    href: '/',
    icon: LayoutDashboard,
  },
  {
    name: 'Devices',
    href: '/devices',
    icon: Cpu,
  },
  {
    name: 'Workflows',
    href: '/workflows',
    icon: GitBranch,
  },
  {
    name: 'Flow Chart',
    href: '/flow',
    icon: Network,
  },
  {
    name: 'AI Assistant',
    href: '/ai',
    icon: MessageSquare,
  },
  {
    name: 'Data',
    href: '/data',
    icon: Database,
  },
  {
    name: 'Settings',
    href: '/settings',
    icon: Settings,
  },
];

export default function Sidebar() {
  const location = useLocation();
  const { devices, session } = useLabPilotStore();

  // Get session status
  const sessionStatus = session?.isConnected ? session : null;

  // Get recent events for activity indicator (fallback to empty array)
  const recentEvents: any[] = [];
  const hasErrors = false;

  return (
    <div className="flex flex-col h-full">
      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-2">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          const Icon = item.icon;

          return (
            <NavLink
              key={item.name}
              to={item.href}
              className={clsx(
                'flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors',
                isActive
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'
                  : 'text-gray-700 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-700'
              )}
            >
              <Icon
                size={20}
                className={clsx(
                  'mr-3',
                  isActive
                    ? 'text-blue-700 dark:text-blue-300'
                    : 'text-gray-500 dark:text-gray-400'
                )}
              />
              {item.name}

              {/* Badge indicators */}
              {item.name === 'Devices' && devices.length > 0 && (
                <span className="ml-auto bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-300 text-xs px-2 py-1 rounded-full">
                  {devices.filter(d => d.connected).length}
                </span>
              )}

              {item.name === 'AI Assistant' && sessionStatus?.aiAvailable && (
                <span className="ml-auto w-2 h-2 bg-green-500 rounded-full" />
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* System status */}
      <div className="px-4 pb-4 border-t border-gray-200 dark:border-gray-700">
        <div className="mt-4 space-y-3">
          {/* Connection status */}
          <div className="flex items-center text-sm">
            <div className={clsx(
              'w-2 h-2 rounded-full mr-2',
              sessionStatus ? 'bg-green-500' : 'bg-red-500'
            )} />
            <span className="text-gray-600 dark:text-gray-400">
              {sessionStatus ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          {/* Activity indicator */}
          {recentEvents.length > 0 && (
            <div className="flex items-center text-sm">
              <Activity
                size={16}
                className={clsx(
                  'mr-2',
                  hasErrors ? 'text-red-500' : 'text-green-500'
                )}
              />
              <span className="text-gray-600 dark:text-gray-400">
                {recentEvents.length} recent events
              </span>
              {hasErrors && (
                <AlertCircle size={14} className="ml-1 text-red-500" />
              )}
            </div>
          )}

          {/* Device summary */}
          {sessionStatus && (
            <div className="text-xs text-gray-500 dark:text-gray-500">
              Session: {sessionStatus.sessionId?.slice(0, 8) || 'unknown'}...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}