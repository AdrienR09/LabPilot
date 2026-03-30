import React, { useState, useRef, useEffect } from 'react';
import { X, Minimize2, Maximize2, Settings as SettingsIcon } from 'lucide-react';

interface FloatingWindowProps {
  title: string;
  children: React.ReactNode;
  isOpen: boolean;
  onClose: () => void;
  initialWidth?: number;
  initialHeight?: number;
  initialX?: number;
  initialY?: number;
  minWidth?: number;
  minHeight?: number;
  resizable?: boolean;
  showSettings?: boolean;
  onSettingsClick?: () => void;
}

export function FloatingWindow({
  title,
  children,
  isOpen,
  onClose,
  initialWidth = 800,
  initialHeight = 600,
  initialX,
  initialY,
  minWidth = 400,
  minHeight = 300,
  resizable = true,
  showSettings = false,
  onSettingsClick,
}: FloatingWindowProps) {
  const [position, setPosition] = useState(() => ({
    x: initialX ?? Math.random() * 200 + 100,
    y: initialY ?? Math.random() * 100 + 100,
  }));
  const [size, setSize] = useState({
    width: initialWidth,
    height: initialHeight,
  });
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [resizeStart, setResizeStart] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const [isMinimized, setIsMinimized] = useState(false);

  const windowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        setPosition({
          x: e.clientX - dragStart.x,
          y: e.clientY - dragStart.y,
        });
      } else if (isResizing) {
        const newWidth = Math.max(minWidth, resizeStart.width + (e.clientX - resizeStart.x));
        const newHeight = Math.max(minHeight, resizeStart.height + (e.clientY - resizeStart.y));
        setSize({ width: newWidth, height: newHeight });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(false);
    };

    if (isDragging || isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizing, dragStart, resizeStart, minWidth, minHeight]);

  if (!isOpen) return null;

  const handleHeaderMouseDown = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains('drag-handle')) {
      setIsDragging(true);
      setDragStart({
        x: e.clientX - position.x,
        y: e.clientY - position.y,
      });
    }
  };

  const handleResizeMouseDown = (e: React.MouseEvent) => {
    if (!resizable) return;
    e.preventDefault();
    setIsResizing(true);
    setResizeStart({
      x: e.clientX,
      y: e.clientY,
      width: size.width,
      height: size.height,
    });
  };

  return (
    <div
      ref={windowRef}
      className="fixed bg-white dark:bg-gray-800 rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700 select-none overflow-hidden"
      style={{
        left: position.x,
        top: position.y,
        width: size.width,
        height: isMinimized ? 'auto' : size.height,
        zIndex: 1000,
      }}
    >
      {/* Window Header */}
      <div
        className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600 cursor-move drag-handle"
        onMouseDown={handleHeaderMouseDown}
      >
        <div className="flex items-center space-x-3">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white drag-handle">
            {title}
          </h3>
        </div>
        <div className="flex items-center space-x-1">
          <button
            onClick={() => setIsMinimized(!isMinimized)}
            className="p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition-colors"
          >
            <Minimize2 className="h-4 w-4" />
          </button>
          {showSettings && (
            <button
              onClick={onSettingsClick}
              className="p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition-colors"
            >
              <SettingsIcon className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 text-gray-500 hover:text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Window Content */}
      {!isMinimized && (
        <div className="flex-1 overflow-auto h-full">
          <div className="p-4 h-full">
            {children}
          </div>
        </div>
      )}

      {/* Resize Handle */}
      {resizable && !isMinimized && (
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize bg-gray-300 dark:bg-gray-600"
          onMouseDown={handleResizeMouseDown}
          style={{
            background: 'linear-gradient(-45deg, transparent 30%, currentColor 30%, currentColor 40%, transparent 40%, transparent 60%, currentColor 60%, currentColor 70%, transparent 70%)',
          }}
        />
      )}
    </div>
  );
}