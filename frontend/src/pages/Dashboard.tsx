import React from 'react';
import { Activity, Cpu, Zap, TrendingUp } from 'lucide-react';
import { useLabPilotStore } from '@/store';

export default function Dashboard() {
  const { sessionStatus, devices, workflows } = useLabPilotStore();

  const stats = [
    {
      name: 'Connected Devices',
      value: devices.filter(d => d.status === 'connected').length,
      icon: Cpu,
      change: '+4.5%',
      changeType: 'increase' as const,
    },
    {
      name: 'Active Workflows',
      value: workflows.filter(w => w.status === 'running').length,
      icon: Activity,
      change: '+2.1%',
      changeType: 'increase' as const,
    },
    {
      name: 'System Health',
      value: sessionStatus?.session_id ? 'Online' : 'Offline',
      icon: Zap,
      change: sessionStatus?.session_id ? 'Connected' : 'Disconnected',
      changeType: sessionStatus?.session_id ? 'increase' : 'decrease' as const,
    },
    {
      name: 'AI Status',
      value: sessionStatus?.ai_available ? 'Available' : 'Unavailable',
      icon: TrendingUp,
      change: sessionStatus?.ai_available ? 'Ready' : 'Offline',
      changeType: sessionStatus?.ai_available ? 'increase' : 'decrease' as const,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Laboratory automation system overview
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="bg-white dark:bg-gray-800 rounded-lg shadow p-6"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                  {stat.name}
                </p>
                <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                  {stat.value}
                </p>
              </div>
              <div className={`p-2 rounded-lg ${
                stat.changeType === 'increase'
                  ? 'bg-green-100 dark:bg-green-900'
                  : 'bg-red-100 dark:bg-red-900'
              }`}>
                <stat.icon className={`h-6 w-6 ${
                  stat.changeType === 'increase'
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400'
                }`} />
              </div>
            </div>
            <div className="mt-4">
              <span className={`text-sm font-medium ${
                stat.changeType === 'increase'
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}>
                {stat.change}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Recent Activity */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Recent Activity
          </h2>
        </div>
        <div className="p-6">
          <div className="space-y-4">
            <div className="flex items-center space-x-3">
              <div className="flex-shrink-0">
                <Activity className="h-5 w-5 text-green-500" />
              </div>
              <div className="flex-1">
                <p className="text-sm text-gray-900 dark:text-white">
                  LabPilot system initialized
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {new Date().toLocaleTimeString()}
                </p>
              </div>
            </div>

            {sessionStatus?.session_id && (
              <div className="flex items-center space-x-3">
                <div className="flex-shrink-0">
                  <Zap className="h-5 w-5 text-blue-500" />
                </div>
                <div className="flex-1">
                  <p className="text-sm text-gray-900 dark:text-white">
                    Connected to backend server
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Session ID: {sessionStatus.session_id}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}