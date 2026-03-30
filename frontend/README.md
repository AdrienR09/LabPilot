# LabPilot Frontend

Modern React-based web interface for the LabPilot AI laboratory automation system.

## Features

- 🎨 **Modern UI**: Clean, responsive interface with dark/light theme support
- 🤖 **AI Integration**: Real-time chat with AI assistant, tool calling, and streaming responses
- 🔧 **Device Management**: Connect and control laboratory instruments
- 🔀 **Workflow Editor**: Create and execute automated experiment workflows
- 📊 **Real-time Updates**: WebSocket integration for live system monitoring
- 💾 **State Management**: Zustand-based global state with persistence
- 🔄 **API Integration**: Type-safe communication with FastAPI backend

## Technology Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS with custom components
- **State Management**: Zustand with Immer middleware
- **API Client**: Axios with React Query
- **Real-time**: WebSockets
- **Icons**: Lucide React
- **Routing**: React Router DOM
- **Notifications**: React Hot Toast
- **Code Highlighting**: React Syntax Highlighter
- **Markdown**: React Markdown

## Quick Start

### Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:3000` and automatically proxy API requests to the FastAPI backend at `http://localhost:8000`.

### Production Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── api/           # API client and WebSocket management
│   ├── components/    # Reusable UI components
│   │   ├── Layout/    # Layout components (Header, Sidebar)
│   │   └── ...
│   ├── pages/         # Page components
│   │   ├── Dashboard.tsx
│   │   ├── Devices.tsx
│   │   ├── Workflows.tsx
│   │   ├── AIChat.tsx
│   │   └── ...
│   ├── store/         # Zustand state management
│   ├── styles/        # Global CSS and Tailwind
│   ├── types/         # TypeScript type definitions
│   ├── App.tsx        # Main application component
│   └── main.tsx       # Application entry point
├── public/            # Static assets
└── package.json       # Dependencies and scripts
```

## API Integration

The frontend communicates with the LabPilot FastAPI backend through:

- **REST API**: HTTP requests for CRUD operations
- **WebSocket**: Real-time events and system updates
- **Server-Sent Events**: Streaming AI chat responses

All API calls are typed and handled through the centralized API client in `src/api/index.ts`.

## State Management

Global application state is managed using Zustand with the following stores:

- **Session State**: Connection status, system information
- **Devices**: Connected instruments and their status
- **Workflows**: Automation workflows and execution
- **AI Chat**: Conversations and messaging
- **UI State**: Theme, sidebar, notifications, loading states

## Component Architecture

### Pages
- **Dashboard**: System overview and quick stats
- **Devices**: Instrument connection and management
- **Workflows**: Automation workflow creation and execution
- **AI Chat**: Real-time AI assistant interaction
- **Data**: Data visualization and management (coming soon)
- **Settings**: User preferences and system configuration

### Layout Components
- **Header**: Navigation, status indicators, theme toggle
- **Sidebar**: Navigation menu with system status
- **Layout**: Main wrapper combining header and sidebar

## WebSocket Events

The frontend listens for real-time events from the backend:

```typescript
{
  type: 'event',
  event: {
    kind: 'DEVICE_CONNECTED' | 'WORKFLOW_STARTED' | 'AI_MESSAGE_RECEIVED' | ...,
    data: { ... },
    timestamp: number
  }
}
```

## Styling

- **Tailwind CSS**: Utility-first styling with custom theme
- **Dark Mode**: Automatic theme switching with persistence
- **Responsive**: Mobile-first design approach
- **Icons**: Lucide React icon library
- **Typography**: Inter font family with JetBrains Mono for code

## Development Guidelines

### Code Style
- Use TypeScript for all components
- Follow functional component patterns with hooks
- Use Tailwind CSS for styling
- Implement proper error boundaries
- Add loading states for async operations

### Performance
- Lazy load heavy components
- Use React.memo for expensive renders
- Implement proper key props for lists
- Debounce user inputs where appropriate

### Accessibility
- Semantic HTML elements
- ARIA labels for interactive elements
- Keyboard navigation support
- High contrast color schemes

## Environment Variables

Create a `.env.local` file for local development:

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/ws
```

## Browser Support

- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

Modern browsers with ES2020 support and WebSocket capabilities are required.

## Contributing

1. Follow the existing code style and patterns
2. Add TypeScript types for all new interfaces
3. Include proper error handling
4. Test components with different states
5. Update this README when adding new features

## Integration with Backend

The frontend is designed to work seamlessly with the LabPilot FastAPI backend:

```bash
# Backend server (from project root)
cd labpilot
python -m uvicorn labpilot_core.server:app --reload --port 8000

# Frontend development server (from project root)
cd frontend
npm run dev
```

The Vite development server automatically proxies API requests to the backend, enabling full-stack development with hot reloading.