#!/bin/bash

# LabPilot Qt Frontend Launcher
# Professional Laboratory Automation System

echo "🔬 LabPilot Qt Frontend Launcher"
echo "==============================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ and try again"
    exit 1
fi

# Check Python version
python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
echo "🐍 Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if PyQt6 installation was successful
echo "✅ Checking PyQt6 installation..."
python3 -c "from PyQt6.QtWidgets import QApplication; print('PyQt6 installation: OK')" || {
    echo "❌ PyQt6 installation failed. Trying alternative installation..."
    pip install --upgrade --force-reinstall PyQt6
}

# Check pyqtgraph
python3 -c "import pyqtgraph as pg; print(f'pyqtgraph version: {pg.__version__}')" || {
    echo "❌ pyqtgraph installation failed"
    exit 1
}

# Launch the application
echo "🚀 Launching LabPilot Qt Frontend..."
echo ""
python3 main.py

# Keep terminal open on macOS/Linux
if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo ""
    echo "Press any key to exit..."
    read -n 1
fi