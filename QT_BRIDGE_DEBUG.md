# Qt Bridge Debugging Guide

## Current Status
✅ Qt Manager window is running
✅ React dev server is running on localhost:3000
✅ Fake instruments and workflows show in tabs

## What to Check

### 1. Open Browser Console (F12)
When the Qt Manager window is open:
1. Right-click in the window → "Inspect Element" or press **F12**
2. Go to the **Console** tab
3. Look for these messages in order:

**Expected sequence:**
```
📱 Page loading started: http://localhost:3000
📊 Page loading progress: 25%
📊 Page loading progress: 50%
📊 Page loading progress: 75%
✅ React app loaded successfully
🔧 Initializing Qt Bridge communication...
🚀 Qt Bridge initialization starting...
Step 1: Checking for QWebChannel...
✅ QWebChannel already available
Step 2: Initializing after delay...
  typeof QWebChannel: function
  typeof qt: object
Step 3: Creating QWebChannel...
  ✅ QWebChannel initialized
  Available objects: ["qtBridge"]
  ✅ window.qtBridge set successfully
  launchInstrumentUI type: function
  ✅ qt-bridge-ready event dispatched
🔧 Initializing Qt Bridge...
🎉 Qt bridge ready event received!
✅ Qt Bridge initialized successfully
   launchInstrumentUI type: function
```

### 2. Test the Bridge Manually
In the browser console (F12), type:

```javascript
// Check if bridge is available
window.qtBridge
//  Should show [Object]

// Try launching an instrument
window.qtBridge.launchInstrumentUI('spec-001')
// Should open a new Qt window

// Get instruments
window.qtBridge.getInstruments()
```

### 3. Common Issues and Fixes

| Issue | Solution |
|-------|----------|
| `typeof QWebChannel: undefined` | Qt resources not loading. Try F5 refresh |
| `typeof qt: undefined` | Not running in Qt WebEngine - try closing browser, use only Qt window |
| `channel.objects: []` | Qt Bridge not registered properly - restart Qt Manager |
| `window.qtBridge undefined after connection` | qtBridge object not exposed - check qt_bridge.py |

### 4. If Qt Bridge Still Not Working
Try these steps:

1. **Close any browser tabs** showing localhost:3000
2. **Kill all processes**:
   ```bash
   pkill -9 python
   pkill -9 vite
   pkill -9 node
   ```
3. **Restart everything:**
   ```bash
   cd /Users/adrien/Documents/Qudi/labpilot/frontend
   npm run dev &
   sleep 15
   cd ../qt_frontend
   python manager_qt_webview.py
   ```
4. **Check console immediately** (F12) - don't wait

### 5. File Locations
- Main Initialization: `/Users/adrien/Documents/Qudi/labpilot/qt_frontend/manager_qt_webview.py` (line 90+)
- React Bridge Init: `/Users/adrien/Documents/Qudi/labpilot/frontend/src/utils/qtBridge.js` (line 27+)
- Qt Bridge Methods: `/Users/adrien/Documents/Qudi/labpilot/qt_frontend/qt_bridge.py` (line 14+)

## Next Steps
1. Open Qt Manager window
2. Press F12 to open DevTools
3. Share the console output showing the initialization sequence
4. Then test clicking instrument Monitor buttons

---
*Last Updated: 2026-03-29*
