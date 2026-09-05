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
# The manager spawns its own backend subprocess (see next comment below) —
# a manager that was force-killed rather than closed normally can leave
# that subprocess orphaned, so clear it too.
pkill -9 -f "labpilot start" 2>/dev/null || true
sleep 1

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    pkill -f "vite" 2>/dev/null || true
    echo "✅ Done"
}

trap cleanup EXIT INT TERM

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

# Launch Qt Manager — this spawns and owns its own backend server process
# (src/labpilot/ui/desktop/managed_server.py) as a real subprocess, not something
# this script needs to start separately anymore: manager_qt_webview.py
# starts `labpilot start` itself and waits for it to be ready before the
# window even opens, printing a clear error and exiting non-zero if it
# can't (e.g. port 8000 already in use by something else). Pass
# --external-backend here instead if you want to point this at an
# already-running/remote server rather than let the manager own one.
echo "🪟 Launching Qt Manager (it will start its own backend server)..."
cd "$PROJECT_ROOT/src/labpilot/ui/desktop"
python manager_qt_webview.py "$@"

# Cleanup runs on exit
