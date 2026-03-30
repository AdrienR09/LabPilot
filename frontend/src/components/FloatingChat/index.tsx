import React, { useState } from 'react';
import { useLabPilotStore } from '@/store';
import { ChatBox } from '@/components/ChatBox/index';

export function FloatingChat() {
  const [isOpen, setIsOpen] = useState(false);
  const session = useLabPilotStore((state) => state.session);

  if (!session.aiAvailable) {
    return null;
  }

  return (
    <div className="fixed bottom-6 right-6 z-40">
      {/* Chat Widget */}
      {isOpen && (
        <div className="absolute bottom-20 right-0 w-96 max-h-[600px] shadow-2xl rounded-lg overflow-hidden">
          <ChatBox />
        </div>
      )}

      {/* Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-14 h-14 rounded-full bg-blue-600 hover:bg-blue-700 text-white shadow-lg flex items-center justify-center transition-all duration-200 hover:scale-110 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2"
        title={isOpen ? 'Close chat' : 'Open chat'}
      >
        {isOpen ? (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </button>
    </div>
  );
}
