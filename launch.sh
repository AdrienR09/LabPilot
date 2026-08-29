#!/bin/bash
# LabPilot Launcher - Backend + Frontend + Qt Manager

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="labpilot-dev"

echo "🚀 LabPilot Launcher"
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

# Defensive pre-flight cleanup: a previous run that was killed via a closed
# window rather than Ctrl-C can leave the backend/frontend running on these
# ports, so every launch would silently talk to stale code otherwise.
echo "🧹 Clearing any leftover processes on ports 3000/8000..."
lsof -ti :3000 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null || true
pkill -9 -f "manager_qt_webview" 2>/dev/null || true
sleep 1

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    pkill -f "vite" 2>/dev/null || true
    if [[ -n "$BACKEND_PID" ]]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    echo "✅ Done"
}

trap cleanup EXIT INT TERM

# Start Backend (real instrument registry, dashboard/catalog/connect/disconnect routes)
echo "🐍 Starting Backend (port 8000)..."
cd "$PROJECT_ROOT"
labpilot start > /tmp/labpilot_backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

echo "  Waiting for backend to be ready..."
# A cold Python bytecode cache (e.g. right after pulling/editing a lot of
# files) can make the first import noticeably slower than a normal restart
# — 45s comfortably covers that without dragging out a genuine failure,
# which is instead caught fast below by noticing the process already died.
for i in $(seq 1 45); do
    if curl -s -o /dev/null http://localhost:8000/api/health; then
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "❌ Backend process exited unexpectedly"
        tail /tmp/labpilot_backend.log
        exit 1
    fi
    sleep 1
done

if ! curl -s -o /dev/null http://localhost:8000/api/health; then
    echo "❌ Backend failed to start"
    tail /tmp/labpilot_backend.log
    exit 1
fi

echo "✅ Backend ready at http://localhost:8000"
echo ""

# Start React Frontend
# npm's shebang is `#!/usr/bin/env node` — node only lives in the base conda
# env, so make sure it's resolvable regardless of which env got activated above.
echo "⚛️  Starting React Frontend (port 3000)..."
cd "$PROJECT_ROOT/frontend"
PATH="/opt/miniconda3/bin:$PATH" /opt/miniconda3/bin/npm run dev > /tmp/labpilot_frontend.log 2>&1 &
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
cd "$PROJECT_ROOT/src/ui/desktop"
python manager_qt_webview.py

# Cleanup runs on exit
