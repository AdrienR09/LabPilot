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
  client.post<{ execution_id: string }>(`/workflows/${id}/execute`, { version });

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
  data?: any;
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