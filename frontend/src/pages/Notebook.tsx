import React from 'react';
import JupyterFrame from '@/components/JupyterFrame';

export default function Notebook() {
  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Notebook</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          A Jupyter notebook with a Python kernel already connected to this session's
          instruments and workflows as <code>lp</code>.
        </p>
      </div>
      <div className="flex-1 min-h-0 bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
        <JupyterFrame mode="notebook" />
      </div>
    </div>
  );
}
