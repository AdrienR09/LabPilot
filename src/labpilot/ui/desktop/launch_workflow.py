#!/usr/bin/env python3
"""
LabPilot Workflow Window Launcher
Called by the Qt bridge to launch a workflow's combined native window as a
separate OS-level process/window — mirrors launch_instrument.py exactly.
"""

import argparse
import subprocess
import sys
from pathlib import Path

LOG_PATH = Path.home() / ".labpilot" / "logs" / "qt_workflow_windows.log"


def launch_workflow_window(workflow_id: str, backend_url: str = "http://localhost:8000"):
    """Launch the native combined Qt window for a workflow, by id.

    Runs as a separate process so it opens as its own OS window and a crash
    in one workflow window can't take down the manager. stdout/stderr are
    captured to a log file (not discarded) so failures are diagnosable
    instead of silently doing nothing.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # `-m`, not the path to main.py with a cwd that makes its sibling
        # imports resolve. The window's modules import each other by their
        # full package name now, so it runs from anywhere — including from
        # an installed wheel, where there is no repo to be inside.
        cmd = [
            sys.executable,
            "-m", "labpilot.ui.desktop.main",
            "--workflow", workflow_id,
            "--backend-url", backend_url,
        ]

        with open(LOG_PATH, "a") as log_file:
            process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)

        print(f"✅ Launched Qt window for workflow {workflow_id} (PID: {process.pid})")
        return process.pid

    except Exception as e:
        print(f"❌ Failed to launch Qt window: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Launch a native combined Qt workflow window')
    parser.add_argument('--workflow', required=True, help='Workflow ID')
    parser.add_argument('--backend-url', default='http://localhost:8000', help='Backend API URL')

    args = parser.parse_args()

    pid = launch_workflow_window(args.workflow, args.backend_url)
    sys.exit(0 if pid else 1)


if __name__ == "__main__":
    main()
