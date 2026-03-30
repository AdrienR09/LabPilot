"""
Qt Interface Launcher API
Handles launching and managing the Qt desktop interface from the web frontend
"""

import os
import subprocess
import sys
import platform
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import psutil
import signal

router = APIRouter(prefix="/qt-interface", tags=["qt-interface"])

# Global process tracking
qt_process = None

def find_qt_frontend_path():
    """Find the Qt frontend directory"""
    current_dir = Path(__file__).parent.parent
    qt_frontend_path = current_dir / "qt_frontend"

    if not qt_frontend_path.exists():
        # Try parent directory
        qt_frontend_path = current_dir.parent / "qt_frontend"

    if not qt_frontend_path.exists():
        raise FileNotFoundError("Qt frontend directory not found")

    return qt_frontend_path

def get_python_executable():
    """Get the appropriate Python executable"""
    # Try to use the same Python that's running this server
    return sys.executable

def is_qt_process_running():
    """Check if Qt interface process is still running"""
    global qt_process
    if qt_process is None:
        return False

    try:
        # Check if process is still alive
        return qt_process.poll() is None
    except:
        return False

@router.post("/launch")
async def launch_qt_interface():
    """Launch the Qt desktop interface"""
    global qt_process

    try:
        qt_frontend_path = find_qt_frontend_path()
        python_exe = get_python_executable()
        main_py = qt_frontend_path / "main.py"

        if not main_py.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Qt frontend main.py not found at {main_py}"
            )

        # Check if already running
        if is_qt_process_running():
            return JSONResponse({
                "status": "already_running",
                "message": "Qt interface is already running",
                "pid": qt_process.pid if qt_process else None
            })

        # Prepare environment
        env = os.environ.copy()

        # Set Python path to include the qt_frontend directory
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{qt_frontend_path}:{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = str(qt_frontend_path)

        # Launch command based on platform
        if platform.system() == "Windows":
            # Windows
            cmd = [python_exe, str(main_py)]
            qt_process = subprocess.Popen(
                cmd,
                cwd=qt_frontend_path,
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            # Linux/macOS - try to launch in a new terminal
            if platform.system() == "Darwin":  # macOS
                # Use osascript to launch in Terminal.app
                cmd = [
                    "osascript", "-e",
                    f'tell application "Terminal" to do script "cd {qt_frontend_path} && {python_exe} main.py"'
                ]
            else:  # Linux
                # Try different terminal emulators
                terminals = ["gnome-terminal", "konsole", "xterm", "terminal"]
                terminal_cmd = None

                for terminal in terminals:
                    if subprocess.run(["which", terminal], capture_output=True).returncode == 0:
                        if terminal == "gnome-terminal":
                            terminal_cmd = [terminal, "--", python_exe, str(main_py)]
                        elif terminal == "konsole":
                            terminal_cmd = [terminal, "-e", python_exe, str(main_py)]
                        else:
                            terminal_cmd = [terminal, "-e", f"{python_exe} {main_py}"]
                        break

                if terminal_cmd:
                    cmd = terminal_cmd
                else:
                    # Fallback: launch without terminal (background process)
                    cmd = [python_exe, str(main_py)]

            qt_process = subprocess.Popen(
                cmd,
                cwd=qt_frontend_path,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        # Give it a moment to start
        import time
        time.sleep(0.5)

        # Check if it started successfully
        if qt_process.poll() is None:
            return JSONResponse({
                "status": "launched",
                "message": "Qt interface launched successfully",
                "pid": qt_process.pid,
                "path": str(qt_frontend_path)
            })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "failed",
                    "message": "Qt interface failed to start",
                    "return_code": qt_process.poll()
                }
            )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Qt frontend not found: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to launch Qt interface: {str(e)}"
        )

@router.get("/status")
async def get_qt_interface_status():
    """Get the current status of the Qt interface"""
    global qt_process

    if qt_process is None:
        return JSONResponse({
            "status": "stopped",
            "message": "Qt interface not launched from web interface",
            "pid": None
        })

    if is_qt_process_running():
        return JSONResponse({
            "status": "running",
            "message": "Qt interface is running",
            "pid": qt_process.pid
        })
    else:
        return JSONResponse({
            "status": "stopped",
            "message": "Qt interface has stopped",
            "pid": None
        })

@router.post("/stop")
async def stop_qt_interface():
    """Stop the Qt interface"""
    global qt_process

    if qt_process is None or not is_qt_process_running():
        return JSONResponse({
            "status": "not_running",
            "message": "Qt interface is not running"
        })

    try:
        # Try graceful termination first
        qt_process.terminate()

        # Wait up to 5 seconds for graceful shutdown
        try:
            qt_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill if it doesn't shut down gracefully
            qt_process.kill()
            qt_process.wait()

        qt_process = None

        return JSONResponse({
            "status": "stopped",
            "message": "Qt interface stopped successfully"
        })

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop Qt interface: {str(e)}"
        )

@router.get("/path")
async def get_qt_frontend_path():
    """Get the path to the Qt frontend directory"""
    try:
        qt_frontend_path = find_qt_frontend_path()
        return JSONResponse({
            "path": str(qt_frontend_path),
            "exists": qt_frontend_path.exists(),
            "main_py_exists": (qt_frontend_path / "main.py").exists()
        })
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Qt frontend directory not found: {str(e)}"
        )