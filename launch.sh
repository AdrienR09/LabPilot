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

# The manager spawns its backend by running the `labpilot` console script by
# name, so a missing/stale install shows up much later as an opaque "server
# never became ready". Say so here instead.
#
# Actually RUN it rather than just checking PATH: pip bakes the entry point's
# import into the shim at install time, so a shim generated before the
# packages were renamed still says `from core.cli import main` and dies with
# ModuleNotFoundError even though `import labpilot` works fine. `command -v`
# passes happily in that state.
if ! command -v labpilot >/dev/null 2>&1; then
    echo "❌ The 'labpilot' command is not on PATH in $CONDA_ENV"
    echo "   Install the package first:  pip install -e $PROJECT_ROOT"
    exit 1
fi
if ! labpilot --help >/dev/null 2>&1; then
    echo "❌ $(command -v labpilot) is stale — it runs, but its import fails:"
    labpilot --help 2>&1 | tail -3 | sed 's/^/   /'
    echo "   Reinstall to regenerate it:  pip install -e $PROJECT_ROOT --no-deps"
    exit 1
fi
echo "✅ labpilot: $(command -v labpilot)"
echo "   Runs are saved automatically to ${LABPILOT_HOME:-$HOME/.labpilot}/data"
echo ""

FRONTEND_LOG=/tmp/labpilot_frontend.log
SERVER_LOG="$HOME/.labpilot/logs/manager_server.log"
FRONTEND_PID=""

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
    # Kill the process group we actually started: `npm run dev` forks vite as
    # a child, so killing the npm PID alone leaves vite holding port 3000 and
    # the next launch silently serves the old bundle. pkill -f "vite" was the
    # blunt version of this and also killed unrelated vite projects.
    if [[ -n "$FRONTEND_PID" ]]; then
        kill -- "-$FRONTEND_PID" 2>/dev/null || kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    lsof -ti :3000 2>/dev/null | xargs kill -9 2>/dev/null || true
    echo "✅ Done"
}

trap cleanup EXIT INT TERM

# Start React Frontend
# npm's shebang is `#!/usr/bin/env node` — node only lives in the base conda
# env, so make sure it's resolvable regardless of which env got activated above.
echo "⚛️  Starting React Frontend (port 3000)..."
cd "$PROJECT_ROOT/frontend"
# Own process group, so cleanup() can take vite down with npm.
set -m
PATH="/opt/miniconda3/bin:$PATH" /opt/miniconda3/bin/npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
set +m
echo "  Frontend PID: $FRONTEND_PID"

# Wait until it actually answers, rather than for a fixed 8 seconds: a cold
# `npm install`ed tree takes longer than that, and a warm one is ready in ~1s.
echo -n "  Waiting for React to start"
for _ in $(seq 1 60); do
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo ""
        echo "❌ Frontend exited during startup — last lines of $FRONTEND_LOG:"
        tail -20 "$FRONTEND_LOG"
        exit 1
    fi
    if curl -sf -o /dev/null http://localhost:3000; then
        READY=1
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

if [[ -z "${READY:-}" ]]; then
    echo "❌ Frontend never answered on http://localhost:3000 — last lines of $FRONTEND_LOG:"
    tail -20 "$FRONTEND_LOG"
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
echo "   Backend log: $SERVER_LOG"
# The managed server appends to that log across launches, so note where this
# launch starts writing — otherwise a failure here tails the PREVIOUS run's
# traceback, which reads exactly like a live error and is not one.
LOG_OFFSET=0
if [[ -f "$SERVER_LOG" ]]; then
    LOG_OFFSET=$(wc -c < "$SERVER_LOG" | tr -d ' ')
fi
# `-m` from anywhere: the desktop modules import each other by full package
# name, so nothing needs a particular cwd any more. (This used to have to
# `cd` into src/labpilot/ui/desktop, because the imports were flat.)
# Note the status directly rather than via `if ! ...`, where `$?` is the
# negation's own result and every failure reports as status 0.
STATUS=0
python -m labpilot.ui.desktop.manager_qt_webview "$@" || STATUS=$?
if [[ $STATUS -ne 0 ]]; then
    echo ""
    echo "❌ Manager exited with status $STATUS."
    # Its most common failure is the backend subprocess it owns failing to
    # come up, and that process logs to a file rather than to this terminal.
    if [[ -f "$SERVER_LOG" ]]; then
        echo "   Backend output from THIS launch ($SERVER_LOG):"
        tail -c "+$((LOG_OFFSET + 1))" "$SERVER_LOG" | tail -20 | sed 's/^/   /'
    fi
    exit $STATUS
fi

# Cleanup runs on exit
