#!/bin/bash
# LabPilot Manager Launcher
# Starts the Qt window with embedded React frontend

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              LabPilot Manager - Qt + React                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if React frontend is running
if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200"; then
    echo "⚠️  React frontend is not running on http://localhost:3000"
    echo ""
    echo "Please start the React frontend first:"
    echo "  cd /Users/adrien/Documents/Qudi/labpilot/frontend"
    echo "  npm run dev"
    echo ""
    exit 1
fi

echo "✓ React frontend is running on http://localhost:3000"
echo ""

# Activate conda environment and launch Qt window
cd "$(dirname "$0")"
conda activate labpilot-dev
python manager_qt_webview.py "$@"
