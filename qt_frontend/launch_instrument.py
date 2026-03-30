#!/usr/bin/env python3
"""
LabPilot Individual Qt Window Launcher
Called by backend API to launch specific instrument Qt windows
"""

import sys
import subprocess
import argparse
from pathlib import Path

def launch_instrument_window(instrument_id: str, instrument_type: str, dimensionality: str):
    """Launch Qt window for specific instrument"""
    try:
        qt_frontend_path = Path(__file__).parent
        main_py = qt_frontend_path / "main.py"

        if not main_py.exists():
            raise FileNotFoundError(f"main.py not found at {main_py}")

        # Launch Qt window with specific instrument parameters
        cmd = [
            sys.executable,
            str(main_py),
            "--instrument", instrument_id,
            "--type", instrument_type,
            "--dimensionality", dimensionality
        ]

        # Launch in background
        process = subprocess.Popen(
            cmd,
            cwd=qt_frontend_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        print(f"✅ Launched Qt window for instrument {instrument_id} (PID: {process.pid})")
        return process.pid

    except Exception as e:
        print(f"❌ Failed to launch Qt window: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Launch individual Qt instrument window')
    parser.add_argument('--instrument', required=True, help='Instrument ID')
    parser.add_argument('--type', required=True, choices=['detector', 'motor'], help='Instrument type')
    parser.add_argument('--dimensionality', required=True, help='Instrument dimensionality')

    args = parser.parse_args()

    pid = launch_instrument_window(args.instrument, args.type, args.dimensionality)
    sys.exit(0 if pid else 1)

if __name__ == "__main__":
    main()