import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useLabPilotStore } from '@/store';
import Layout from '@/components/Layout';
import { DeviceModal } from '@/components/DeviceModal/index';
import { WorkflowModal } from '@/components/WorkflowModal/index';
import { UploadSetupModal } from '@/components/UploadSetupModal';
import { WorkflowWindowContent } from '@/components/WorkflowWindow';
import { initQtBridge } from '@/utils/qtBridge';
import Devices from '@/pages/Devices';
import Workflows from '@/pages/Workflows';
import Flow from '@/pages/Flow';
import Data from '@/pages/Data';
import Settings from '@/pages/Settings';
import '@/styles/globals.css';

function App() {
  // Selectively subscribe to store properties to avoid unnecessary re-renders
  const initializeApp = useLabPilotStore((state) => state.initializeApp);
  const session = useLabPilotStore((state) => state.session);
  const ui = useLabPilotStore((state) => state.ui);
  const showDeviceModal = useLabPilotStore((state) => state.showDeviceModal);
  const showWorkflowModal = useLabPilotStore((state) => state.showWorkflowModal);

  useEffect(() => {
    initializeApp().catch(console.error);
  }, [initializeApp]);

  useEffect(() => {
    // Registered here (app mount), not just from Devices/Workflows pages —
    // the Qt shell's "qt-bridge-ready" event fires once, ~300ms after page
    // load, regardless of which route is showing. Registering only from a
    // page-level component risked missing it if the user hadn't navigated
    // there yet (default route is Dashboard).
    initQtBridge();
  }, []);

  return (
    <Router>
      <Routes>
        {/* Standalone window routes - NO Layout wrapper */}
        <Route path="/workflow-window" element={<WorkflowWindowContent />} />

        {/* Main app routes - WITH Layout wrapper */}
        <Route path="/" element={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <Layout>
              {ui.showDeviceModal && <DeviceModal isOpen={ui.showDeviceModal} />}
              {ui.showWorkflowModal && <WorkflowModal isOpen={ui.showWorkflowModal} />}
              {ui.showUploadSetupModal && <UploadSetupModal isOpen={ui.showUploadSetupModal} />}
              <div className="space-y-6">
                <div>
                  <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
                  <p className="text-gray-600 dark:text-gray-400">LabPilot Laboratory Automation System</p>
                </div>

                {/* System Status Card */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">System Status</h2>

                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Backend Connection:</span>
                      <div className="flex items-center space-x-2">
                        <div className={`w-2 h-2 rounded-full ${session.isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span className="text-sm font-medium text-gray-900 dark:text-white">
                          {session.isConnected ? 'Connected' : 'Disconnected'}
                        </span>
                      </div>
                    </div>

                    {session.isConnected && session.sessionId && (
                      <>
                        <div className="flex justify-between items-center">
                          <span className="text-sm text-gray-600 dark:text-gray-400">Session ID:</span>
                          <span className="text-sm font-mono text-gray-700 dark:text-gray-300">
                            {session.sessionId}
                          </span>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-sm text-gray-600 dark:text-gray-400">Devices Connected:</span>
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {session.devicesConnected}
                          </span>
                        </div>

                        <div className="flex justify-between items-center">
                          <span className="text-sm text-gray-600 dark:text-gray-400">Workflows Running:</span>
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {session.workflowEngineRunning}
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </Layout>
          </div>
        } />

        <Route path="/devices" element={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <Layout>
              {ui.showDeviceModal && <DeviceModal isOpen={ui.showDeviceModal} />}
              {ui.showWorkflowModal && <WorkflowModal isOpen={ui.showWorkflowModal} />}
              {ui.showUploadSetupModal && <UploadSetupModal isOpen={ui.showUploadSetupModal} />}
              <Devices />
            </Layout>
          </div>
        } />

        <Route path="/workflows" element={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <Layout>
              {ui.showDeviceModal && <DeviceModal isOpen={ui.showDeviceModal} />}
              {ui.showWorkflowModal && <WorkflowModal isOpen={ui.showWorkflowModal} />}
              {ui.showUploadSetupModal && <UploadSetupModal isOpen={ui.showUploadSetupModal} />}
              <Workflows />
            </Layout>
          </div>
        } />

        <Route path="/flow" element={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <Layout>
              {ui.showDeviceModal && <DeviceModal isOpen={ui.showDeviceModal} />}
              {ui.showWorkflowModal && <WorkflowModal isOpen={ui.showWorkflowModal} />}
              {ui.showUploadSetupModal && <UploadSetupModal isOpen={ui.showUploadSetupModal} />}
              <Flow />
            </Layout>
          </div>
        } />

        <Route path="/data" element={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <Layout>
              {ui.showDeviceModal && <DeviceModal isOpen={ui.showDeviceModal} />}
              {ui.showWorkflowModal && <WorkflowModal isOpen={ui.showWorkflowModal} />}
              {ui.showUploadSetupModal && <UploadSetupModal isOpen={ui.showUploadSetupModal} />}
              <Data />
            </Layout>
          </div>
        } />

        <Route path="/settings" element={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <Layout>
              {ui.showDeviceModal && <DeviceModal isOpen={ui.showDeviceModal} />}
              {ui.showWorkflowModal && <WorkflowModal isOpen={ui.showWorkflowModal} />}
              {ui.showUploadSetupModal && <UploadSetupModal isOpen={ui.showUploadSetupModal} />}
              <Settings />
            </Layout>
          </div>
        } />
      </Routes>
    </Router>
  );
}

export default App;
