# LabPilot Manager - Qt + React Architecture

## Overview

The LabPilot Manager now uses a **hybrid Qt + React architecture**:

- **Manager Interface**: React app (that you already like) embedded in a Qt window via QWebEngineView
- **Instrument UIs**: Native Qt windows with PyQtGraph for real-time instrument control

This gives you the best of both worlds:
- Keep your beautiful React design for the manager
- Use powerful Qt/PyQtGraph for instrument control windows

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Qt Main Window (QMainWindow)               │
│  ┌───────────────────────────────────────────────────┐  │
│  │        QWebEngineView                             │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │                                             │  │  │
│  │  │   React Frontend (localhost:3000)          │  │  │
│  │  │   - Dashboard                               │  │  │
│  │  │   - Devices                                 │  │  │
│  │  │   - Workflows                               │  │  │
│  │  │   - AI Assistant                            │  │  │
│  │  │   - Data                                    │  │  │
│  │  │   - Settings                                │  │  │
│  │  │                                             │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

When clicking "UI" buttons in React:
    ↓
Opens separate Qt windows for instruments
    ↓
┌──────────────────────────┐  ┌──────────────────────────┐
│  Spectrometer Window     │  │   Camera Window          │
│  (Native Qt/PyQtGraph)   │  │   (Native Qt/PyQtGraph)  │
│                          │  │                          │
│  ┌────────────────────┐  │  │  ┌────────────────────┐  │
│  │  Real-time Plot    │  │  │  │  2D Image Display  │  │
│  │  (PyQtGraph)       │  │  │  │  (PyQtGraph)       │  │
│  └────────────────────┘  │  │  └────────────────────┘  │
│  Controls & Parameters   │  │  Controls & Parameters   │
└──────────────────────────┘  └──────────────────────────┘
```

## Quick Start

### 1. Make sure React frontend is running:

```bash
cd /Users/adrien/Documents/Qudi/labpilot/frontend
npm run dev
# Should be running on http://localhost:3000
```

### 2. Launch the Qt manager window:

```bash
cd /Users/adrien/Documents/Qudi/labpilot/qt_frontend
./launch_manager.sh
```

Or directly with Python:

```bash
conda activate labpilot-dev
python manager_qt_webview.py
```

### 3. Custom URLs:

```bash
# Use different React URL
python manager_qt_webview.py --url http://localhost:5173

# Specify backend URL
python manager_qt_webview.py --backend-url http://localhost:8000
```

## Features

### ✅ What Works

- **React Frontend**: Your full React app embedded in Qt window
- **Native Feel**: Behaves like a native desktop application
- **Instrument UIs**: Click "UI" buttons in React → Opens Qt instrument windows
- **Dual Architecture**: React for management, Qt for real-time control
- **Hot Reload**: React dev server hot reload works inside Qt window
- **DevTools**: Right-click → Inspect for React DevTools

### 🎯 How It Works

1. **Manager Window** (`manager_qt_webview.py`):
   - Creates Qt `QMainWindow`
   - Embeds `QWebEngineView` (Chromium-based browser)
   - Loads your React app from `http://localhost:3000`
   - React app talks to backend API at `http://localhost:8000`

2. **Instrument Windows** (existing Qt code):
   - When React has a "Launch UI" button
   - Backend API signals to open Qt window
   - Native Qt window opens with PyQtGraph plots
   - Real-time instrument control

## File Structure

```
qt_frontend/
├── manager_qt_webview.py      # Main Qt window with embedded React
├── launch_manager.sh           # Convenient launcher script
├── instrument_windows.py       # Qt instrument control windows
├── qudi_instrument_windows.py  # Qudi-style instrument windows
└── requirements.txt            # Python dependencies
```

## Requirements

### Python Dependencies

```bash
pip install PyQt6 PyQt6-WebEngine pyqtgraph numpy
```

Already installed in `labpilot-dev` conda environment.

### React Frontend

Must be running separately:

```bash
cd ../frontend
npm install
npm run dev
```

## Development Workflow

### Typical Development Session

```bash
# Terminal 1: Start React frontend
cd /Users/adrien/Documents/Qudi/labpilot/frontend
npm run dev

# Terminal 2: Start backend API (if needed)
cd /Users/adrien/Documents/Qudi/labpilot/backend
python -m uvicorn main:app --reload

# Terminal 3: Launch Qt manager
cd /Users/adrien/Documents/Qudi/labpilot/qt_frontend
./launch_manager.sh
```

### React Development

- Edit React components in `frontend/src/`
- Changes hot-reload automatically in the Qt window
- Use browser DevTools (right-click → Inspect in Qt window)

### Qt Instrument Windows Development

- Edit `instrument_windows.py` or `qudi_instrument_windows.py`
- Restart Qt manager to see changes
- Test by clicking "UI" buttons in React interface

## Communication Flow

```
React App (in Qt window)
    ↓ HTTP requests
Backend API (FastAPI)
    ↓ Qt signals/slots or WebSockets
Qt Instrument Windows
    ↓ Direct communication
Instruments/Hardware
```

## Advantages of This Approach

1. **Keep What Works**: Your React design stays exactly as you like it
2. **No Conversion Needed**: No need to replicate React in Qt widgets
3. **Best Tools for Each Job**:
   - React for complex UIs and state management
   - Qt for real-time plotting and instrument control
4. **Easy Updates**: Update React independently from Qt
5. **Familiar Development**: Use React DevTools, hot reload, etc.

## Troubleshooting

### React frontend not loading

- Check if React dev server is running: `curl http://localhost:3000`
- Start it manually: `cd ../frontend && npm run dev`

### Blank white window

- Open DevTools (right-click → Inspect) and check console
- Verify backend API is running: `curl http://localhost:8000/api/health`

### Instrument UI windows not opening

- Check that instrument windows code is working: `python -c "from instrument_windows import *"`
- Verify backend can communicate with Qt

## Migration from Old Manager

The old pure-Qt manager implementations are still available:
- `qt_material_manager.py` - Material Design Qt version
- `manager_main.py` - Entry point for pure Qt version

But recommended approach is now:
- **Use**: `manager_qt_webview.py` (React embedded in Qt)
- **Benefits**: Keep your React design, no conversion needed

## Next Steps

1. ✅ React frontend running
2. ✅ Qt window embedding React
3. 🔄 Connect "UI" buttons to launch Qt instrument windows
4. 🔄 Implement communication between React and Qt
5. 🔄 Add system tray icon for Qt manager
6. 🔄 Package as standalone app

## Questions?

This architecture gives you:
- The React manager interface you like
- Native Qt performance for instruments
- Easy development workflow
- Best of both worlds

Enjoy! 🚀
