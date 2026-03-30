import React, { useState, useRef, useEffect } from 'react';
import { useLabPilotStore } from '@/store';
import { StructuredInputForm } from '@/components/StructuredInputForm/index';
import { ChatSessionModal } from '@/components/ChatSessionModal';
import { ChatSessionManager, ChatSession } from '@/utils/chatSessionManager';
import { FolderOpen, Save } from 'lucide-react';

export function ChatBox() {
  const {
    currentConversation,
    chatLoading,
    chatError,
    session,
    sendMessage,
    clearChat,
  } = useLabPilotStore((state) => ({
    currentConversation: state.currentConversation,
    chatLoading: state.chatLoading,
    chatError: state.chatError,
    session: state.session,
    sendMessage: state.sendMessage,
    clearChat: state.clearChat,
  }));

  const [inputValue, setInputValue] = useState('');
  const [showLogs, setShowLogs] = useState(false);
  const [showSessionModal, setShowSessionModal] = useState(false);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentConversation?.messages]);

  // Load current session on mount
  useEffect(() => {
    const session = ChatSessionManager.getCurrentSession();
    if (session) {
      setCurrentSession(session);
    }
  }, []);

  // Save messages to session when they change
  useEffect(() => {
    if (currentSession && currentConversation?.messages) {
      // Update session with current messages
      const updatedSession = {
        ...currentSession,
        messages: currentConversation.messages.map(msg => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp,
        })),
      };
      ChatSessionManager.saveSession(updatedSession);
      setCurrentSession(updatedSession);
    }
  }, [currentConversation?.messages, currentSession?.id]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || chatLoading) return;

    const message = inputValue;
    setInputValue('');
    await sendMessage(message);
  };

  const handleStructuredSubmit = async (values: Record<string, string | number | boolean>) => {
    const message = Object.entries(values)
      .map(([key, value]) => `${key}: ${value}`)
      .join(', ');
    setInputValue('');
    await sendMessage(message);
  };

  const handleClear = () => {
    clearChat();
    setInputValue('');
  };

  const handleSaveSession = () => {
    if (currentConversation?.messages && currentConversation.messages.length > 0) {
      let session = currentSession;

      if (!session) {
        // Create new session
        session = ChatSessionManager.createNewSession();
        setCurrentSession(session);
      }

      // Save current messages to session
      const updatedSession = {
        ...session,
        messages: currentConversation.messages.map(msg => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp,
        })),
      };

      ChatSessionManager.saveSession(updatedSession);
      setCurrentSession(updatedSession);

      alert('Session saved successfully!');
    }
  };

  const handleSessionSelected = (session: ChatSession) => {
    setCurrentSession(session);

    // Load session messages into current conversation
    // This would require updating the store to load session messages
    // For now, we'll just show the session is loaded
    console.log('Loaded session:', session.name, 'with', session.messages.length, 'messages');

    // In a full implementation, you'd want to:
    // loadConversation(session.messages);
  };

  const handleNewSession = () => {
    const newSession = ChatSessionManager.createNewSession();
    setCurrentSession(newSession);
    clearChat();
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 h-full min-h-[600px] flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Lab Assistant Chat</h2>
          {currentSession && (
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {currentSession.name}
            </span>
          )}
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowSessionModal(true)}
            className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
            title="Manage Sessions"
          >
            <FolderOpen className="h-4 w-4" />
          </button>
          {currentConversation && currentConversation.messages.length > 0 && (
            <>
              <button
                onClick={handleSaveSession}
                className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                title="Save Session"
              >
                <Save className="h-4 w-4" />
              </button>
              <button
                onClick={handleClear}
                className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                Clear Chat
              </button>
            </>
          )}
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {!session.aiAvailable ? (
          <div className="text-center py-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
              <span className="text-2xl">🤖</span>
            </div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">AI Assistant Unavailable</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
              Configure an AI provider (Ollama, OpenAI, etc.) in your backend to enable the AI assistant.
            </p>
          </div>
        ) : !currentConversation || currentConversation.messages.length === 0 ? (
          <div className="text-center py-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
              <span className="text-2xl">👋</span>
            </div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">Welcome to Lab Assistant</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
              I'm your AI laboratory assistant. I can help you control devices, create workflows, and analyze data. How can I assist you today?
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {currentConversation.messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-xs rounded-lg px-4 py-3 ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-br-none'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white rounded-bl-none'
                  }`}
                >
                  <p className="text-sm break-words whitespace-pre-wrap">{msg.content}</p>
                  <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'}`}>
                    {new Date(msg.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
              </div>
            ))}
            {/* Show structured prompt if latest message has one */}
            {currentConversation.messages.length > 0 &&
              currentConversation.messages[currentConversation.messages.length - 1].role === 'assistant' &&
              currentConversation.messages[currentConversation.messages.length - 1].structuredPrompt && (
                <div className="flex justify-start">
                  <div className="max-w-sm w-full">
                    <StructuredInputForm
                      prompt={currentConversation.messages[currentConversation.messages.length - 1].structuredPrompt!}
                      onSubmit={handleStructuredSubmit}
                      isLoading={chatLoading}
                    />
                  </div>
                </div>
              )}
            {chatLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg rounded-bl-none px-4 py-3">
                  <div className="flex space-x-2">
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                </div>
              </div>
            )}
            {chatError && (
              <div className="flex justify-center">
                <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-lg px-4 py-3 text-sm max-w-xs">
                  {chatError}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700">
        {!session.aiAvailable ? (
          <div className="text-center text-sm text-gray-500 dark:text-gray-400 py-2">
            AI assistant is not available
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex space-x-3">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={chatLoading ? 'Waiting for response...' : 'Ask me anything...'}
                disabled={chatLoading}
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                type="submit"
                disabled={chatLoading || !inputValue.trim()}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {chatLoading ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                )}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Session Management Modal */}
      <ChatSessionModal
        isOpen={showSessionModal}
        onClose={() => setShowSessionModal(false)}
        onSessionSelected={handleSessionSelected}
        currentSessionId={currentSession?.id}
      />
    </div>
  );
}
