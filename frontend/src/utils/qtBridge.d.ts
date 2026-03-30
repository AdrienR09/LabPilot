export interface QtBridge {
  isInQt: () => boolean;
  launchInstrumentUI: (instrumentId: string) => void;
  connectInstrument: (params: Record<string, any>) => Promise<void>;
  disconnectInstrument: (instrumentId: string) => Promise<void>;
  [key: string]: any;
}

export const qtBridge: QtBridge;
export function initQtBridge(callback?: () => void): void;
