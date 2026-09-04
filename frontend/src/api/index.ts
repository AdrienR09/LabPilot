// API client for LabPilot backend communication
import {
  ApiResponse,
  SessionStatus,
  Device,
  DeviceConnectionRequest,
  Workflow,
  Conversation,
  LabPilotEvent,
  WebSocketMessage,
} from '@/types';

// Base configuration
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';

// Generic API client class
class APIClient {
  private baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;

    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json() as ApiResponse<T>;

    if (!data.success) {
      throw new Error(data.error || 'API request failed');
    }

    return data.data!;
  }

  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  async post<T>(endpoint: string, body: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async put<T>(endpoint: string, body: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  async patch<T>(endpoint: string, body: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }
}

// Create API client instance
const client = new APIClient(API_BASE_URL);

// Session management
export const getSessionStatus = (): Promise<SessionStatus> =>
  client.get<SessionStatus>('/session/status');

// Device management
export const getDevices = (): Promise<Device[]> =>
  client.get<Device[]>('/devices');

export const connectDevice = (device: DeviceConnectionRequest): Promise<void> =>
  client.post<void>('/devices/connect', device);

export const disconnectDevice = (name: string): Promise<void> =>
  client.delete<void>(`/devices/${name}`);

// Workflow management
export const getWorkflows = (): Promise<Workflow[]> =>
  client.get<Workflow[]>('/workflows');

export const createWorkflow = (name: string, description?: string): Promise<Workflow> =>
  client.post<Workflow>('/workflows', { name, description });

export const executeWorkflow = (id: string, version?: number): Promise<{ execution_id: string }> =>
  client.post<{ execution_id: string }>('/workflows/execute', { workflow_id: id, version });

export interface WorkflowScript {
  path: string;
  content: string;
}

export interface WorkflowGraphNode {
  id: string;
  name: string;
  kind: string;
  [key: string]: any;
}

export interface WorkflowGraphEdge {
  from_node: string;
  to_node: string;
  label?: string;
}

export interface WorkflowGraphDetail {
  id: string;
  name: string;
  nodes: Record<string, WorkflowGraphNode>;
  edges: WorkflowGraphEdge[];
  metadata?: Record<string, any>;
}

export const getWorkflowGraph = (id: string): Promise<WorkflowGraphDetail> =>
  client.get<WorkflowGraphDetail>(`/workflows/${id}`);

export const getWorkflowScript = (id: string): Promise<WorkflowScript> =>
  client.get<WorkflowScript>(`/workflows/${id}/script`);

export const updateWorkflowScript = (id: string, content: string): Promise<{ path: string }> =>
  client.put<{ path: string }>(`/workflows/${id}/script`, { content });

export const loadWorkflowFromPath = (path: string): Promise<{ workflow_id: string; script_path: string }> =>
  client.post<{ workflow_id: string; script_path: string }>('/workflows/load', { path });

// Workflow template library + instrument role-slot binding — see
// core/workflow_templates/ and core/workflow/instrument_roles.py. A
// template declares the instrument "roles" it needs (kind + dimensionality)
// without naming a specific instrument; loading one creates a workflow whose
// roles start unbound, then each role is bound to a real connected
// instrument (via the flowchart) before it can run.
export interface WorkflowRoleRequirement {
  kind: string;
  dimensionality: string;
}

export interface WorkflowTemplate {
  name: string;
  description: string;
  required_instruments: Record<string, WorkflowRoleRequirement>;
}

export const getWorkflowTemplates = (): Promise<WorkflowTemplate[]> =>
  client.get<WorkflowTemplate[]>('/workflows/templates');

export const loadWorkflowTemplate = (
  templateName: string
): Promise<{ workflow_id: string; script_path: string }> =>
  client.post<{ workflow_id: string; script_path: string }>(
    `/workflows/templates/${templateName}/load`,
    {}
  );

export interface WorkflowBindingRole {
  role: string;
  kind: string;
  dimensionality: string;
  instrument_id: string | null;
  optional: boolean;
}

export const getWorkflowBindings = (id: string): Promise<{ roles: WorkflowBindingRole[] }> =>
  client.get<{ roles: WorkflowBindingRole[] }>(`/workflows/${id}/bindings`);

export const setWorkflowBinding = (
  id: string,
  role: string,
  instrumentId: string | null
): Promise<{ role: string; instrument_id: string | null }> =>
  client.put<{ role: string; instrument_id: string | null }>(
    `/workflows/${id}/bindings/${role}`,
    { instrument_id: instrumentId }
  );

// AI Chat
export const sendMessage = (
  message: string,
  conversationId?: string,
  useTools: boolean = true
): Promise<{ response: string; conversation_id: string }> =>
  client.post<{ response: string; conversation_id: string }>('/ai/chat', {
    message,
    conversation_id: conversationId,
    use_tools: useTools,
  });

export const getConversations = (): Promise<Conversation[]> =>
  client.get<Conversation[]>('/ai/conversations');

// Configuration
export const getConfig = (): Promise<any> =>
  client.get<any>('/config');

export const updateConfig = (config: any): Promise<void> =>
  client.put<void>('/config', config);

// Dashboard management
export interface DashboardInstrument {
  id: string;
  name: string;
  adapter_type: string;
  kind: string;
  dimensionality: string;
  tags: string[];
  connected: boolean;
  status?: 'idle' | 'busy' | 'error';
  error?: string | null;
  data?: any;
  connection_params?: Record<string, any>;
  custom_settings?: Record<string, any>;
}

export interface InstrumentSchema {
  name: string;
  kind: string;
  readable: Record<string, string>;
  settable: Record<string, string>;
  units: Record<string, string>;
  limits: Record<string, [number, number]>;
  tags: string[];
}

export const getInstrumentSchema = (id: string): Promise<InstrumentSchema> =>
  client.get<InstrumentSchema>(`/dashboard/instruments/${id}/schema`);

export const readInstrumentData = (id: string): Promise<Record<string, any>> =>
  client.get<Record<string, any>>(`/dashboard/instruments/${id}/data`);

export const writeInstrumentSettings = (
  id: string,
  values: Record<string, any>
): Promise<{ message: string }> =>
  client.post<{ message: string }>(`/dashboard/instruments/${id}/settings`, { values });

// Native-UI display preferences (e.g. an actuator's "use a live slider"
// toggle) — never written to the instrument itself. See
// core/config/instrument_ui_prefs.py. Keys are dynamic (declared per
// instrument kind by the backend's ui_prefs_schema, not fixed here) so
// new preferences don't need a new frontend field each time.
export type InstrumentUIPrefs = Record<string, any>;

// One declared display preference (the "tier 4" metaobject a native
// UIComponent exposes) — `kind` is a rendering hint ("bool" today; room
// to grow) so InstrumentSettingsModal can render a generic form instead
// of one-off JSX per preference.
export interface DisplayPrefSpec {
  kind: string;
  label: string;
  default: any;
}

export type InstrumentUIPrefsSchema = Record<string, DisplayPrefSpec>;

export const getInstrumentUIPrefs = (id: string): Promise<InstrumentUIPrefs> =>
  client.get<InstrumentUIPrefs>(`/dashboard/instruments/${id}/ui_prefs`);

export const getInstrumentUIPrefsSchema = (id: string): Promise<InstrumentUIPrefsSchema> =>
  client.get<InstrumentUIPrefsSchema>(`/dashboard/instruments/${id}/ui_prefs_schema`);

export const writeInstrumentUIPrefs = (
  id: string,
  prefs: InstrumentUIPrefs
): Promise<{ message: string }> =>
  client.put<{ message: string }>(`/dashboard/instruments/${id}/ui_prefs`, { prefs });

export interface CatalogEntry {
  adapter_key: string;
  manufacturer: string;
  model: string;
  display_name: string;
  instrument_type: string;
  backend: string;
  connection_types: string[];
  tags: string[];
}

export interface DashboardWorkflow {
  id: string;
  name: string;
  workflow_type: string;
  connected_instruments: string[];
  running: boolean;
  progress: number;
  has_data: boolean;
}

export interface DashboardConnection {
  instrument_id: string;
  workflow_id: string;
  type: string;
}

export interface DashboardState {
  instruments: DashboardInstrument[];
  workflows: DashboardWorkflow[];
  connections: DashboardConnection[];
}

export const getDashboardState = (): Promise<DashboardState> =>
  client.get<DashboardState>('/dashboard/state');

export const getDashboardInstruments = (): Promise<DashboardInstrument[]> =>
  client.get<DashboardInstrument[]>('/dashboard/instruments');

export const getDashboardWorkflows = (): Promise<DashboardWorkflow[]> =>
  client.get<DashboardWorkflow[]>('/dashboard/workflows');

export const executeDashboardWorkflow = (
  workflowId: string,
  config?: any
): Promise<{ message: string; data: string }> =>
  client.post<{ message: string; data: string }>(
    `/dashboard/workflows/${workflowId}/execute`,
    { workflow_id: workflowId, config }
  );

export const stopDashboardWorkflow = (workflowId: string): Promise<{ message: string }> =>
  client.post<{ message: string }>(`/dashboard/workflows/${workflowId}/stop`, {});

export const getCatalog = (): Promise<CatalogEntry[]> =>
  client.get<CatalogEntry[]>('/dashboard/catalog');

export const createInstrument = (
  adapterKey: string,
  opts: { id?: string; name?: string; connectionParams?: Record<string, any> } = {}
): Promise<DashboardInstrument> =>
  client.post<DashboardInstrument>('/dashboard/instruments', {
    adapter_key: adapterKey,
    id: opts.id,
    name: opts.name,
    connection_params: opts.connectionParams || {},
  });

export const connectInstrument = (id: string): Promise<DashboardInstrument> =>
  client.post<DashboardInstrument>(`/dashboard/instruments/${id}/connect`, {});

export const disconnectInstrument = (id: string): Promise<DashboardInstrument> =>
  client.post<DashboardInstrument>(`/dashboard/instruments/${id}/disconnect`, {});

export const removeInstrument = (id: string): Promise<{ message: string }> =>
  client.delete<{ message: string }>(`/dashboard/instruments/${id}`);

export const updateInstrumentConnection = (
  id: string,
  connectionParams: Record<string, any>
): Promise<DashboardInstrument> =>
  client.patch<DashboardInstrument>(`/dashboard/instruments/${id}/connection`, {
    connection_params: connectionParams,
  });

export interface InstrumentConfigList {
  configs: string[];
  active: string | null;
}

export const getInstrumentConfigs = (): Promise<InstrumentConfigList> =>
  client.get<InstrumentConfigList>('/dashboard/configs');

export interface ActivateConfigResult {
  active: string;
  instruments: DashboardInstrument[];
}

export const activateInstrumentConfig = (name: string): Promise<ActivateConfigResult> =>
  client.post<ActivateConfigResult>(`/dashboard/configs/${name}/activate`, {});

export const newInstrumentConfig = (name: string): Promise<ActivateConfigResult> =>
  client.post<ActivateConfigResult>('/dashboard/configs/new', { name });

export const uploadInstrumentConfig = (
  name: string,
  devices: Record<string, any>[]
): Promise<ActivateConfigResult> =>
  client.post<ActivateConfigResult>('/dashboard/configs/upload', { name, devices });

export const deleteInstrumentConfig = (name: string): Promise<{ message: string }> =>
  client.delete<{ message: string }>(`/dashboard/configs/${name}`);

// Export all API functions
export const api = {
  getSessionStatus,
  getDevices,
  connectDevice,
  disconnectDevice,
  getWorkflows,
  createWorkflow,
  executeWorkflow,
  sendMessage,
  getConversations,
  getConfig,
  updateConfig,
  getDashboardState,
  getDashboardInstruments,
  getDashboardWorkflows,
  executeDashboardWorkflow,
  stopDashboardWorkflow,
  getCatalog,
  createInstrument,
  connectInstrument,
  disconnectInstrument,
  removeInstrument,
  updateInstrumentConnection,
};

// WebSocket Manager
class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private listeners: Map<string, Function[]> = new Map();

  constructor(url: string) {
    this.url = url;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            this.handleMessage(message);
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        this.ws.onclose = () => {
          console.log('WebSocket disconnected');
          this.handleReconnect();
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          if (this.reconnectAttempts === 0) {
            reject(error);
          }
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  private handleMessage(message: WebSocketMessage) {
    if (message.type === 'event' && message.event) {
      this.emit('event', message.event);
    }
  }

  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => {
        console.log(`Attempting to reconnect WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        this.connect().catch(console.error);
      }, this.reconnectDelay * this.reconnectAttempts);
    }
  }

  addEventListener(event: string, listener: Function) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event)!.push(listener);
  }

  removeEventListener(event: string, listener: Function) {
    const listeners = this.listeners.get(event);
    if (listeners) {
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  private emit(event: string, data: any) {
    const listeners = this.listeners.get(event);
    if (listeners) {
      listeners.forEach(listener => listener(data));
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Create WebSocket manager instance
export const wsManager = new WebSocketManager(WS_BASE_URL);

// Export default
export default api;