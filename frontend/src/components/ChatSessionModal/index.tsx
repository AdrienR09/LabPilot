import React, { useState, useEffect } from 'react';
import {
  Save,
  FolderOpen,
  Trash2,
  Edit3,
  Download,
  Upload,
  Search,
  Plus,
  MessageCircle,
  Calendar,
  X,
} from 'lucide-react';
import { ChatSessionManager, ChatSession } from '@/utils/chatSessionManager';

interface ChatSessionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSessionSelected: (session: ChatSession) => void;
  currentSessionId?: string | null;
}

export function ChatSessionModal({
  isOpen,
  onClose,
  onSessionSelected,
  currentSessionId,
}: ChatSessionModalProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingSession, setEditingSession] = useState<string | null>(null);
  const [newSessionName, setNewSessionName] = useState('');
  const [activeTab, setActiveTab] = useState<'browse' | 'import'>('browse');

  useEffect(() => {
    if (isOpen) {
      loadSessions();
    }
  }, [isOpen]);

  const loadSessions = () => {
    const allSessions = ChatSessionManager.getAllSessions();
    setSessions(allSessions);
  };

  const filteredSessions = searchQuery
    ? ChatSessionManager.searchSessions(searchQuery)
    : sessions;

  const handleNewSession = () => {
    const newSession = ChatSessionManager.createNewSession();
    onSessionSelected(newSession);
    loadSessions();
    onClose();
  };

  const handleSessionSelect = (session: ChatSession) => {
    ChatSessionManager.setCurrentSession(session.id);
    onSessionSelected(session);
    onClose();
  };

  const handleDeleteSession = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this chat session?')) {
      ChatSessionManager.deleteSession(sessionId);
      loadSessions();
    }
  };

  const handleRenameSession = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const session = sessions.find(s => s.id === sessionId);
    if (session) {
      setEditingSession(sessionId);
      setNewSessionName(session.name);
    }
  };

  const handleSaveRename = (sessionId: string) => {
    if (newSessionName.trim()) {
      ChatSessionManager.updateSessionName(sessionId, newSessionName.trim());
      setEditingSession(null);
      setNewSessionName('');
      loadSessions();
    }
  };

  const handleCancelRename = () => {
    setEditingSession(null);
    setNewSessionName('');
  };

  const handleExportSession = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const exportData = ChatSessionManager.exportSession(sessionId);
    const session = sessions.find(s => s.id === sessionId);

    if (exportData && session) {
      const blob = new Blob([exportData], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${session.name.replace(/[^a-z0-9]/gi, '_')}_chat_session.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  const handleImportSession = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      const importedSession = ChatSessionManager.importSession(content);

      if (importedSession) {
        loadSessions();
        alert('Session imported successfully!');
        setActiveTab('browse');
      } else {
        alert('Failed to import session. Please check the file format.');
      }
    };

    reader.readAsText(file);
    event.target.value = ''; // Reset file input
  };

  const handleClearAllSessions = () => {
    if (confirm('Are you sure you want to delete ALL chat sessions? This cannot be undone.')) {
      ChatSessionManager.clearAllSessions();
      setSessions([]);
      setSearchQuery('');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-full max-w-4xl mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Chat Sessions</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab('browse')}
            className={`px-6 py-3 font-medium transition-colors ${
              activeTab === 'browse'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            Browse Sessions
          </button>
          <button
            onClick={() => setActiveTab('import')}
            className={`px-6 py-3 font-medium transition-colors ${
              activeTab === 'import'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            Import/Export
          </button>
        </div>

        <div className="p-6">
          {activeTab === 'browse' && (
            <div className="space-y-6">
              {/* Actions */}
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <button
                    onClick={handleNewSession}
                    className="inline-flex items-center px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    New Session
                  </button>

                  {/* Search */}
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search sessions..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white w-64"
                    />
                  </div>
                </div>

                {sessions.length > 0 && (
                  <button
                    onClick={handleClearAllSessions}
                    className="text-red-600 hover:text-red-700 text-sm font-medium"
                  >
                    Clear All
                  </button>
                )}
              </div>

              {/* Sessions List */}
              <div className="max-h-96 overflow-y-auto">
                {filteredSessions.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    {searchQuery ? 'No sessions match your search.' : 'No chat sessions yet.'}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {filteredSessions.map((session) => (
                      <div
                        key={session.id}
                        onClick={() => handleSessionSelect(session)}
                        className={`p-4 rounded-lg border cursor-pointer transition-all hover:shadow-md ${
                          currentSessionId === session.id
                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            {editingSession === session.id ? (
                              <div className="flex items-center space-x-2">
                                <input
                                  type="text"
                                  value={newSessionName}
                                  onChange={(e) => setNewSessionName(e.target.value)}
                                  onKeyPress={(e) => {
                                    if (e.key === 'Enter') handleSaveRename(session.id);
                                    if (e.key === 'Escape') handleCancelRename();
                                  }}
                                  className="flex-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                                  autoFocus
                                />
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleSaveRename(session.id);
                                  }}
                                  className="p-1 text-green-600 hover:text-green-700"
                                >
                                  <Save className="h-4 w-4" />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleCancelRename();
                                  }}
                                  className="p-1 text-gray-600 hover:text-gray-700"
                                >
                                  <X className="h-4 w-4" />
                                </button>
                              </div>
                            ) : (
                              <div>
                                <div className="flex items-center space-x-2">
                                  <MessageCircle className="h-4 w-4 text-blue-600" />
                                  <h3 className="font-medium text-gray-900 dark:text-white">
                                    {session.name}
                                  </h3>
                                  {currentSessionId === session.id && (
                                    <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded">
                                      Current
                                    </span>
                                  )}
                                </div>
                                <div className="mt-1 flex items-center space-x-4 text-xs text-gray-500 dark:text-gray-400">
                                  <span className="flex items-center">
                                    <Calendar className="h-3 w-3 mr-1" />
                                    {new Date(session.lastModified).toLocaleDateString()}
                                  </span>
                                  <span>{session.messages.length} messages</span>
                                </div>
                                {session.messages.length > 0 && (
                                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                                    {session.messages[session.messages.length - 1]?.content.slice(0, 100)}...
                                  </p>
                                )}
                              </div>
                            )}
                          </div>

                          {editingSession !== session.id && (
                            <div className="flex items-center space-x-1 ml-4">
                              <button
                                onClick={(e) => handleRenameSession(session.id, e)}
                                className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                                title="Rename"
                              >
                                <Edit3 className="h-4 w-4" />
                              </button>
                              <button
                                onClick={(e) => handleExportSession(session.id, e)}
                                className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                                title="Export"
                              >
                                <Download className="h-4 w-4" />
                              </button>
                              <button
                                onClick={(e) => handleDeleteSession(session.id, e)}
                                className="p-1.5 text-red-400 hover:text-red-600"
                                title="Delete"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'import' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                  Import Session
                </h3>
                <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-8 text-center">
                  <Upload className="h-8 w-8 mx-auto text-gray-400 mb-4" />
                  <div className="space-y-2">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      Select a JSON file to import a chat session
                    </p>
                    <label className="inline-block">
                      <input
                        type="file"
                        accept=".json"
                        onChange={handleImportSession}
                        className="hidden"
                      />
                      <span className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md cursor-pointer font-medium transition-colors">
                        Choose File
                      </span>
                    </label>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                  Export All Sessions
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  Download all your chat sessions as a single JSON file for backup.
                </p>
                <button
                  onClick={() => {
                    const allSessions = ChatSessionManager.getAllSessions();
                    const exportData = JSON.stringify(allSessions, null, 2);
                    const blob = new Blob([exportData], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `labpilot_chat_sessions_${new Date().toISOString().split('T')[0]}.json`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                  }}
                  disabled={sessions.length === 0}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white rounded-md font-medium transition-colors"
                >
                  <Download className="h-4 w-4 mr-2 inline" />
                  Export All Sessions
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}