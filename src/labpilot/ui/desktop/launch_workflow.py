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
        desktop_path = Path(__file__).parent
        main_py = desktop_path / "main.py"

        if not main_py.exists():
            raise FileNotFoundError(f"main.py not found at {main_py}")

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(main_py),
            "--workflow", workflow_id,
            "--backend-url", backend_url,
        ]

        with open(LOG_PATH, "a") as log_file:
            process = subprocess.Popen(
                cmd,
                cwd=desktop_path,
                stdout=log_file,
                stderr=log_file,
            )

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
