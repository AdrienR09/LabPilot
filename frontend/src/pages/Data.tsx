import React from 'react';
import { BarChart3, Database } from 'lucide-react';

export default function Data() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Data</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Analyze and visualize experimental data
        </p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Data Visualization
          </h2>
        </div>
        <div className="p-6">
          <div className="text-center py-8">
            <BarChart3 className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-sm font-medium text-gray-900 dark:text-white">
              Data visualization coming soon
            </h3>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              Advanced data analysis and plotting tools will be available here.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}