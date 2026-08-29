import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import {
  getCatalog as apiGetCatalog,
  createInstrument as apiCreateInstrument,
  connectInstrument as apiConnectInstrument,
  disconnectInstrument as apiDisconnectInstrument,
  removeInstrument as apiRemoveInstrument,
  getInstrumentConfigs as apiGetInstrumentConfigs,
  activateInstrumentConfig as apiActivateInstrumentConfig,
  newInstrumentConfig as apiNewInstrumentConfig,
  uploadInstrumentConfig as apiUploadInstrumentConfig,
  type CatalogEntry,
} from '@/api';

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
  status?: 'idle' | 'busy' | 'error';
  kind?: string;
  dimensionality?: string;
  tags?: string[];
  parameters?: Record<string, any>;
  last_reading?: any;
  error?: string;
  connection_params?: Record<string, any>;
  custom_settings?: Record<string, any>;
}

export interface Workflow {
  id: string;
  name: string;
  version: number;
  status?: 'ready' | 'running' | 'completed' | 'error';
  created_at: number;
  updated_at: number;
  description?: string;
  script_path?: string;
  workflow_type?: string;
  connected_instruments?: string[];
  running?: boolean;
  has_data?: boolean;
  progress?: number;
  // Populated from the most recent execution_logs row (see
  // GET /api/workflows) — "completed" | "failed" | "cancelled" | null.
  last_status?: string | null;
  last_completed_at?: number | null;
}


interface UIState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark';
  loading: boolean;
  showDeviceModal: boolean;
  showWorkflowModal: boolean;
  showUploadSetupModal: boolean;
  selectedInstrumentId: string | null;
  showInstrumentSettings: boolean;
  showInstrumentLiveView: boolean;
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

  // Instrument catalog (for the device-creation UI)
  catalog: CatalogEntry[];
  catalogLoading: boolean;

  // Instrument-set configs (named, swappable setups)
  instrumentConfigs: string[];
  activeInstrumentConfig: string | null;

  // Workflows
  workflows: Workflow[];
  workflowsLoading: boolean;
  workflowsError: string | null;

  // Chat
  currentConversation: Conversation | null;
  chatLoading: boolean;
  chatError: string | null;
  // Set by openAIChat() when the AI chat is opened scoped to a specific
  // workflow (or a fresh one) — read by ChatBox to prefill its input and
  // to pass workflowId/conversationId along on every send in that
  // session. conversationId is stable per workflow ("workflow-{id}") so
  // reopening the chat for the same workflow loads the same history
  // (see loadConversationHistory) instead of starting blank each time.
  aiChatContext: { workflowId?: string; seedText?: string; conversationId: string } | null;

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
  showUploadSetupModal: () => void;
  hideUploadSetupModal: () => void;
  showInstrumentSettings: (instrumentId: string) => void;
  hideInstrumentSettings: () => void;
  showInstrumentUI: (instrumentId: string) => void;
  hideInstrumentUI: () => void;

  // Device management
  loadDevices: () => Promise<void>;
  connectDevice: (name: string, adapterType: string, params: Record<string, any>) => Promise<void>;
  disconnectDevice: (deviceId: string) => Promise<void>;
  connectDeviceById: (deviceId: string) => Promise<void>;
  removeDevice: (deviceId: string) => Promise<void>;
  loadCatalog: () => Promise<void>;
  createDeviceFromCatalog: (
    adapterKey: string,
    opts?: { id?: string; name?: string; connectionParams?: Record<string, any> }
  ) => Promise<void>;

  // Instrument-set config management
  loadInstrumentConfigs: () => Promise<void>;
  activateInstrumentConfig: (name: string) => Promise<void>;
  createBlankInstrumentConfig: (name: string) => Promise<void>;
  uploadInstrumentConfig: (name: string, devices: Record<string, any>[]) => Promise<void>;

  // Workflow management
  loadWorkflows: () => Promise<void>;
  createWorkflow: (name: string, description?: string) => Promise<void>;
  executeWorkflow: (id: string) => Promise<void>;
  stopWorkflow: (id: string) => Promise<void>;
  unloadWorkflow: (id: string) => Promise<void>;
  loadWorkflowScript: (path: string) => Promise<void>;

  // Chat management
  sendMessage: (message: string, workflowId?: string, conversationId?: string) => Promise<void>;
  clearChat: () => void;
  openAIChat: (ctx: { workflowId?: string; seedText?: string }) => void;
  clearAIChatContext: () => void;
  loadConversationHistory: (conversationId: string) => Promise<void>;

  // App initialization
  initializeApp: () => Promise<void>;
}

export const useLabPilotStore = create<LabPilotState>()(
  immer((set, get) => ({
    // Initial state
    session: {
      isConnected: false,
      sessionId: null,
      devicesConnected: 0,
      aiAvailable: false,
      workflowEngineRunning: 0,
    },

    devices: [],
    devicesLoading: false,
    devicesError: null,

    catalog: [],
    catalogLoading: false,

    instrumentConfigs: [],
    activeInstrumentConfig: null,

    workflows: [],
    workflowsLoading: false,
    workflowsError: null,

    currentConversation: null,
    chatLoading: false,
    chatError: null,
    aiChatContext: null,

    ui: {
      sidebarOpen: true,
      theme: 'dark',
      loading: false,
      showDeviceModal: false,
      showWorkflowModal: false,
      showUploadSetupModal: false,
      selectedInstrumentId: null,
      showInstrumentSettings: false,
      showInstrumentLiveView: false,
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

    showUploadSetupModal: () => set((state) => {
      state.ui.showUploadSetupModal = true;
    }),

    hideUploadSetupModal: () => set((state) => {
      state.ui.showUploadSetupModal = false;
    }),

    showInstrumentSettings: (instrumentId: string) => set((state) => {
      state.ui.selectedInstrumentId = instrumentId;
      state.ui.showInstrumentSettings = true;
    }),

    hideInstrumentSettings: () => set((state) => {
      state.ui.selectedInstrumentId = null;
      state.ui.showInstrumentSettings = false;
    }),

    showInstrumentUI: (instrumentId: string) => set((state) => {
      state.ui.selectedInstrumentId = instrumentId;
      state.ui.showInstrumentLiveView = true;
    }),

    hideInstrumentUI: () => set((state) => {
      state.ui.selectedInstrumentId = null;
      state.ui.showInstrumentLiveView = false;
    }),

    loadDevices: async () => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });

      try {
        const response = await fetch('/api/dashboard/instruments', { signal: AbortSignal.timeout(5000) });
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        const data = await response.json();
        const devices = data.data || [];
        console.log('✅ Loaded devices from backend:', devices.length);
        set((state) => {
          state.devices = devices;
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
        const device = state.devices.find(d => d.id === deviceId);
        if (device) device.status = 'busy';
        state.devicesError = null;
      });

      try {
        const updated = await apiDisconnectInstrument(deviceId);
        set((state) => {
          const device = state.devices.find(d => d.id === deviceId);
          if (device) {
            device.connected = updated.connected;
            device.status = updated.status || 'idle';
            device.error = updated.error || undefined;
          }
        });
      } catch (error) {
        set((state) => {
          const device = state.devices.find(d => d.id === deviceId);
          if (device) device.status = 'error';
          state.devicesError = error instanceof Error ? error.message : 'Failed to disconnect device';
        });
      }
    },

    connectDeviceById: async (deviceId: string) => {
      set((state) => {
        const device = state.devices.find(d => d.id === deviceId);
        if (device) device.status = 'busy';
        state.devicesError = null;
      });

      try {
        const updated = await apiConnectInstrument(deviceId);
        set((state) => {
          const device = state.devices.find(d => d.id === deviceId);
          if (device) {
            device.connected = updated.connected;
            device.status = updated.status || 'idle';
            device.error = updated.error || undefined;
          }
        });
      } catch (error) {
        set((state) => {
          const device = state.devices.find(d => d.id === deviceId);
          if (device) device.status = 'error';
          state.devicesError = error instanceof Error ? error.message : 'Failed to connect device';
        });
      }
    },

    removeDevice: async (deviceId: string) => {
      // Remove locally immediately; the DELETE call is best-effort so the
      // list stays usable even if the backend is unreachable (fake/dev mode).
      set((state) => {
        state.devices = state.devices.filter(d => d.id !== deviceId);
      });
      try {
        await apiRemoveInstrument(deviceId);
      } catch (error) {
        console.log('Backend unavailable or device not found there, removed from frontend only');
      }
    },

    loadCatalog: async () => {
      set((state) => {
        state.catalogLoading = true;
      });
      try {
        const catalog = await apiGetCatalog();
        set((state) => {
          state.catalog = catalog;
        });
      } catch (error) {
        console.log('Backend unavailable, catalog browsing disabled:', error instanceof Error ? error.message : String(error));
      } finally {
        set((state) => {
          state.catalogLoading = false;
        });
      }
    },

    createDeviceFromCatalog: async (adapterKey, opts = {}) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });
      try {
        const created = await apiCreateInstrument(adapterKey, opts);
        set((state) => {
          state.devices.push({
            id: created.id,
            name: created.name,
            adapter_type: created.adapter_type,
            category: created.kind,
            connected: created.connected,
            status: created.status || 'idle',
            kind: created.kind,
            dimensionality: created.dimensionality,
            tags: created.tags,
          });
        });
        get().hideDeviceModal();
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to create device';
        });
        throw error; // let the caller (DeviceModal) know it failed and keep its form state
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
    },

    loadInstrumentConfigs: async () => {
      try {
        const { configs, active } = await apiGetInstrumentConfigs();
        set((state) => {
          state.instrumentConfigs = configs;
          state.activeInstrumentConfig = active;
        });
      } catch (error) {
        console.log('Backend unavailable, instrument configs unavailable:', error instanceof Error ? error.message : String(error));
      }
    },

    activateInstrumentConfig: async (name: string) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });
      try {
        const { instruments } = await apiActivateInstrumentConfig(name);
        set((state) => {
          state.devices = instruments as any;
          state.activeInstrumentConfig = name;
        });
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to switch instrument config';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
      await get().loadInstrumentConfigs();
    },

    createBlankInstrumentConfig: async (name: string) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });
      try {
        const { instruments } = await apiNewInstrumentConfig(name);
        set((state) => {
          state.devices = instruments as any;
          state.activeInstrumentConfig = name;
        });
        get().hideUploadSetupModal();
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to create instrument config';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
      await get().loadInstrumentConfigs();
    },

    uploadInstrumentConfig: async (name: string, devices: Record<string, any>[]) => {
      set((state) => {
        state.devicesLoading = true;
        state.devicesError = null;
      });
      try {
        const { instruments } = await apiUploadInstrumentConfig(name, devices);
        set((state) => {
          state.devices = instruments as any;
          state.activeInstrumentConfig = name;
        });
        get().hideUploadSetupModal();
      } catch (error) {
        set((state) => {
          state.devicesError = error instanceof Error ? error.message : 'Failed to load uploaded config';
        });
      } finally {
        set((state) => {
          state.devicesLoading = false;
        });
      }
      await get().loadInstrumentConfigs();
    },

    loadWorkflows: async () => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        const response = await fetch('/api/workflows', { signal: AbortSignal.timeout(5000) });
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        const data = await response.json();
        set((state) => {
          state.workflows = data.data || [];
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

        if (!response.ok) {
          const error = await response.json().catch(() => null);
          throw new Error(error?.detail || error?.error || 'Failed to execute workflow');
        }

        // Reload workflows list after execution
        await get().loadWorkflows();
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to execute workflow';
        });
        throw error;
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    stopWorkflow: async (id: string) => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        const response = await fetch(`/api/workflows/${id}/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });

        if (!response.ok) {
          const error = await response.json().catch(() => null);
          throw new Error(error?.detail || error?.error || 'Failed to stop workflow');
        }

        await get().loadWorkflows();
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to stop workflow';
        });
        throw error;
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    unloadWorkflow: async (id: string) => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        const response = await fetch(`/api/workflows/${id}`, { method: 'DELETE' });

        if (!response.ok) {
          const error = await response.json().catch(() => null);
          throw new Error(error?.detail || error?.error || 'Failed to unload workflow');
        }

        await get().loadWorkflows();
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to unload workflow';
        });
        throw error;
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    loadWorkflowScript: async (path: string) => {
      set((state) => {
        state.workflowsLoading = true;
        state.workflowsError = null;
      });

      try {
        const response = await fetch('/api/workflows/load', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path }),
        });

        if (!response.ok) {
          const error = await response.json().catch(() => null);
          throw new Error(error?.detail || error?.error || 'Failed to load workflow script');
        }

        await get().loadWorkflows();
      } catch (error) {
        set((state) => {
          state.workflowsError = error instanceof Error ? error.message : 'Failed to load workflow script';
        });
        throw error;
      } finally {
        set((state) => {
          state.workflowsLoading = false;
        });
      }
    },

    sendMessage: async (message: string, workflowId?: string, conversationId?: string) => {
      // Check if AI is available
      const { aiAvailable } = get().session;
      if (!aiAvailable) {
        set((state) => {
          state.chatError = 'AI assistant is not available. Please configure an AI provider in the backend.';
        });
        return;
      }

      // Initialize conversation if needed — seeded with the caller's
      // explicit conversationId (e.g. "workflow-{id}", see openAIChat) so
      // every message in this session lands in the same persisted
      // conversation, rather than falling back to the backend's "default"
      // bucket shared by every unscoped chat.
      if (!get().currentConversation) {
        set((state) => {
          state.currentConversation = {
            id: `conv-${Date.now()}`,
            messages: [],
            conversationId,
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
            conversation_id: conversationId ?? get().currentConversation?.conversationId,
            use_tools: true,
            workflow_id: workflowId,
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

    // Opens the AI chat scoped to a workflow (or a fresh one). A workflow
    // gets a stable "workflow-{id}" conversation id so reopening its chat
    // later loads the same persisted history (see loadConversationHistory
    // and the backend's ConfigPersistence.save_conversation, called after
    // every exchange) instead of starting blank; a context-free "new
    // workflow" chat gets a fresh id each time since there's no workflow
    // identity yet to key off of. `seedText` prefills the input for the
    // user to edit rather than being auto-sent.
    openAIChat: (ctx) => {
      const conversationId = ctx.workflowId ? `workflow-${ctx.workflowId}` : `chat-${Date.now()}`;
      set((state) => {
        state.aiChatContext = { ...ctx, conversationId };
        state.chatError = null;
      });
      if (ctx.workflowId) {
        get().loadConversationHistory(conversationId);
      } else {
        set((state) => {
          state.currentConversation = { id: `conv-${conversationId}`, messages: [], conversationId };
        });
      }
    },

    clearAIChatContext: () => set((state) => {
      state.aiChatContext = null;
    }),

    loadConversationHistory: async (conversationId: string) => {
      try {
        const response = await fetch(`/api/ai/conversations/${conversationId}`);
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        const data = await response.json();
        const messages: Message[] = data.data || [];
        set((state) => {
          state.currentConversation = { id: `conv-${conversationId}`, messages, conversationId };
        });
      } catch (error) {
        // No saved history (new workflow, or the AI backend is down) —
        // still seed conversationId so sendMessage keeps using it.
        set((state) => {
          state.currentConversation = { id: `conv-${conversationId}`, messages: [], conversationId };
        });
      }
    },

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