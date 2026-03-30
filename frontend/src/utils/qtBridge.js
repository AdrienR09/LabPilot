/**
 * Qt Bridge JavaScript Helper
 *
 * Include this in your React app to communicate with Qt
 *
 * Usage in React:
 *   import { qtBridge, initQtBridge } from './qtBridge';
 *
 *   useEffect(() => {
 *     initQtBridge(() => {
 *       console.log('Qt Bridge ready!');
 *     });
 *   }, []);
 *
 *   // Launch instrument UI
 *   qtBridge.launchInstrumentUI('spectrometer_001');
 */

let bridge = null;
let initialized = false;
let initCallbacks = [];

/**
 * Initialize Qt Bridge
 * Call this once when your React app mounts
 */
export function initQtBridge(callback) {
  // If already initialized, call callback immediately
  if (initialized) {
    console.log('ℹ️  Qt Bridge already initialized');
    if (callback) callback(bridge);
    return;
  }

  console.log('🔧 Initializing Qt Bridge...');

  if (callback) {
    initCallbacks.push(callback);
  }

  // Listen for qt-bridge-ready event from Qt Manager
  const eventHandler = (event) => {
    console.log('🎉 Qt bridge ready event received!');
    window.removeEventListener('qt-bridge-ready', eventHandler);
    clearTimeout(timeoutId);

    // The Qt setup script should have set window.qtBridge
    if (window.qtBridge) {
      bridge = window.qtBridge;
      initialized = true;
      console.log('✅ Qt Bridge initialized successfully');
      console.log('   launchInstrumentUI type:', typeof bridge.launchInstrumentUI);

      // Call all queued callbacks
      initCallbacks.forEach(cb => cb(bridge));
      initCallbacks = [];
    } else {
      console.warn('⚠️  qt-bridge-ready event received but window.qtBridge not set');
      createMockBridgeFallback(callback);
    }
  };

  window.addEventListener('qt-bridge-ready', eventHandler);

  // Timeout after 10 seconds
  const timeoutId = setTimeout(() => {
    if (!initialized) {
      console.warn('⏱️  Qt Bridge initialization timeout (10s) - using mock mode');
      window.removeEventListener('qt-bridge-ready', eventHandler);
      createMockBridgeFallback(callback);
    }
  }, 10000);
}

/**
 * Helper to setup mock bridge as fallback
 */
function createMockBridgeFallback(callback) {
  console.warn('Mock Qt Bridge will be used for development');
  bridge = createMockBridge();
  initialized = true;
  if (callback) callback(bridge);
  initCallbacks.forEach(cb => cb(bridge));
  initCallbacks = [];
}

/**
 * Create mock bridge for development (when not in Qt)
 */
function createMockBridge() {
  return {
    // Instruments
    getInstruments: () => {
      return Promise.resolve(JSON.stringify([
        {
          id: 'spectrometer_001',
          name: 'Ocean Optics USB2000+',
          type: 'Spectrometer',
          kind: 'detector',
          dimensionality: '1D',
          connected: true,
          status: 'Ready',
          has_ui: true
        },
        {
          id: 'camera_001',
          name: 'Andor iXon EMCCD',
          type: 'Camera',
          kind: 'detector',
          dimensionality: '2D',
          connected: true,
          status: 'Ready',
          has_ui: true
        }
      ]));
    },

    getWorkflows: () => {
      return Promise.resolve(JSON.stringify([
        {
          id: 'workflow_001',
          name: 'Spectroscopy Scan',
          description: 'Full spectrum acquisition',
          status: 'ready',
          progress: 0.0,
          connected_instruments: ['spectrometer_001']
        }
      ]));
    },

    launchInstrumentUI: (instrumentId) => {
      console.log(`[Mock] Launch UI for: ${instrumentId}`);

      // Create fake instrument data based on ID
      const instrumentData = {
        id: instrumentId,
        name: `${instrumentId} - Interface`,
        kind: 'detector',
        dimensionality: '1D',
        connected: true,
        category: 'Generic Instrument',
        model: 'Mock Device'
      };

      // Pass instrument data via localStorage so the window can access it
      localStorage.setItem('instrumentWindowData', JSON.stringify(instrumentData));

      // Open instrument UI in a new window for mock mode
      const url = `/instrument-window`;
      const window_handle = window.open(url, `instrument_${instrumentId}`, 'width=1200,height=700,resizable=yes');
      if (window_handle) {
        window_handle.focus();
        console.log(`✅ Opened instrument UI window for ${instrumentId}`);
      } else {
        console.error(`❌ Failed to open instrument window - popup may be blocked`);
      }
    },

    connectInstrument: (instrumentId, params) => {
      console.log(`[Mock] Connect instrument: ${instrumentId}`);
    },

    disconnectInstrument: (instrumentId) => {
      console.log(`[Mock] Disconnect instrument: ${instrumentId}`);
    },

    startWorkflow: (workflowId) => {
      console.log(`[Mock] Start workflow: ${workflowId}`);
    },

    stopWorkflow: (workflowId) => {
      console.log(`[Mock] Stop workflow: ${workflowId}`);
    },

    saveSession: () => {
      console.log(`[Mock] Save session`);
      return Promise.resolve('/mock/session/path');
    },

    loadSession: (sessionPath) => {
      console.log(`[Mock] Load session: ${sessionPath}`);
    },

    listSessions: () => {
      return Promise.resolve(JSON.stringify([]));
    },

    getBlockDiagram: () => {
      // Generate block diagram from mock instruments and workflows
      // Matching the fake data in the store/index.ts
      const mockInstruments = [
        { id: 'spec-001', name: 'Tunable Spectrometer', kind: 'detector', dimensionality: '1D', connected: true },
        { id: 'camera-001', name: 'Spectrum Camera', kind: 'detector', dimensionality: '2D', connected: true },
        { id: 'laser-001', name: 'Tunable Laser', kind: 'source', dimensionality: '0D', connected: true },
        { id: 'motor-001', name: 'XY Motion Stage', kind: 'motor', dimensionality: '0D', connected: true },
        { id: 'lockin-001', name: 'Lock-in Amplifier', kind: 'detector', dimensionality: '0D', connected: true },
        { id: 'pm-001', name: 'Power Meter 1', kind: 'detector', dimensionality: '0D', connected: true },
        { id: 'osci-001', name: 'Oscilloscope', kind: 'detector', dimensionality: '1D', connected: true },
        { id: 'shaker-001', name: 'Vibration Shaker', kind: 'actuator', dimensionality: '0D', connected: false },
        { id: 'ir-cam-001', name: 'IR Camera', kind: 'detector', dimensionality: '2D', connected: true },
        { id: 'pump-001', name: 'Peristaltic Pump', kind: 'actuator', dimensionality: '0D', connected: true },
      ];

      const mockWorkflows = [
        {
          id: 'wf-spec-scan',
          name: 'Spectroscopy Scan',
          description: 'Scan sample spectrum across wavelength range',
          connected_instruments: ['spec-001', 'laser-001']
        },
        {
          id: 'wf-temp-sweep',
          name: 'Temperature Sweep',
          description: 'Measure optical properties vs temperature',
          connected_instruments: ['motor-001', 'camera-001']
        },
        {
          id: 'wf-lockin-meas',
          name: 'Lock-in Measurement',
          description: 'Perform lock-in detection measurement',
          connected_instruments: ['lockin-001', 'pm-001']
        }
      ];

      const nodes = [];
      const edges = [];

      // Add instrument nodes (left side)
      mockInstruments.forEach((inst, idx) => {
        nodes.push({
          id: inst.id,
          type: 'instrument',
          label: inst.name,
          kind: inst.kind,
          dimensionality: inst.dimensionality,
          connected: inst.connected,
          position: { x: 50, y: idx * 120 + 50 }
        });
      });

      // Add workflow nodes (right side) and edges
      mockWorkflows.forEach((wf, idx) => {
        nodes.push({
          id: wf.id,
          type: 'workflow',
          label: wf.name,
          description: wf.description,
          position: { x: 600, y: idx * 120 + 50 }
        });

        // Add edges to connected instruments
        if (wf.connected_instruments) {
          wf.connected_instruments.forEach(instId => {
            edges.push({
              id: `${instId}_${wf.id}`,
              source: instId,
              target: wf.id
            });
          });
        }
      });

      console.log(`[Mock] getBlockDiagram: ${nodes.length} nodes, ${edges.length} edges`);
      return Promise.resolve(JSON.stringify({ nodes, edges }));
    },

    // Signal handlers (mock)
    instrumentUpdated: {
      connect: (handler) => console.log('[Mock] Connected to instrumentUpdated')
    },
    workflowUpdated: {
      connect: (handler) => console.log('[Mock] Connected to workflowUpdated')
    },
    sessionUpdated: {
      connect: (handler) => console.log('[Mock] Connected to sessionUpdated')
    }
  };
}

/**
 * Qt Bridge API
 * Exposes all Qt functions to React
 */
export const qtBridge = {
  /**
   * Get all instruments
   * @returns {Promise<Array>} List of instruments
   */
  async getInstruments() {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return [];
    }
    const json = await bridge.getInstruments();
    return JSON.parse(json);
  },

  /**
   * Get all workflows
   * @returns {Promise<Array>} List of workflows
   */
  async getWorkflows() {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return [];
    }
    const json = await bridge.getWorkflows();
    return JSON.parse(json);
  },

  /**
   * Get single instrument by ID
   * @param {string} instrumentId - Instrument ID
   * @returns {Promise<Object>} Instrument data
   */
  async getInstrument(instrumentId) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return null;
    }
    const json = await bridge.getInstrument(instrumentId);
    return JSON.parse(json);
  },

  /**
   * Launch instrument UI window
   * @param {string} instrumentId - Instrument ID
   */
  launchInstrumentUI(instrumentId) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.launchInstrumentUI(instrumentId);
    console.log(`Launching UI for instrument: ${instrumentId}`);
  },

  /**
   * Connect an instrument
   * @param {string} instrumentId - Instrument ID
   * @param {Object} params - Connection parameters
   */
  connectInstrument(instrumentId, params = {}) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.connectInstrument(instrumentId, JSON.stringify(params));
  },

  /**
   * Disconnect an instrument
   * @param {string} instrumentId - Instrument ID
   */
  disconnectInstrument(instrumentId) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.disconnectInstrument(instrumentId);
  },

  /**
   * Start a workflow
   * @param {string} workflowId - Workflow ID
   */
  startWorkflow(workflowId) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.startWorkflow(workflowId);
  },

  /**
   * Stop a workflow
   * @param {string} workflowId - Workflow ID
   */
  stopWorkflow(workflowId) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.stopWorkflow(workflowId);
  },

  /**
   * Save current session
   * @returns {Promise<string>} Path to saved session file
   */
  async saveSession() {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return null;
    }
    return await bridge.saveSession();
  },

  /**
   * Load session from file
   * @param {string} sessionPath - Path to session file
   */
  loadSession(sessionPath) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.loadSession(sessionPath);
  },

  /**
   * List all saved sessions
   * @returns {Promise<Array>} List of session files
   */
  async listSessions() {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return [];
    }
    const json = await bridge.listSessions();
    return JSON.parse(json);
  },

  /**
   * Get block diagram data
   * @returns {Promise<Object>} Block diagram nodes and edges
   */
  async getBlockDiagram() {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return { nodes: [], edges: [] };
    }
    const json = await bridge.getBlockDiagram();
    return JSON.parse(json);
  },

  /**
   * Subscribe to instrument updates
   * @param {Function} callback - Called when instrument is updated
   */
  onInstrumentUpdated(callback) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.instrumentUpdated.connect(callback);
  },

  /**
   * Subscribe to workflow updates
   * @param {Function} callback - Called when workflow is updated
   */
  onWorkflowUpdated(callback) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.workflowUpdated.connect(callback);
  },

  /**
   * Subscribe to session updates
   * @param {Function} callback - Called when session is updated
   */
  onSessionUpdated(callback) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.sessionUpdated.connect(callback);
  },

  /**
   * Check if running in Qt WebEngine
   * @returns {boolean} True if in Qt, false if in browser
   */
  isInQt() {
    return typeof qt !== 'undefined' && typeof qt.webChannelTransport !== 'undefined';
  }
};

// Auto-initialize when qwebchannel.js is loaded
if (typeof window !== 'undefined') {
  window.qtBridge = qtBridge;
  window.initQtBridge = initQtBridge;
}

export default qtBridge;
