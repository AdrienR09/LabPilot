# LabPilot - Quick Start

## Overview

LabPilot is a Qt + React hybrid application for managing lab instruments and workflows.

- **Frontend**: React app (Vite) embedded in Qt window via QWebEngineView
- **Instruments**: 5 fake instruments built-in for development/testing
- **No backend needed**: Works standalone with mock data

## Quick Start

```bash
cd /Users/adrien/Documents/Qudi/labpilot
./launch.sh
```

This will:
1. Start React dev server on http://localhost:3000
2. Launch Qt Manager window with embedded React

**That's it!** 🎉

## Features

### Devices Tab
- ✅ Shows 5 mock instruments by default
- ✅ UI Launch button (Monitor icon) → Opens PyQtGraph instrument UI
- ✅ Add Device button → Create new instruments
- ✅ Device model field (new!)

### Flow Tab
- ✅ Block diagram with ReactFlow
- ✅ Shows instruments (left) connected to workflows (right)
- ✅ Animated connection lines

### Workflows Tab
- ✅ List of available workflows
- ✅ Launch workflow button

## Architecture

```
┌─────────────────────────────┐
│   Qt Manager Window         │
│  ┌───────────────────────┐  │
│  │  React App (QWebView) │  │  ← Embedded React UI
│  │  - Devices Tab        │  │
│  │  - Workflows Tab      │  │
│  │  - Flow Tab           │  │
│  └───────────────────────┘  │
│        ↕ QtBridge           │
│  ┌───────────────────────┐  │
│  │  Qt Bridge (Python)   │  │  ← Qt-React Communication
│  └───────────────────────┘  │
└─────────────────────────────┘
         ↓ (launches)
┌─────────────────────────────┐
│ Instrument UI Windows       │
│ (PyQt6 + PyQtGraph plots)   │  ← Real-time plots
└─────────────────────────────┘
```

## Fake Instruments (Built-in)

1. **Tunable Spectrometer** (USB2000+) - 500-1000nm
2. **Spectrum Camera** (iXon EMCCD) - 1024×2048 CCD
3. **Tunable Laser** (Coherent Ti:Sapphire) - 700-1050nm
4. **XY Motion Stage** (Newport XPS-C8) - 2-axis
5. **Lock-in Amplifier** (Stanford SR844) - 100Hz-1MHz

All pre-loaded and ready to launch UIs!

## Troubleshooting

### Qt Manager shows blank screen
```bash
# Check React is running:
ps aux | grep vite
# Should see: node .../vite
```

### UI Launch doesn't work
- Check browser console (F12) for errors
- Should see: `✅ Qt Bridge ready`

### React won't start
```bash
# Install dependencies
cd frontend
npm install
npm run dev
```

## Adding Instruments

In Qt Manager:
1. Click "+ Connect Device"
2. Enter device name
3. Select device type
4. Enter model (new field!)
5. Click "Connect"

Device will instantly appear in devices list!

## File Structure (Cleaned Up)

```
/labpilot/
├── launch.sh              ← Single file to launch everything
├── frontend/              ← React app
│   └── src/
│       ├── pages/         ← Devices, Workflows, Flow
│       ├── components/    ← UI components
│       └── store/         ← State management (with fake data)
├── qt_frontend/           ← Qt window code
│   ├── manager_qt_webview.py
│   ├── qt_bridge.py       ← React-Qt communication
│   └── ...
├── backend/               ← Optional (not needed for fake mode)
└── docs/                  ← Documentation
```

## Next Steps

- ✅ Add more instruments by editing `frontend/src/store/index.ts`
- ✅ Customize workflows in `frontend/src/pages/Workflows.tsx`
- ✅ Extend block diagram in `frontend/src/pages/Flow.tsx`
- ⚡ Connect real instruments via backend (when ready)

---

**For development: No backend setup needed!**
**For production: Add backend integration in `launch.sh`**
