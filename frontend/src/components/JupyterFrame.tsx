import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { getJupyterStatus, startJupyter, JupyterStatus } from '@/api';

interface JupyterFrameProps {
  /** 'notebook' embeds the Jupyter file browser/notebook UI; 'terminal'
   * opens (and embeds) one IPython terminal session on the same server. */
  mode: 'notebook' | 'terminal';
}

// The Jupyter server (see core/jupyter_launcher.py) runs on its own
// dynamically-chosen port, separate from the LabPilot API's own
// host:port — so unlike every other page here, this one talks to
// `status.base_url` directly (its own origin) rather than through the
// `/api` proxy.
export default function JupyterFrame({ mode }: JupyterFrameProps) {
  const [status, setStatus] = useState<JupyterStatus | null>(null);
  const [iframeSrc, setIframeSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const boot = useCallback(async () => {
    setLoading(true);
    setError(null);
    setIframeSrc(null);
    try {
      let s = await getJupyterStatus();
      if (!s.running) {
        s = await startJupyter();
      }
      setStatus(s);
      if (mode === 'notebook') {
        setIframeSrc(`${s.base_url}/tree?token=${s.token}`);
      } else {
        const resp = await fetch(`${s.base_url}/api/terminals?token=${s.token}`, { method: 'POST' });
        if (!resp.ok) {
          throw new Error(`Failed to open a terminal session (HTTP ${resp.status})`);
        }
        const term = await resp.json();
        setIframeSrc(`${s.base_url}/terminals/${term.name}?token=${s.token}`);
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to reach the Jupyter server');
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    boot();
  }, [boot]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <p className="text-sm text-red-600 dark:text-red-400 mb-4">{error}</p>
        <button
          onClick={boot}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700"
        >
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  if (loading || !iframeSrc || !status) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <Loader2 size={28} className="animate-spin text-blue-600 dark:text-blue-400" />
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Starting the Jupyter {mode === 'notebook' ? 'notebook' : 'console'} server…
        </p>
      </div>
    );
  }

  return (
    <iframe
      key={iframeSrc}
      src={iframeSrc}
      title={mode === 'notebook' ? 'Jupyter Notebook' : 'IPython Console'}
      className="w-full h-full border-0 rounded-lg bg-white"
    />
  );
}
