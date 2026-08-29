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
 * Call this once when your React app mounts. No-ops outside the Qt desktop
 * shell — there's no mock/fake fallback here; callers check
 * qtBridge.isInQt() and use real in-app UI (backed by the actual backend)
 * when it's false.
 */
export function initQtBridge(callback) {
  if (initialized) {
    if (callback) callback(bridge);
    return;
  }

  if (typeof qt === 'undefined' || typeof qt.webChannelTransport === 'undefined') {
    // Not running inside the Qt shell — nothing to initialize.
    return;
  }

  // manager_qt_webview.py dispatches 'qt-bridge-ready' exactly once, ~300ms
  // after the page finishes loading. This module is only wired up from
  // page-level components (Devices.tsx, Workflows.tsx), which mount late
  // if the app's default route is something else (e.g. Dashboard) — by
  // the time the user navigates to Devices, the one-shot event has already
  // fired and a listener registered now would wait forever, permanently
  // logging "Qt Bridge not initialized". window.qtBridge itself persists
  // once Qt sets it though, so check that directly first — it's set to
  // the real channel proxy (not this module's own `qtBridge` export,
  // which self-assigns window.qtBridge as a placeholder before Qt's
  // channel is ready).
  if (window.qtBridge && window.qtBridge !== qtBridge) {
    bridge = window.qtBridge;
    initialized = true;
    if (callback) callback(bridge);
    return;
  }

  if (callback) {
    initCallbacks.push(callback);
  }

  const eventHandler = () => {
    window.removeEventListener('qt-bridge-ready', eventHandler);
    if (window.qtBridge) {
      bridge = window.qtBridge;
      initialized = true;
      initCallbacks.forEach(cb => cb(bridge));
      initCallbacks = [];
    } else {
      console.warn('qt-bridge-ready event received but window.qtBridge not set');
    }
  };

  window.addEventListener('qt-bridge-ready', eventHandler);
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
   * Launch combined workflow UI window (every instrument the workflow
   * references, in one native window — see workflow_window.py).
   * @param {string} workflowId - Workflow ID
   */
  launchWorkflowUI(workflowId) {
    if (!bridge) {
      console.warn('Qt Bridge not initialized');
      return;
    }
    bridge.launchWorkflowUI(workflowId);
    console.log(`Launching UI for workflow: ${workflowId}`);
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
