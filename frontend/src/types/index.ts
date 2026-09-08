// Core types for LabPilot frontend

export interface SessionStatus {
  session_id: string;
  devices_connected: number;
  ai_available: boolean;
  workflow_engine_running: number;
}

export interface Device {
  name: string;
  adapter_type: string;
  connected: boolean;
  status: string;
  error?: string;
  last_reading?: any;
  connection_params?: Record<string, any>;
}

export interface Workflow {
  id: string;
  name: string;
  version: number;
  status: 'ready' | 'running' | 'completed' | 'error';
  created_at: number;
  updated_at: number;
  description?: string;
}

export interface UserPreferences {
  theme: 'light' | 'dark';
  units: 'metric' | 'imperial';
  decimal_places: number;
  auto_save: boolean;
}

export interface UIState {
  sidebarOpen: boolean;
  activeTab: 'devices' | 'workflows' | 'data';
  theme: 'light' | 'dark';
  loading: boolean;
  notifications: Notification[];
}

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: number;
  duration?: number;
}

export interface LabPilotEvent {
  uid: string;
  kind: string;
  timestamp: number;
  data?: any;
}

// API Request/Response types
export interface DeviceConnectionRequest {
  name: string;
  adapter_type: string;
  connection_params: Record<string, any>;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  use_tools?: boolean;
}

export interface ChatResponse {
  response: string;
  tool_calls?: number;
  conversation_id: string;
}

export interface WorkflowExecutionRequest {
  workflow_id: string;
  version?: number;
}

export interface WorkflowExecutionResponse {
  execution_id: string;
  status: string;
}
// ---- Transport ----
//
// These two describe what the backend actually puts on the wire, and were
// missing: `api/index.ts` imported both, so the module — and with it the
// WebSocketManager defined in it — did not typecheck. That is why the
// manager was written and never wired to anything.

/** Every REST route's envelope — see `core/server.py`'s `ApiResponse`. */
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string | null;
  timestamp?: number;
}

/**
 * One frame on `/ws`. The server sends `{type: "event", event}` for every
 * event on the session bus (see `LabPilotServer._event_broadcaster`) and
 * `{type: "pong"}` in reply to a ping.
 */
export interface WebSocketMessage {
  type: 'event' | 'pong' | string;
  event?: LabPilotEvent;
}
