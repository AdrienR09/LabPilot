/**
 * Shared instrument types.
 *
 * This used to also hold a ~1150-line hardcoded fake instrument catalog
 * (DETECTOR_0D, ACTUATOR_1D, etc.) used as a fallback when the backend was
 * unreachable. Removed: instruments now always come from the real backend
 * catalog (`GET /api/dashboard/catalog`, backed by `instruments/`) — no
 * fake/fallback data. If the backend is down, the UI should show that
 * state rather than silently substituting fabricated instruments.
 */

export interface Parameter {
  name: string;
  type: 'number' | 'text' | 'select' | 'boolean';
  value: any;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  description?: string;
}

export interface Instrument {
  id: string;
  name: string;
  manufacturer: string;
  modelNumber: string;
  adapterType: string;
  category: string;
  connected: boolean;
  kind: 'detector' | 'source' | 'motor' | 'actuator';
  dimensionality: '0D' | '1D' | '2D' | '3D';
  tags: string[];
  description: string;
  parameters: Record<string, Parameter>;
}
