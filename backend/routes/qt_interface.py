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

def find_existing_qt_processes(app_type: str = "manager"):
    """Find existing Qt application processes"""
    app_name = f"{app_type}.py"
    existing_processes = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline'] or []
            if any(app_name in arg for arg in cmdline):
                existing_processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cmdline': ' '.join(cmdline)
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return existing_processes

def find_qt_frontend_path():
    """Find the Qt frontend directory"""
    current_dir = Path(__file__).parent.parent

    # Try multiple possible locations
    possible_paths = [
        current_dir / "qt_frontend",
        current_dir.parent / "qt_frontend",
        Path("/Users/adrien/Documents/Qudi/labpilot/qt_frontend"),  # Absolute path
        Path.cwd() / "qt_frontend",  # From current working directory
    ]

    for qt_frontend_path in possible_paths:
        if qt_frontend_path.exists() and (qt_frontend_path / "main.py").exists():
            print(f"Found Qt frontend at: {qt_frontend_path}")
            return qt_frontend_path

    # Debug: print what we tried
    print("Qt frontend search paths tried:")
    for path in possible_paths:
        print(f"  - {path} (exists: {path.exists()})")

    raise FileNotFoundError(f"Qt frontend directory not found. Tried: {possible_paths}")

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
async def launch_qt_interface(app_type: str = "manager"):
    """Launch the Qt desktop interface

    Args:
        app_type: Type of Qt application to launch ('manager' or 'instruments')
    """
    global qt_process

    try:
        qt_frontend_path = find_qt_frontend_path()
        python_exe = get_python_executable()

        # Choose which application to launch
        if app_type == "manager":
            app_file = qt_frontend_path / "manager.py"
        elif app_type == "modern":
            app_file = qt_frontend_path / "modern_manager.py"
        elif app_type == "hybrid":
            app_file = qt_frontend_path / "hybrid_manager.py"
        elif app_type == "launcher":
            app_file = qt_frontend_path / "launch_interfaces.py"
        else:
            app_file = qt_frontend_path / "main.py"

        if not app_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Qt frontend {app_file.name} not found at {app_file}"
            )

        # Check if already running
        if is_qt_process_running():
            return JSONResponse({
                "status": "already_running",
                "message": "Qt interface is already running from this API",
                "pid": qt_process.pid if qt_process else None
            })

        # Check for existing Qt processes not started by this API
        existing_processes = find_existing_qt_processes(app_type)
        if existing_processes:
            return JSONResponse({
                "status": "external_process_found",
                "message": f"Qt {app_type} is already running (launched externally)",
                "processes": existing_processes,
                "suggestion": "Use the running instance or stop existing processes first"
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
            cmd = [python_exe, str(app_file)]
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
                    f'tell application "Terminal" to do script "cd {qt_frontend_path} && {python_exe} {app_file.name}"'
                ]
            else:  # Linux
                # Try different terminal emulators
                terminals = ["gnome-terminal", "konsole", "xterm", "terminal"]
                terminal_cmd = None

                for terminal in terminals:
                    if subprocess.run(["which", terminal], capture_output=True).returncode == 0:
                        if terminal == "gnome-terminal":
                            terminal_cmd = [terminal, "--", python_exe, str(app_file)]
                        elif terminal == "konsole":
                            terminal_cmd = [terminal, "-e", python_exe, str(app_file)]
                        else:
                            terminal_cmd = [terminal, "-e", f"{python_exe} {app_file}"]
                        break

                if terminal_cmd:
                    cmd = terminal_cmd
                else:
                    # Fallback: launch without terminal (background process)
                    cmd = [python_exe, str(app_file)]

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
                "message": f"Qt {app_type} interface launched successfully",
                "pid": qt_process.pid,
                "path": str(qt_frontend_path),
                "app_type": app_type,
                "app_file": str(app_file)
            })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "failed",
                    "message": f"Qt {app_type} interface failed to start",
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

@router.get("/processes")
async def get_qt_processes():
    """Get all running Qt processes"""
    try:
        manager_processes = find_existing_qt_processes("manager")
        modern_processes = find_existing_qt_processes("modern_manager")
        hybrid_processes = find_existing_qt_processes("hybrid_manager")
        launcher_processes = find_existing_qt_processes("launch_interfaces")
        instruments_processes = find_existing_qt_processes("main")

        return JSONResponse({
            "manager_processes": manager_processes,
            "modern_processes": modern_processes,
            "hybrid_processes": hybrid_processes,
            "launcher_processes": launcher_processes,
            "instruments_processes": instruments_processes,
            "total_processes": len(manager_processes) + len(modern_processes) + len(hybrid_processes) + len(launcher_processes) + len(instruments_processes)
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Qt processes: {str(e)}"
        )

@router.post("/stop-all")
async def stop_all_qt_processes():
    """Stop all Qt processes"""
    try:
        stopped_processes = []
        failed_processes = []

        # Stop manager processes
        for proc_info in find_existing_qt_processes("manager"):
            try:
                proc = psutil.Process(proc_info['pid'])
                proc.terminate()
                stopped_processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                failed_processes.append({"process": proc_info, "error": str(e)})

        # Stop instruments processes
        for proc_info in find_existing_qt_processes("main"):
            try:
                proc = psutil.Process(proc_info['pid'])
                proc.terminate()
                stopped_processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                failed_processes.append({"process": proc_info, "error": str(e)})

        return JSONResponse({
            "status": "completed",
            "stopped_processes": stopped_processes,
            "failed_processes": failed_processes
        })

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop Qt processes: {str(e)}"
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