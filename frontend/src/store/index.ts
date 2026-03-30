import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { INSTRUMENT_CATALOG } from '@/data/instruments';

interface SessionState {
  isConnected: boolean;
  sessionId: string | null;
  devicesConnected: number;
  aiAvailable: boolean;
  workflowEngineRunning: number;
}

interface Device {
  id: string;
  name: string;
  adapter_type: string;
  category: string;
  manufacturer?: string;
  modelNumber?: string;
  model?: string;
  connected: boolean;
  kind?: string;
  dimensionality?: string;
  tags?: string[];
  parameters?: Record<string, any>;
  last_reading?: any;
  error?: string;
}

// Convert Instrument catalog to Device format for store
const FAKE_INSTRUMENTS: Device[] = INSTRUMENT_CATALOG.map(inst => ({
  id: inst.id,
  name: inst.name,
  adapter_type: inst.adapterType,
  category: inst.category,
  manufacturer: inst.manufacturer,
  modelNumber: inst.modelNumber,
  model: inst.modelNumber,
  connected: inst.connected,
  kind: inst.kind,
  dimensionality: inst.dimensionality,
  tags: inst.tags || [],
  parameters: inst.parameters,
}));

interface Workflow {
  id: string;
  name: string;
  version: number;
  status?: 'ready' | 'running' | 'completed' | 'error';
  created_at: number;
  updated_at: number;
  description?: string;
  workflow_type?: string;
  connected_instruments?: string[];
  running?: boolean;
  has_data?: boolean;
  progress?: number;
}

// Fake workflows for development
const FAKE_WORKFLOWS: Workflow[] = [
  {
    id: 'wf-spec-scan',
    name: 'Spectroscopy Scan',
    version: 1,
    status: 'ready',
    created_at: Date.now() - 86400000,
    updated_at: Date.now(),
    description: 'Scan sample spectrum across wavelength range',
    workflow_type: 'Spectroscopy',
    connected_instruments: ['spec-001', 'laser-001'],
    running: false,
    has_data: false,
    progress: 0,
  },
  {
    id: 'wf-temp-sweep',
    name: 'Temperature Sweep',
    version: 1,
    status: 'ready',
    created_at: Date.now() - 172800000,
    updated_at: Date.now(),
    description: 'Measure optical properties vs temperature',
    workflow_type: 'Temperature Control',
    connected_instruments: ['motor-001', 'camera-001'],
    running: false,
    has_data: false,
    progress: 0,
  },
  {
    id: 'wf-lockin-meas',
    name: 'Lock-in Measurement',
    version: 1,
    status: 'ready',
    created_at: Date.now() - 259200000,
    updated_at: Date.now(),
    description: 'Perform lock-in detection measurement',
    workflow_type: 'Signal Detection',
    connected_instruments: ['lockin-001', 'pm-001'],
    running: false,
    has_data: false,
    progress: 0,
  },
];

interface UIState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  loading: boolean;
  showDeviceModal: boolean;
  showWorkflowModal: boolean;
  selectedInstrumentId: string | null;
  showInstrumentSettings: boolean;
}

interface UserPreferences {
  theme: 'light' | 'dark';
  autoConnect: boolean;
  notifications: boolean;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  structuredPrompt?: {
    message: string;
    inputs: Array<{
      type: 'select' | 'text' | 'number' | 'checkbox' | 'radio';
      id: string;
      label: string;
      description?: string;
      required?: boolean;
      options?: Array<{ label: string; value: string | number }>;
      placeholder?: string;
    }>;
    submitLabel?: string;
  };
}

interface Conversation {
  id: string;
  messages: Message[];
  conversationId?: string;
}

interface LabPilotState {
  // Session state
  session: SessionState;

  // Devices
  devices: Device[];
  devicesLoading: boolean;
  devicesError: string | null;

  // Workflows
  workflows: Workflow[];
  workflowsLoading: boolean;
  workflowsError: string | null;

  // Chat
  currentConversation: Conversation | null;
  chatLoading: boolean;
  chatError: string | null;

  // UI state
  ui: UIState;

  // User preferences
  preferences: UserPreferences;

  // Actions
  setSessionState: (state: Partial<SessionState>) => void;
  setUIState: (state: Partial<UIState>) => void;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleSidebar: () => void;
  setLoading: (loading: boolean) => void;
  showDeviceModal: () => void;
  hideDeviceModal: () => void;
  showWorkflowModal: () => void;
  hideWorkflowModal: () => void;
  showInstrumentSettings: (instrumentId: string) => void;
  hideInstrumentSettings: () => void;

  // Device management
  loadDevices: () => Promise<void>;
  connectDevice: (name: string, adapterType: string, params: Record<string, any>) => Promise<void>;
  disconnectDevice: (deviceId: string) => Promise<void>;
  connectDeviceById: (deviceId: string) => Promise<void>;

  // Workflow management
  loadWorkflows: () => Promise<void>;
  createWorkflow: (name: string, description?: string) => Promise<void>;
  executeWorkflow: (id: string) => Promise<void>;

  // Chat management
  sendMessage: (message: string) => Promise<void>;
  clearChat: () => void;

  // App initialization
  initializeApp: () => Promise<void>;
}

export const useLabPilotStore = create<LabPilotState>()(
  immer((set, get) => ({
    // Initial state
    session: {
      isConnected: true,
      sessionId: 'fake-session-' + Math.random().toString(36).substring(2, 9),
      devicesConnected: FAKE_INSTRUMENTS.filter(d => d.connected).length,
      aiAvailable: true,
      workflowEngineRunning: 0,
    },

    devices: FAKE_INSTRUMENTS,
    devicesLoading: false,
    devicesError: null,

    workflows: [],
    workflowsLoading: false,
    workflowsError: null,

    currentConversation: null,
    chatLoading: false,
    chatError: null,

    ui: {
      sidebarOpen: true,
      theme: 'dark',
      loading: false,
      showDeviceModal: false,
      showWorkflowModal: false,
      selectedInstrumentId: null,
      showInstrumentSettings: false,
    },

    preferences: {
      theme: 'dark',
      autoConnect: true,
      notifications: true,
    },

    // Actions
    setSessionState: (sessionState) => set((state) => {
      Object.assign(state.session, sessionState);
    }),

    setUIState: (uiState) => set((state) => {
      Object.assign(state.ui, uiState);
    }),

    setTheme: (theme) => set((state) => {
      state.ui.theme = theme;
      state.preferences.theme = theme;

      // Update document class
      if (theme === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }

      // Persist to localStorage
      try {
        localStorage.setItem('labpilot-theme', theme);
      } catch (e) {
        console.warn('Failed to save theme preference:', e);
      }
    }),

    toggleSidebar: () => set((state) => {
      state.ui.sidebarOpen = !state.ui.sidebarOpen;
    }),

    setLoading: (loading) => set((state) => {
      state.ui.loading = loading;
    }),

    showDeviceModal: () => set((state) => {
      state.ui.showDeviceModal = true;
    }),

    hideDeviceModal: () => set((state) => {
      state.ui.showDeviceModal = false;
    }),

    showWorkflowModal: () => set((state) => {
      state.ui.showWorkflowModal = true;
    }),

    hideWorkflowModal: () => set((state) => {
      state.ui.showWorkflowModal = false;
    }),

    showInstrumentSettings: (instrumentId: string) => set((state) => {
      state.ui.selectedInstrumentId = instrumentId;
      state.ui.showInstrumentSettings = true;
    }),

    hideInstrumentSettings: () => set((state) => {
      state.ui.selectedInstrumentId = null;
      state.ui.showInstrumentSettings = false;
    }),

    loadDevices: async () => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });

      try {
        // Try to connect to backend and fetch devices
        try {
          const response = await fetch('/api/dashboard/instruments', { signal: AbortSignal.timeout(2000) });
          if (response.ok) {
            const data = await response.json();
            const devices = data.data || [];
            console.log('✅ Loaded devices from backend:', devices.length);
            set((state) => {
              state.devices = devices;
            });
            return;
          } else {
            console.log(`Backend returned ${response.status}, using fake instruments`);
          }
        } catch (e) {
          // Backend not available, use fake data
          console.log('Backend unavailable, using fake instruments:', e instanceof Error ? e.message : String(e));
        }

        // Use fake instruments
        console.log('Loading 10 fake instruments...');
        set((state) => {
          state.devices = FAKE_INSTRUMENTS;
        });
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to load devices';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
    },

    connectDevice: async (name: string, adapterType: string, params: Record<string, any> = {}) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });

      try {
        // In development mode, add device to local state
        const newDevice: Device = {
          id: `dev-${Date.now()}`,
          name,
          adapter_type: adapterType,
          category: params.category || 'Unknown',
          model: params.model || 'N/A',
          connected: true,
        };

        set((state) => {
          state.devices.push(newDevice);
        });

        get().hideDeviceModal();

        // Try to also connect via backend if available
        try {
          const response = await fetch('/api/devices/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name,
              adapter_type: adapterType,
              connection_params: params,
            }),
          });

          if (response.ok) {
            console.log('Device connected on backend');
            await get().loadDevices();
          }
        } catch (e) {
          console.log('Backend unavailable, device added to frontend only');
        }
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to connect device';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
    },

    disconnectDevice: async (deviceId: string) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });

      try {
        // Toggle device connected status to false
        set((state) => {
          const device = state.devices.find(d => d.id === deviceId);
          if (device) {
            device.connected = false;
          }
        });

        // Try to also disconnect via backend if available
        try {
          const response = await fetch(`/api/devices/${deviceId}/disconnect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          });

          if (response.ok) {
            console.log('Device disconnected on backend');
            await get().loadDevices();
          }
        } catch (e) {
          console.log('Backend unavailable, device disconnected on frontend only');
        }
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to disconnect device';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
    },

    connectDeviceById: async (deviceId: string) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });

      try {
        // Toggle device connected status to true
        set((state) => {
          const device = state.devices.find(d => d.id === deviceId);
          if (device) {
            device.connected = true;
          }
        });

        // Try to also connect via backend if available
        try {
          const response = await fetch(`/api/devices/${deviceId}/connect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          });

          if (response.ok) {
            console.log('Device connected on backend');
            await get().loadDevices();
          }
        } catch (e) {
          console.log('Backend unavailable, device connected on frontend only');
        }
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to connect device';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
    },

    loadWorkflows: async () => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        // Try to connect to backend
        try {
          const response = await fetch('/api/workflows', { signal: AbortSignal.timeout(2000) });
          if (response.ok) {
            const data = await response.json();
            const workflows = data.data || [];
            set((state) => {
              state.workflows = workflows;
            });
            return;
          } else {
            console.log(`Backend returned ${response.status}, using fake workflows`);
          }
        } catch (e) {
          console.log('Backend unavailable, using fake workflows:', e instanceof Error ? e.message : String(e));
        }

        // Use fake workflows
        console.log('Loading 3 fake workflows...');
        set((state) => {
          state.workflows = FAKE_WORKFLOWS;
        });
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to load workflows';
        });
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    createWorkflow: async (name: string, description?: string) => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        const response = await fetch('/api/workflows', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: description || '' }),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || error.error || 'Failed to create workflow');
        }

        // Reload workflows list after successful creation
        await get().loadWorkflows();
        get().hideWorkflowModal();
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to create workflow';
        });
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    executeWorkflow: async (id: string) => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        const response = await fetch(`/api/workflows/${id}/execute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });

        if (!response.ok) throw new Error('Failed to execute workflow');

        // Reload workflows list after execution
        await get().loadWorkflows();
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to execute workflow';
        });
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    sendMessage: async (message: string) => {
      // Check if AI is available
      const { aiAvailable } = get().session;
      if (!aiAvailable) {
        set((state) => {
          state.chatError = 'AI assistant is not available. Please configure an AI provider in the backend.';
        });
        return;
      }

      // Initialize conversation if needed
      if (!get().currentConversation) {
        set((state) => {
          state.currentConversation = {
            id: `conv-${Date.now()}`,
            messages: [],
            conversationId: undefined,
          };
        });
      }

      // Add user message to conversation
      const userMessage: Message = {
        id: `msg-${Date.now()}`,
        role: 'user',
        content: message,
        timestamp: Date.now(),
      };

      set((state) => {
        if (state.currentConversation) {
          state.currentConversation.messages.push(userMessage);
        }
        state.chatLoading = true;
        state.chatError = null;
      });

      try {
        const response = await fetch('/api/ai/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message,
            conversation_id: get().currentConversation?.conversationId,
            use_tools: true,
          }),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || error.error || 'Failed to get response from AI');
        }

        const data = await response.json();
        const aiResponse = data.data;

        // Add assistant message to conversation
        const assistantMessage: Message = {
          id: `msg-${Date.now()}-ai`,
          role: 'assistant',
          content: aiResponse.response || 'No response',
          timestamp: Date.now(),
          structuredPrompt: aiResponse.structured_prompt,
        };

        set((state) => {
          if (state.currentConversation) {
            state.currentConversation.messages.push(assistantMessage);
            state.currentConversation.conversationId = aiResponse.conversation_id;
          }
        });
      } catch (error) {
        set((state) => {
          state.chatError = error instanceof Error ? error.message : 'Failed to send message';
        });
      } finally {
        set((state) => {
          state.chatLoading = false;
        });
      }
    },

    clearChat: () => set((state) => {
      state.currentConversation = null;
      state.chatError = null;
    }),

    initializeApp: async () => {
      set((state) => {
        state.ui.loading = true;
      });

      try {
        // Load theme from localStorage
        const savedTheme = localStorage.getItem('labpilot-theme') as 'light' | 'dark' || 'dark';
        get().setTheme(savedTheme);

        // Check backend connection
        try {
          const response = await fetch('/api/session/status', { signal: AbortSignal.timeout(2000) });
          if (response.ok) {
            const data = await response.json();
            get().setSessionState({
              isConnected: true,
              sessionId: data.data.session_id || null,
              devicesConnected: data.data.devices_connected || 0,
              aiAvailable: data.data.ai_available || false,
              workflowEngineRunning: data.data.workflow_engine_running || 0,
            });
          }
        } catch (e) {
          console.log('Backend unavailable, using fake instruments');
        }

        // ALWAYS load devices and workflows (fake or real)
        await Promise.all([
          get().loadDevices(),
          get().loadWorkflows(),
        ]);
      } catch (error) {
        console.error('Failed to initialize app:', error);
      } finally {
        set((state) => {
          state.ui.loading = false;
        });
      }
    },
  }))
);