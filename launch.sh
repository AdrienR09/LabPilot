#!/bin/bash
# LabPilot Simple Launcher - Frontend + Qt Manager
# No backend required for fake instruments

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="labpilot-dev"

echo "🚀 LabPilot Launcher (Standalone Mode)"
echo "======================================"
echo ""

# Activate conda environment
echo "📦 Activating conda environment: $CONDA_ENV"
eval "$(conda shell.bash hook)"
conda activate $CONDA_ENV 2>/dev/null || true

if [[ "$CONDA_DEFAULT_ENV" != "$CONDA_ENV" ]]; then
    echo "❌ Failed to activate conda environment"
    exit 1
fi

echo "✅ Conda ready"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    pkill -f "vite" 2>/dev/null || true
    echo "✅ Done"
}

trap cleanup EXIT INT TERM

# Start React Frontend
echo "⚛️  Starting React Frontend (port 3000)..."
cd "$PROJECT_ROOT/frontend"
/opt/miniconda3/bin/npm run dev > /tmp/labpilot_frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# Wait for React to be ready
echo "  Waiting for React to start..."
sleep 8

if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo "❌ Frontend failed to start"
    tail /tmp/labpilot_frontend.log
    exit 1
fi

echo "✅ React Frontend ready at http://localhost:3000"
echo ""

# Launch Qt Manager
echo "🪟 Launching Qt Manager..."
cd "$PROJECT_ROOT/qt_frontend"
python manager_qt_webview.py

# Cleanup runs on exit
