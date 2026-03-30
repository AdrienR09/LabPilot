/**
 * Qt Bridge Test Component
 * Drop this into your React app to test Qt communication
 *
 * Usage:
 *   import QtBridgeTest from './components/QtBridgeTest';
 *   <QtBridgeTest />
 */

import { useState, useEffect } from 'react';
import { qtBridge, initQtBridge } from '../utils/qtBridge';

export default function QtBridgeTest() {
  const [isReady, setIsReady] = useState(false);
  const [instruments, setInstruments] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    // Initialize Qt Bridge
    initQtBridge(() => {
      console.log('Qt Bridge initialized!');
      setIsReady(true);
      loadData();
    });

    // Subscribe to updates
    qtBridge.onInstrumentUpdated((id, data) => {
      console.log('Instrument updated:', id, data);
      loadData();
    });

    qtBridge.onWorkflowUpdated((id, data) => {
      console.log('Workflow updated:', id, data);
      loadData();
    });

    qtBridge.onSessionUpdated((data) => {
      console.log('Session updated:', data);
      loadData();
    });
  }, []);

  async function loadData() {
    const [inst, wf, sess] = await Promise.all([
      qtBridge.getInstruments(),
      qtBridge.getWorkflows(),
      qtBridge.listSessions()
    ]);
    setInstruments(inst);
    setWorkflows(wf);
    setSessions(sess);
  }

  async function handleSaveSession() {
    const path = await qtBridge.saveSession();
    alert(`Session saved to: ${path}`);
    loadData();
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Qt Bridge Test</h1>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            isReady ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
          }`}>
            {isReady ? '✓ Ready' : '⏳ Initializing...'}
          </span>
          <span className="text-sm text-gray-600">
            {qtBridge.isInQt() ? '🖥️ Running in Qt' : '🌐 Running in Browser (Mock)'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Instruments */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Instruments</h2>
          <div className="space-y-3">
            {instruments.map(inst => (
              <div key={inst.id} className="border rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold">{inst.name}</h3>
                    <p className="text-sm text-gray-600">{inst.type}</p>
                    <span className={`inline-block mt-1 px-2 py-1 rounded text-xs ${
                      inst.connected
                        ? 'bg-green-100 text-green-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {inst.status}
                    </span>
                  </div>
                  <div className="flex flex-col gap-2">
                    {inst.connected && inst.has_ui && (
                      <button
                        onClick={() => qtBridge.launchInstrumentUI(inst.id)}
                        className="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
                      >
                        Launch UI
                      </button>
                    )}
                    {!inst.connected && (
                      <button
                        onClick={() => qtBridge.connectInstrument(inst.id)}
                        className="px-3 py-1 bg-green-500 text-white rounded text-sm hover:bg-green-600"
                      >
                        Connect
                      </button>
                    )}
                    {inst.connected && (
                      <button
                        onClick={() => qtBridge.disconnectInstrument(inst.id)}
                        className="px-3 py-1 bg-red-500 text-white rounded text-sm hover:bg-red-600"
                      >
                        Disconnect
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Workflows */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Workflows</h2>
          <div className="space-y-3">
            {workflows.map(wf => (
              <div key={wf.id} className="border rounded-lg p-4">
                <h3 className="font-semibold">{wf.name}</h3>
                <p className="text-sm text-gray-600 mb-2">{wf.description}</p>

                {wf.status === 'running' && (
                  <div className="mb-2">
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all"
                        style={{ width: `${wf.progress * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      {Math.round(wf.progress * 100)}% complete
                    </p>
                  </div>
                )}

                <div className="flex gap-2 mt-2">
                  {wf.status === 'ready' && (
                    <button
                      onClick={() => qtBridge.startWorkflow(wf.id)}
                      className="px-3 py-1 bg-green-500 text-white rounded text-sm hover:bg-green-600"
                    >
                      ▶ Start
                    </button>
                  )}
                  {wf.status === 'running' && (
                    <button
                      onClick={() => qtBridge.stopWorkflow(wf.id)}
                      className="px-3 py-1 bg-red-500 text-white rounded text-sm hover:bg-red-600"
                    >
                      ■ Stop
                    </button>
                  )}
                </div>

                <div className="mt-2">
                  <p className="text-xs text-gray-500">Connected instruments:</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {wf.connected_instruments.map(id => (
                      <span key={id} className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded text-xs">
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Session Management */}
        <div className="bg-white rounded-lg shadow p-6 lg:col-span-2">
          <h2 className="text-xl font-semibold mb-4">Session Management</h2>

          <button
            onClick={handleSaveSession}
            className="mb-4 px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600"
          >
            💾 Save Current Session
          </button>

          {sessions.length > 0 && (
            <div>
              <h3 className="font-semibold mb-2">Saved Sessions</h3>
              <div className="space-y-2">
                {sessions.map(session => (
                  <div key={session.path} className="flex items-center justify-between border rounded p-3">
                    <div>
                      <p className="font-medium">{session.name}</p>
                      <p className="text-xs text-gray-500">{session.path}</p>
                    </div>
                    <button
                      onClick={() => qtBridge.loadSession(session.path)}
                      className="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
                    >
                      Load
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
