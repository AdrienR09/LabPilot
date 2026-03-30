import React from 'react';
import { MessageSquare, Send } from 'lucide-react';

export default function AIChat() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Chat</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Interact with your laboratory AI assistant
        </p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow h-96 flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Lab Assistant
          </h2>
        </div>
        <div className="flex-1 p-6 flex items-center justify-center">
          <div className="text-center">
            <MessageSquare className="mx-auto h-12 w-12 text-gray-400" />
            <h3 className="mt-4 text-sm font-medium text-gray-900 dark:text-white">
              AI Assistant Ready
            </h3>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              Start a conversation to get help with your experiments.
            </p>
          </div>
        </div>
        <div className="p-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex space-x-3">
            <input
              type="text"
              placeholder="Type your message..."
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            />
            <button className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}