import React from 'react';
import JupyterFrame from '@/components/JupyterFrame';

export default function Console() {
  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Console</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          An IPython terminal running inside the LabPilot package environment, with{' '}
          <code>lp</code> already connected to this session.
        </p>
      </div>
      <div className="flex-1 min-h-0 bg-black rounded-lg shadow overflow-hidden">
        <JupyterFrame mode="terminal" />
      </div>
    </div>
  );
}
