# LabPilot Launch Guide

## Quick Start - Launch Everything at Once

```bash
cd /Users/adrien/Documents/Qudi/labpilot
./launch_labpilot.sh
```

This script will:
1. Activate the `labpilot-dev` conda environment
2. Start the Backend API server (http://localhost:8000)
3. Start the React dev server (http://localhost:3000)
4. Launch the Qt Manager window

When you close the Qt window, all services will stop automatically.

---

## Individual Component Commands

### Option 1: Backend Only

```bash
conda activate labpilot-dev
cd /Users/adrien/Documents/Qudi/labpilot/backend
python main.py
```

**What it does:**
- Starts FastAPI backend on http://localhost:8000
- API endpoints available at http://localhost:8000/docs
- Handles device management, AI routes, Qt interface

**Check it's running:**
```bash
curl http://localhost:8000/health
```

---

### Option 2: React Frontend Only

```bash
cd /Users/adrien/Documents/Qudi/labpilot/frontend
npm run dev
```

**What it does:**
- Starts Vite dev server on http://localhost:3000
- Hot reload enabled for development
- Serves the React UI (Devices, Workflows, Flow diagram)

**Access in browser:**
```
http://localhost:3000
```

---

### Option 3: Qt Manager Only

```bash
conda activate labpilot-dev
cd /Users/adrien/Documents/Qudi/labpilot/qt_frontend
python manager_qt_webview.py
```

**What it does:**
- Opens Qt window with embedded React frontend
- Requires React dev server to be running at http://localhost:3000
- Provides Qt Bridge for launching instrument UIs
- Instrument UIs use PyQtGraph for plotting

**Prerequisites:**
- Backend must be running (port 8000)
- Frontend must be running (port 3000)

---

## Full Manual Launch (3 Terminals)

**Terminal 1 - Backend:**
```bash
conda activate labpilot-dev
cd /Users/adrien/Documents/Qudi/labpilot/backend
python main.py
```

**Terminal 2 - Frontend:**
```bash
cd /Users/adrien/Documents/Qudi/labpilot/frontend
npm run dev
```

**Terminal 3 - Qt Manager:**
```bash
conda activate labpilot-dev
cd /Users/adrien/Documents/Qudi/labpilot/qt_frontend
python manager_qt_webview.py
```

---

## Testing the Integration

Once all three are running:

1. **Test UI Launching:**
   - In Qt Manager, go to "Devices" page
   - Click the Monitor icon (🖥️) on any connected instrument
   - A Qt window should pop up with PyQtGraph plots

2. **Test Block Diagram:**
   - Go to "Flow" page
   - Should see instruments on left, workflows on right
   - Connected with animated lines

3. **Test Add Instrument:**
   - Click "+ Connect Device"
   - Fill in name, select type
   - Enter model (new field!)
   - See category displayed below model

---

## Troubleshooting

### Qt Manager shows blank screen
**Problem:** React frontend not running
**Solution:** Start React dev server first:
```bash
cd /Users/adrien/Documents/Qudi/labpilot/frontend
npm run dev
```

### UI Launch buttons don't work
**Problem:** Qt Bridge not connected
**Solution:** Check browser console for Qt Bridge messages:
- Should see: `✅ Qt Bridge ready`
- If not, restart Qt Manager

### Block diagram is empty
**Problem:** No data from Qt Bridge
**Solution:** Check Flow.tsx is using `qtBridge.getBlockDiagram()`
- Open browser DevTools (F12)
- Check Console for errors
- Should see QtBridge logs

### Backend connection errors
**Problem:** Backend not running or wrong port
**Solution:** Verify backend is on port 8000:
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy","service":"labpilot-api"}
```

---

## Log Files (when using launch script)

- Backend logs: `/tmp/labpilot_backend.log`
- Frontend logs: `/tmp/labpilot_frontend.log`

**View logs in real-time:**
```bash
tail -f /tmp/labpilot_backend.log
tail -f /tmp/labpilot_frontend.log
```

---

## Stopping Everything

### If using launch script:
- Just close the Qt Manager window
- Script automatically stops backend and frontend

### If running manually:
- Press `Ctrl+C` in each terminal window

### Nuclear option:
```bash
# Kill all node/vite processes
pkill -f "vite"

# Kill all python processes (careful!)
pkill -f "main.py"
```

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│   Qt Manager Window (PyQt6)             │
│   ┌─────────────────────────────────┐   │
│   │  QWebEngineView                 │   │
│   │  ┌───────────────────────────┐  │   │
│   │  │  React App (localhost:3000)│  │   │
│   │  │  - Devices Page            │  │   │
│   │  │  - Workflows Page          │  │   │
│   │  │  - Flow Page (ReactFlow)   │  │   │
│   │  └───────────────────────────┘  │   │
│   └─────────────────────────────────┘   │
│            ↕ QtBridge (QWebChannel)     │
│   ┌─────────────────────────────────┐   │
│   │  Qt Bridge (Python)             │   │
│   │  - getInstruments()             │   │
│   │  - launchInstrumentUI()         │   │
│   │  - getBlockDiagram()            │   │
│   └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
            ↕
┌─────────────────────────────────────────┐
│  Backend API (FastAPI + Uvicorn)        │
│  http://localhost:8000                  │
│  - /api/devices                         │
│  - /api/workflows                       │
│  - /api/ai                              │
└─────────────────────────────────────────┘
            ↕
┌─────────────────────────────────────────┐
│  Frontend Dev Server (Vite)             │
│  http://localhost:3000                  │
│  - React components                     │
│  - TailwindCSS styling                  │
│  - ReactFlow for diagrams               │
└─────────────────────────────────────────┘
```

### Instrument UI Windows
When you click "Launch UI" on a device:
```
┌────────────────────────────────────────┐
│  Hybrid Instrument Window (PyQt6)     │
│  ┌─────────────┬──────────────────┐   │
│  │ PyQtGraph   │  React Controls  │   │
│  │ Plot (70%)  │  (QWebEngine 30%)│   │
│  │             │                  │   │
│  │ Real-time   │  - Start/Stop    │   │
│  │ Spectrum    │  - Parameters    │   │
│  │ or Image    │  - Settings      │   │
│  └─────────────┴──────────────────┘   │
└────────────────────────────────────────┘
```

---

## Next Steps

After launching, you should:

1. ✅ Verify all three components are running
2. ✅ Test UI launching from Devices page
3. ✅ Check Flow diagram shows connections
4. ✅ Test Add Instrument modal (now has Model field!)
5. ✅ Test session save/load functionality

**Happy experimenting! 🚀**
