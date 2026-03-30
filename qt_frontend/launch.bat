@echo off
REM LabPilot Qt Frontend Launcher - Windows
REM Professional Laboratory Automation System

echo 🔬 LabPilot Qt Frontend Launcher
echo ===============================

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ from python.org and try again
    pause
    exit /b 1
)

REM Show Python version
for /f "tokens=*" %%i in ('python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"') do set python_version=%%i
echo 🐍 Python version: %python_version%

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo 📥 Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM Check PyQt6 installation
echo ✅ Checking PyQt6 installation...
python -c "from PyQt6.QtWidgets import QApplication; print('PyQt6 installation: OK')" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ PyQt6 installation failed. Trying alternative installation...
    python -m pip install --upgrade --force-reinstall PyQt6
)

REM Check pyqtgraph
python -c "import pyqtgraph as pg; print(f'pyqtgraph version: {pg.__version__}')" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ pyqtgraph installation failed
    pause
    exit /b 1
)

REM Launch the application
echo 🚀 Launching LabPilot Qt Frontend...
echo.
python main.py

REM Keep terminal open
echo.
echo Press any key to exit...
pause >nul