import { api } from '@/api';

export interface ChatSession {
  id: string;
  name: string;
  created: string;
  lastModified: string;
  messages: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
  }>;
}

export class ChatSessionManager {
  private static readonly STORAGE_KEY = 'labpilot-chat-sessions';
  private static readonly CURRENT_SESSION_KEY = 'labpilot-current-session';

  private static generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  static getAllSessions(): ChatSession[] {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  }

  static getCurrentSessionId(): string | null {
    return localStorage.getItem(this.CURRENT_SESSION_KEY);
  }

  static setCurrentSession(sessionId: string): void {
    localStorage.setItem(this.CURRENT_SESSION_KEY, sessionId);
  }

  static createNewSession(name?: string): ChatSession {
    const session: ChatSession = {
      id: this.generateId(),
      name: name || `Chat ${new Date().toLocaleDateString()}`,
      created: new Date().toISOString(),
      lastModified: new Date().toISOString(),
      messages: [],
    };

    this.saveSession(session);
    this.setCurrentSession(session.id);
    return session;
  }

  static getSession(sessionId: string): ChatSession | null {
    const sessions = this.getAllSessions();
    return sessions.find(s => s.id === sessionId) || null;
  }

  static getCurrentSession(): ChatSession | null {
    const currentId = this.getCurrentSessionId();
    if (!currentId) return null;
    return this.getSession(currentId);
  }

  static saveSession(session: ChatSession): void {
    const sessions = this.getAllSessions();
    const existingIndex = sessions.findIndex(s => s.id === session.id);

    session.lastModified = new Date().toISOString();

    if (existingIndex >= 0) {
      sessions[existingIndex] = session;
    } else {
      sessions.push(session);
    }

    // Keep only the latest 50 sessions
    const sortedSessions = sessions
      .sort((a, b) => new Date(b.lastModified).getTime() - new Date(a.lastModified).getTime())
      .slice(0, 50);

    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(sortedSessions));
  }

  static deleteSession(sessionId: string): void {
    const sessions = this.getAllSessions();
    const filteredSessions = sessions.filter(s => s.id !== sessionId);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(filteredSessions));

    // If we deleted the current session, clear the current session
    if (this.getCurrentSessionId() === sessionId) {
      localStorage.removeItem(this.CURRENT_SESSION_KEY);
    }
  }

  static addMessage(
    sessionId: string,
    role: 'user' | 'assistant',
    content: string
  ): void {
    const session = this.getSession(sessionId);
    if (!session) return;

    const message = {
      id: this.generateId(),
      role,
      content,
      timestamp: new Date().toISOString(),
    };

    session.messages.push(message);
    this.saveSession(session);
  }

  static updateSessionName(sessionId: string, newName: string): void {
    const session = this.getSession(sessionId);
    if (!session) return;

    session.name = newName;
    this.saveSession(session);
  }

  static exportSession(sessionId: string): string {
    const session = this.getSession(sessionId);
    if (!session) return '';

    return JSON.stringify(session, null, 2);
  }

  static importSession(sessionData: string): ChatSession | null {
    try {
      const session: ChatSession = JSON.parse(sessionData);

      // Validate session structure
      if (!session.id || !session.name || !Array.isArray(session.messages)) {
        throw new Error('Invalid session format');
      }

      // Generate new ID to avoid conflicts
      session.id = this.generateId();
      session.lastModified = new Date().toISOString();

      this.saveSession(session);
      return session;
    } catch (error) {
      console.error('Failed to import session:', error);
      return null;
    }
  }

  static searchSessions(query: string): ChatSession[] {
    const sessions = this.getAllSessions();
    const lowerQuery = query.toLowerCase();

    return sessions.filter(session =>
      session.name.toLowerCase().includes(lowerQuery) ||
      session.messages.some(msg =>
        msg.content.toLowerCase().includes(lowerQuery)
      )
    );
  }

  static clearAllSessions(): void {
    localStorage.removeItem(this.STORAGE_KEY);
    localStorage.removeItem(this.CURRENT_SESSION_KEY);
  }
}