# LabPilot Qt Material Manager

A complete Qt Material Design manager interface that replaces the React frontend with native Qt components.

## Overview

This Qt Material Manager provides all the functionality of the React frontend in a native Qt application with Material Design styling:

- **Dashboard**: System status overview with real-time metrics
- **Devices**: Instrument management with card-based layout
- **Workflows**: Experiment control and monitoring
- **AI Assistant**: Chat interface with tool execution
- **Data**: Results analysis and visualization
- **Settings**: Complete configuration management

## Features

✅ **Complete Qt Material Design Interface**
- Modern card-based layouts
- Material Design components and styling
- Responsive grid layouts
- Professional color scheme

✅ **Full Manager Functionality**
- Device connection/disconnection controls
- Workflow creation and execution
- AI assistant with chat interface
- Data visualization with pyqtgraph
- Settings management with multiple tabs

✅ **API Integration**
- REST API client for backend communication
- Real-time status updates
- Async operations with Qt threads
- Error handling and connection monitoring

✅ **Material Design Themes**
- Multiple built-in themes (light_blue, dark_blue, etc.)
- Dynamic theme switching
- Consistent styling across all components

## Installation

1. **Install Dependencies**:
```bash
cd labpilot/qt_frontend
pip install -r requirements.txt
```

2. **Key Dependencies**:
- PyQt6 (Qt framework)
- qt-material (Material Design styling)
- pyqtgraph (Scientific plotting)
- requests (HTTP client)

## Usage

### Method 1: Direct Launch
```bash
cd labpilot/qt_frontend
python manager_main.py
```

### Method 2: Test Script
```bash
cd labpilot/qt_frontend
python test_manager.py
```

### Method 3: With Options
```bash
python manager_main.py --theme dark_blue.xml --backend-url http://localhost:8000 --page devices
```

## Command Line Options

- `--theme THEME`: Choose Material Design theme (default: light_blue.xml)
- `--backend-url URL`: Backend server URL (default: http://localhost:8000)
- `--page PAGE`: Start on specific page (dashboard, devices, workflows, ai, data, settings)
- `--no-splash`: Skip splash screen
- `--debug`: Enable debug output

## Available Themes

Use `--theme` option with any of these Qt Material themes:
- `light_blue.xml` (default)
- `dark_blue.xml`
- `light_cyan.xml`
- `dark_cyan.xml`
- `light_lightgreen.xml`
- `dark_lightgreen.xml`
- `light_pink.xml`
- `dark_pink.xml`
- And many more...

## Architecture

### Main Components

1. **LabPilotMaterialManager**: Main window with sidebar navigation
2. **MaterialSidebar**: Navigation panel with page selection
3. **Page Classes**: Individual pages for each section
4. **LabPilotApiClient**: Backend communication layer

### Page Structure

Each page inherits from `BasePage` and implements:
- `setup_ui()`: Create the page layout
- `set_api_client()`: Set backend client
- `refresh_data()`: Update page data

### File Organization

```
qt_frontend/
├── manager_main.py              # Main entry point
├── qt_material_manager.py       # Main window and navigation
├── api_client.py               # Backend API integration
├── dashboard_page.py           # System overview page
├── devices_page.py             # Instrument management
├── workflows_page.py           # Experiment control
├── ai_assistant_page.py        # AI chat interface
├── data_page.py               # Results and analysis
├── settings_page.py           # Configuration management
├── test_manager.py             # Test script
└── requirements.txt           # Dependencies
```

## Features by Page

### Dashboard Page
- System status cards (devices, workflows, AI, data)
- Real-time metrics (CPU, memory, network)
- Recent events list
- Quick actions buttons

### Devices Page
- Grid-based device cards
- Connect/disconnect controls
- Device filtering (type, status)
- Qt interface launching
- Add/remove devices

### Workflows Page
- Workflow cards with status indicators
- Progress monitoring for running workflows
- Start/stop controls
- Create new experiments
- Results viewer

### AI Assistant Page
- Chat interface with message history
- Tool execution with progress indicators
- Available tools panel
- Capabilities information
- Real-time AI status

### Data Page
- Data file browser
- Tabbed viewer (plot, table, statistics)
- Import/export functionality
- pyqtgraph integration
- File management

### Settings Page
- Tabbed configuration (Appearance, Connection, Instruments, AI, Data)
- Theme selection with live preview
- Backend URL configuration
- AI provider settings
- Data management options

## Backend Integration

The manager communicates with the LabPilot backend via REST API:

- **Session Status**: `/api/session/status`
- **Devices**: `/api/devices/*`
- **Workflows**: `/api/workflows/*`
- **AI Chat**: `/api/ai/chat`
- **Data**: `/api/data/*`

Real-time updates are handled through periodic polling and signal/slot communication.

## Development

### Adding New Pages

1. Create new page class inheriting from `BasePage`
2. Implement required methods (`setup_ui`, `set_api_client`, `refresh_data`)
3. Add to `PageType` enum
4. Update `init_pages()` in main manager
5. Add navigation button in sidebar

### Customizing Themes

Qt Material themes can be customized by:
1. Modifying existing theme files
2. Creating new theme XML files
3. Using extra CSS parameters in `apply_stylesheet()`

### API Client Extension

Add new API endpoints by:
1. Adding methods to `LabPilotApiClient`
2. Implementing proper error handling
3. Emitting appropriate signals for UI updates

## Troubleshooting

### Common Issues

1. **Qt Material not found**: Install with `pip install qt-material`
2. **PyQt6 import error**: Install with `pip install PyQt6`
3. **Backend connection failed**: Check backend URL and server status
4. **Theme not loading**: Verify theme name is correct

### Debug Mode

Use `--debug` flag for detailed output:
```bash
python manager_main.py --debug
```

This will show:
- Theme information
- Backend connection status
- Page loading details
- API call results

## Comparison with React Frontend

| Feature | React Frontend | Qt Material Manager |
|---------|---------------|-------------------|
| Technology | React + TypeScript | PyQt6 + Material Design |
| Styling | Tailwind CSS | Qt Material themes |
| State Management | Zustand | Qt signals/slots |
| API Communication | Fetch/WebSocket | Requests + QNetwork |
| Performance | Web browser | Native desktop |
| Installation | npm install | pip install |
| Deployment | Web server | Desktop executable |

Both interfaces provide the same functionality but with different technology stacks and user experiences.

## Future Enhancements

- [ ] WebSocket integration for real-time updates
- [ ] Flow Chart page implementation
- [ ] Advanced data visualization options
- [ ] Custom theme creation tools
- [ ] Plugin system for additional pages
- [ ] Session persistence and restoration
- [ ] Multi-language support